import csv
import io
import secrets
import uuid
import zipfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    make_response,
    request,
    send_file,
    session,
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (
    Assignment,
    AuditLog,
    Department,
    Evaluation,
    Notification,
    Semester,
    Submission,
    Subject,
    User,
    latest_submission,
    utcnow,
)


api = Blueprint("api", __name__)
UPLOAD_EXTENSIONS = {".pdf", ".docx"}
ROLES = {"student", "professor", "admin"}


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


@api.errorhandler(ApiError)
def handle_api_error(error):
    body = {"code": error.code, "message": error.message}
    if error.fields:
        body["fields"] = error.fields
    return jsonify(success=False, error=body), error.status


def success(data, status=200):
    return jsonify(success=True, data=data), status


def payload():
    if request.mimetype == "multipart/form-data":
        return request.form.to_dict()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "Send a JSON object in the request body.")
    return data


def required_text(data, name, maximum=255):
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "VALIDATION_ERROR", f"{name.replace('_', ' ').capitalize()} is required.", {name: "Required"})
    value = value.strip()
    if len(value) > maximum:
        raise ApiError(400, "VALIDATION_ERROR", f"{name.replace('_', ' ').capitalize()} is too long.", {name: f"Maximum {maximum} characters"})
    return value


def parse_bool(data, name, default=False):
    value = data.get(name, default)
    if value == "true":
        value = True
    elif value == "false":
        value = False
    if not isinstance(value, bool):
        raise ApiError(400, "VALIDATION_ERROR", f"{name.replace('_', ' ').capitalize()} must be true or false.")
    return value


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_due_at(value):
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "VALIDATION_ERROR", "A valid due date is required.", {"due_at": "Required"})
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError as error:
        raise ApiError(400, "VALIDATION_ERROR", "Enter a valid due date.", {"due_at": "Invalid date"}) from error


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            raise ApiError(401, "UNAUTHENTICATED", "Please sign in to continue.")
        user = db.session.get(User, session["user_id"])
        if user is None or not user.is_active:
            session.clear()
            raise ApiError(401, "UNAUTHENTICATED", "This account is unavailable. Contact an administrator.")
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user.role not in roles:
                raise ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.")
            return view(*args, **kwargs)

        return wrapped

    return decorate


def audit(action, entity_type, entity_id=None):
    db.session.add(
        AuditLog(
            actor_id=g.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def notify_users(user_ids, kind, message):
    db.session.add_all(
        [Notification(user_id=user_id, kind=kind, message=message) for user_id in set(user_ids)]
    )


def student_assignments(user):
    return Assignment.query.filter(
        Assignment.status == "Published",
        Assignment.department_id == user.department_id,
        Assignment.semester_id == user.semester_id,
    ).order_by(Assignment.due_at.asc())


def professor_can_manage(user, assignment):
    return assignment.professor_id == user.id and assignment.subject in user.subjects


def assignment_status(assignment, submission):
    if submission and submission.evaluation and submission.evaluation.published_at:
        return "Evaluated"
    if submission:
        return "Submitted"
    return "Overdue" if assignment.due_at < utcnow() else "Pending"


def save_reference(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    name = secure_filename(file_storage.filename)
    if not name or Path(name).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "Reference files must be PDF or DOCX.")
    content = file_storage.read()
    if not valid_document(name, content):
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "The reference file is not a valid PDF or DOCX.")
    key = uuid.uuid4().hex
    path = Path(current_app.config["UPLOAD_FOLDER"]) / key
    path.write_bytes(content)
    return name, key


def valid_document(filename, content):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return content.startswith(b"%PDF-")
    if suffix == ".docx" and content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                return "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False
    return False


@api.get("/health")
def health():
    db.session.execute(db.select(func.count()).select_from(User))
    return success({"status": "ok"})


@api.get("/auth/csrf")
def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return success({"csrf_token": token})


@api.post("/auth/login")
def login():
    data = payload()
    identifier = required_text(data, "login_id", 160).lower()
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "VALIDATION_ERROR", "Password is required.")
    user = User.query.filter(
        db.or_(func.lower(User.login_id) == identifier, func.lower(User.email) == identifier)
    ).first()
    if user is None or not user.is_active or not user.check_password(password):
        raise ApiError(401, "INVALID_CREDENTIALS", "The login ID or password is incorrect.")
    csrf_token_value = session.get("csrf_token") or secrets.token_urlsafe(32)
    session.clear()
    session["user_id"] = user.id
    session["csrf_token"] = csrf_token_value
    return success({"user": user.public_dict(), "csrf_token": csrf_token_value})


@api.post("/auth/logout")
@login_required
def logout():
    session.clear()
    return success({"message": "Signed out."})


@api.get("/auth/me")
@login_required
def auth_me():
    return success({"user": g.user.public_dict()})


@api.post("/auth/forgot-password")
def forgot_password():
    payload()
    return success(
        {"message": "If the account exists, contact your administrator to reset its password."}
    )


@api.get("/student/dashboard")
@roles_required("student")
def student_dashboard():
    assignments = student_assignments(g.user).all()
    submissions = {
        assignment.id: latest_submission(assignment.id, g.user.id) for assignment in assignments
    }
    counts = {"total": len(assignments), "pending": 0, "submitted": 0, "overdue": 0, "evaluated": 0}
    for assignment in assignments:
        counts[assignment_status(assignment, submissions[assignment.id]).lower()] += 1
    return success(
        {
            "counts": counts,
            "upcoming": [
                assignment.public_dict(g.user)
                for assignment in assignments
                if assignment.due_at >= utcnow()
            ][:5],
            "recent_submissions": [
                submission.public_dict()
                for submission in Submission.query.filter_by(student_id=g.user.id)
                .order_by(Submission.submitted_at.desc())
                .limit(5)
            ],
        }
    )


@api.get("/student/assignments")
@roles_required("student")
def list_student_assignments():
    query = student_assignments(g.user)
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(
            db.or_(Assignment.title.ilike(f"%{search}%"), Assignment.description.ilike(f"%{search}%"))
        )
    assignments = query.all()
    return success(
        [
            {
                **assignment.public_dict(g.user),
                "derived_status": assignment_status(
                    assignment, latest_submission(assignment.id, g.user.id)
                ),
            }
            for assignment in assignments
        ]
    )


@api.post("/student/assignments/<int:assignment_id>/submissions")
@roles_required("student")
def submit_assignment(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if (
        assignment is None
        or assignment.status != "Published"
        or assignment.department_id != g.user.department_id
        or assignment.semester_id != g.user.semester_id
    ):
        raise ApiError(404, "NOT_FOUND", "Assignment not found.")
    if "file" not in request.files:
        raise ApiError(400, "VALIDATION_ERROR", "Choose a PDF or DOCX file.", {"file": "Required"})
    upload = request.files["file"]
    original_name = secure_filename(upload.filename or "")
    if not original_name or Path(original_name).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "Only PDF and DOCX files are accepted.")
    contents = upload.read()
    if not valid_document(original_name, contents):
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "The selected file is not a valid PDF or DOCX.")
    max_bytes = current_app.config["MAX_CONTENT_LENGTH"]
    if len(contents) > max_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", f"Files must be {max_bytes // (1024 * 1024)} MB or smaller.")
    now = utcnow()
    is_late = now > assignment.due_at
    if is_late and not assignment.allow_late:
        raise ApiError(400, "DEADLINE_PASSED", "Late submissions are not allowed for this assignment.")
    previous = latest_submission(assignment.id, g.user.id)
    if previous and not assignment.allow_resubmission:
        raise ApiError(409, "RESUBMISSION_DISABLED", "Resubmission is not allowed for this assignment.")

    storage_key = uuid.uuid4().hex
    path = Path(current_app.config["UPLOAD_FOLDER"]) / storage_key
    path.write_bytes(contents)
    submission = Submission(
        assignment_id=assignment.id,
        student_id=g.user.id,
        attempt=(previous.attempt + 1) if previous else 1,
        original_name=original_name,
        storage_key=storage_key,
        mime_type="application/pdf" if original_name.lower().endswith(".pdf") else
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=len(contents),
        submitted_at=now,
        is_late=is_late,
    )
    try:
        db.session.add(submission)
        notify_users(
            [assignment.professor_id],
            "submission_received",
            f"{g.user.full_name} submitted {assignment.title}.",
        )
        audit("submission.created", "submission")
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        path.unlink(missing_ok=True)
        raise ApiError(500, "SUBMISSION_SAVE_FAILED", "The submission could not be saved. Please try again.") from error
    return success(submission.public_dict(), 201)


@api.get("/student/submissions")
@roles_required("student")
def list_student_submissions():
    submissions = Submission.query.filter_by(student_id=g.user.id).order_by(
        Submission.submitted_at.desc()
    )
    return success([submission.public_dict() for submission in submissions])


@api.get("/student/notifications")
@roles_required("student", "professor", "admin")
def list_notifications():
    notifications = Notification.query.filter_by(user_id=g.user.id).order_by(
        Notification.created_at.desc()
    ).limit(50)
    return success([notification.public_dict() for notification in notifications])


@api.post("/notifications/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    notification = db.session.get(Notification, notification_id)
    if notification is None or notification.user_id != g.user.id:
        raise ApiError(404, "NOT_FOUND", "Notification not found.")
    notification.read_at = utcnow()
    db.session.commit()
    return success(notification.public_dict())


@api.get("/files/submissions/<int:submission_id>")
@login_required
def download_submission(submission_id):
    submission = db.session.get(Submission, submission_id)
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "File not found.")
    if g.user.role == "student":
        allowed = submission.student_id == g.user.id
    elif g.user.role == "professor":
        allowed = professor_can_manage(g.user, submission.assignment)
    else:
        allowed = True
    if not allowed:
        raise ApiError(404, "NOT_FOUND", "File not found.")
    path = Path(current_app.config["UPLOAD_FOLDER"]) / submission.storage_key
    if not path.is_file():
        raise ApiError(404, "FILE_MISSING", "The stored submission file is unavailable.")
    return send_file(path, as_attachment=True, download_name=submission.original_name)


@api.get("/files/references/<int:assignment_id>")
@login_required
def download_reference(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or not assignment.reference_key:
        raise ApiError(404, "NOT_FOUND", "Reference file not found.")
    if g.user.role == "student":
        allowed = (
            assignment.status == "Published"
            and g.user.department_id == assignment.department_id
            and g.user.semester_id == assignment.semester_id
        )
    elif g.user.role == "professor":
        allowed = professor_can_manage(g.user, assignment)
    else:
        allowed = True
    if not allowed:
        raise ApiError(404, "NOT_FOUND", "Reference file not found.")
    path = Path(current_app.config["UPLOAD_FOLDER"]) / assignment.reference_key
    if not path.is_file():
        raise ApiError(404, "FILE_MISSING", "The stored reference file is unavailable.")
    return send_file(path, as_attachment=True, download_name=assignment.reference_name)


@api.get("/professor/dashboard")
@roles_required("professor")
def professor_dashboard():
    assignments = Assignment.query.filter_by(professor_id=g.user.id).all()
    assignment_ids = [item.id for item in assignments]
    all_submissions = Submission.query.filter(Submission.assignment_id.in_(assignment_ids)).all() if assignment_ids else []
    students = User.query.filter_by(role="student", is_active=True).all()
    submissions = [
        latest_submission(assignment.id, student.id)
        for assignment in assignments
        if assignment.status == "Published"
        for student in students
        if student.department_id == assignment.department_id
        and student.semester_id == assignment.semester_id
        and latest_submission(assignment.id, student.id) is not None
    ]
    pending = [item for item in submissions if item.evaluation is None or item.evaluation.published_at is None]
    expected = sum(
        User.query.filter_by(
            role="student",
            is_active=True,
            department_id=item.department_id,
            semester_id=item.semester_id,
        ).count()
        for item in assignments if item.status == "Published"
    )
    return success(
        {
            "counts": {
                "assignments": len(assignments),
                "submissions": len(submissions),
                "to_evaluate": len(pending),
                "completion_percent": round((len(submissions) / expected) * 100) if expected else 0,
            },
            "assignments": [item.public_dict() for item in assignments],
            "recent_submissions": [
                item.public_dict()
                for item in sorted(all_submissions, key=lambda row: row.submitted_at, reverse=True)[:6]
            ],
        }
    )


@api.get("/professor/subjects")
@roles_required("professor")
def list_professor_subjects():
    return success([subject.public_dict() for subject in g.user.subjects])


@api.get("/professor/assignments")
@roles_required("professor")
def list_professor_assignments():
    assignments = Assignment.query.filter_by(professor_id=g.user.id).order_by(
        Assignment.created_at.desc()
    )
    return success([assignment.public_dict() for assignment in assignments])


@api.post("/professor/assignments")
@roles_required("professor")
def create_assignment():
    data = payload()
    subject_id = parse_int(data.get("subject_id"))
    department_id = parse_int(data.get("department_id"))
    semester_id = parse_int(data.get("semester_id"))
    subject = db.session.get(Subject, subject_id) if subject_id is not None else None
    if subject is None or subject not in g.user.subjects:
        raise ApiError(403, "SUBJECT_NOT_ASSIGNED", "You can only create assignments for your assigned subjects.")
    if (
        subject.department_id != department_id
        or subject.semester_id != semester_id
    ):
        raise ApiError(400, "ACADEMIC_SCOPE_MISMATCH", "Subject, department and semester must match.")
    due_at = parse_due_at(data.get("due_at"))
    if due_at <= utcnow():
        raise ApiError(400, "VALIDATION_ERROR", "The due date must be in the future.", {"due_at": "Must be in the future"})
    try:
        max_marks = float(data.get("max_marks"))
    except (TypeError, ValueError) as error:
        raise ApiError(400, "VALIDATION_ERROR", "Maximum marks must be a positive number.") from error
    if max_marks <= 0 or max_marks > 10000:
        raise ApiError(400, "VALIDATION_ERROR", "Maximum marks must be greater than zero.")
    status = data.get("status", "Draft")
    if status not in {"Draft", "Published"}:
        raise ApiError(400, "VALIDATION_ERROR", "Status must be Draft or Published.")
    title = required_text(data, "title", 160)
    description = required_text(data, "description", 5000)
    allow_late = parse_bool(data, "allow_late", True)
    allow_resubmission = parse_bool(data, "allow_resubmission", True)
    reference_name, reference_key = save_reference(request.files.get("reference"))
    assignment = Assignment(
        professor_id=g.user.id,
        department_id=subject.department_id,
        semester_id=subject.semester_id,
        subject_id=subject.id,
        title=title,
        description=description,
        due_at=due_at,
        max_marks=max_marks,
        status=status,
        allow_late=allow_late,
        allow_resubmission=allow_resubmission,
        reference_name=reference_name,
        reference_key=reference_key,
    )
    try:
        db.session.add(assignment)
        db.session.flush()
        if status == "Published":
            recipients = User.query.filter_by(
                role="student",
                is_active=True,
                department_id=assignment.department_id,
                semester_id=assignment.semester_id,
            ).with_entities(User.id).all()
            notify_users([row.id for row in recipients], "assignment_published", f"New assignment: {assignment.title}.")
        audit("assignment.created", "assignment", assignment.id)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        if reference_key:
            (Path(current_app.config["UPLOAD_FOLDER"]) / reference_key).unlink(missing_ok=True)
        raise ApiError(500, "ASSIGNMENT_SAVE_FAILED", "The assignment could not be saved.") from error
    return success(assignment.public_dict(), 201)


@api.put("/professor/assignments/<int:assignment_id>")
@roles_required("professor")
def update_assignment(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or not professor_can_manage(g.user, assignment):
        raise ApiError(404, "NOT_FOUND", "Assignment not found.")
    data = payload()
    for name, maximum in (("title", 160), ("description", 5000)):
        if name in data:
            setattr(assignment, name, required_text(data, name, maximum))
    if "due_at" in data:
        assignment.due_at = parse_due_at(data["due_at"])
    if "max_marks" in data:
        try:
            marks = float(data["max_marks"])
        except (TypeError, ValueError) as error:
            raise ApiError(400, "VALIDATION_ERROR", "Maximum marks must be a positive number.") from error
        if marks <= 0 or marks > 10000:
            raise ApiError(400, "VALIDATION_ERROR", "Maximum marks must be greater than zero.")
        assignment.max_marks = marks
    if "status" in data:
        if data["status"] not in {"Draft", "Published", "Closed"}:
            raise ApiError(400, "VALIDATION_ERROR", "Choose Draft, Published or Closed.")
        was_published = assignment.status == "Published"
        assignment.status = data["status"]
        if assignment.status == "Published" and not was_published:
            recipients = User.query.filter_by(
                role="student",
                is_active=True,
                department_id=assignment.department_id,
                semester_id=assignment.semester_id,
            ).with_entities(User.id).all()
            notify_users([row.id for row in recipients], "assignment_published", f"New assignment: {assignment.title}.")
    for name in ("allow_late", "allow_resubmission"):
        if name in data:
            setattr(assignment, name, parse_bool(data, name))
    audit("assignment.updated", "assignment", assignment.id)
    db.session.commit()
    return success(assignment.public_dict())


@api.delete("/professor/assignments/<int:assignment_id>")
@roles_required("professor")
def delete_assignment(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or not professor_can_manage(g.user, assignment):
        raise ApiError(404, "NOT_FOUND", "Assignment not found.")
    if Submission.query.filter_by(assignment_id=assignment.id).first():
        raise ApiError(409, "HAS_SUBMISSIONS", "Assignments with submissions cannot be deleted. Close it instead.")
    reference_key = assignment.reference_key
    audit("assignment.deleted", "assignment", assignment.id)
    db.session.delete(assignment)
    db.session.commit()
    if reference_key:
        (Path(current_app.config["UPLOAD_FOLDER"]) / reference_key).unlink(missing_ok=True)
    return success({"message": "Assignment deleted."})


@api.get("/professor/assignments/<int:assignment_id>/submissions")
@roles_required("professor")
def list_assignment_submissions(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or not professor_can_manage(g.user, assignment):
        raise ApiError(404, "NOT_FOUND", "Assignment not found.")
    students = User.query.filter_by(
        role="student",
        is_active=True,
        department_id=assignment.department_id,
        semester_id=assignment.semester_id,
    ).order_by(User.full_name).all()
    result = []
    for student in students:
        submission = latest_submission(assignment.id, student.id)
        result.append(
            submission.public_dict()
            if submission
            else {
                "id": None,
                "assignment_id": assignment.id,
                "assignment": assignment.title,
                "student_id": student.id,
                "student": student.full_name,
                "login_id": student.login_id,
                "attempt": 0,
                "file_name": None,
                "submitted_at": None,
                "is_late": False,
                "status": "Overdue" if assignment.due_at < utcnow() else "Pending",
                "evaluation": None,
            }
        )
    return success(result)


@api.post("/professor/submissions/<int:submission_id>/evaluation")
@roles_required("professor")
def evaluate_submission(submission_id):
    submission = db.session.get(Submission, submission_id)
    if submission is None or not professor_can_manage(g.user, submission.assignment):
        raise ApiError(404, "NOT_FOUND", "Submission not found.")
    data = payload()
    try:
        marks = float(data.get("marks"))
    except (TypeError, ValueError) as error:
        raise ApiError(400, "VALIDATION_ERROR", "Enter a valid mark.") from error
    if marks < 0 or marks > submission.assignment.max_marks:
        raise ApiError(400, "MARKS_OUT_OF_RANGE", f"Marks must be between 0 and {submission.assignment.max_marks:g}.")
    feedback = data.get("feedback", "")
    if not isinstance(feedback, str) or len(feedback) > 5000:
        raise ApiError(400, "VALIDATION_ERROR", "Feedback must be 5,000 characters or fewer.")
    publish = parse_bool(data, "publish", True)
    evaluation = submission.evaluation
    if evaluation is None:
        evaluation = Evaluation(submission=submission, evaluator_id=g.user.id)
        db.session.add(evaluation)
    evaluation.evaluator_id = g.user.id
    evaluation.marks = marks
    evaluation.feedback = feedback.strip()
    if publish:
        evaluation.published_at = utcnow()
        notify_users(
            [submission.student_id],
            "evaluation_published",
            f"Your results for {submission.assignment.title} are available.",
        )
    audit("evaluation.published" if publish else "evaluation.saved", "submission", submission.id)
    db.session.commit()
    return success(submission.public_dict())


@api.get("/admin/dashboard")
@roles_required("admin")
def admin_dashboard():
    counts = {
        "students": User.query.filter_by(role="student").count(),
        "professors": User.query.filter_by(role="professor").count(),
        "departments": Department.query.filter_by(is_active=True).count(),
        "assignments": Assignment.query.count(),
        "submissions": Submission.query.count(),
    }
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(8).all()
    return success(
        {
            "counts": counts,
            "activity": [
                {
                    "action": item.action,
                    "actor": item.actor.full_name,
                    "entity_type": item.entity_type,
                    "created_at": item.created_at.isoformat() + "Z",
                }
                for item in recent
            ],
        }
    )


@api.get("/admin/users")
@roles_required("admin")
def list_users():
    query = User.query.order_by(User.full_name)
    role = request.args.get("role")
    search = request.args.get("q", "").strip()
    if role in ROLES:
        query = query.filter_by(role=role)
    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f"%{search}%"),
                User.login_id.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )
    return success([user.public_dict() for user in query.limit(250)])


@api.post("/admin/users")
@roles_required("admin")
def create_user():
    data = payload()
    role = data.get("role")
    if role not in ROLES:
        raise ApiError(400, "VALIDATION_ERROR", "Role must be student, professor or admin.")
    login_id = required_text(data, "login_id", 80)
    email = required_text(data, "email", 160).lower()
    full_name = required_text(data, "full_name", 120)
    password = data.get("password")
    if not isinstance(password, str) or len(password) < 8:
        raise ApiError(400, "VALIDATION_ERROR", "Password must contain at least 8 characters.")
    department_id = data.get("department_id") or None
    semester_id = data.get("semester_id") or None
    department = db.session.get(Department, department_id) if department_id else None
    semester = db.session.get(Semester, semester_id) if semester_id else None
    if department_id and department is None:
        raise ApiError(400, "VALIDATION_ERROR", "Choose a valid department.")
    if semester_id and (semester is None or semester.department_id != department_id):
        raise ApiError(400, "VALIDATION_ERROR", "Choose a semester in the selected department.")
    if role == "student" and (department is None or semester is None):
        raise ApiError(400, "VALIDATION_ERROR", "Students need a department and semester.")
    user = User(
        login_id=login_id,
        email=email,
        role=role,
        full_name=full_name,
        department_id=department_id,
        semester_id=semester_id,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    subject_ids = data.get("subject_ids", [])
    if role == "professor":
        if not isinstance(subject_ids, list):
            raise ApiError(400, "VALIDATION_ERROR", "subject_ids must be a list.")
        for subject_id in subject_ids:
            subject = db.session.get(Subject, subject_id)
            if subject is None:
                raise ApiError(400, "VALIDATION_ERROR", "One or more subjects are invalid.")
            if department_id and subject.department_id != department_id:
                raise ApiError(400, "VALIDATION_ERROR", "Assigned subjects must belong to the professor's department.")
            user.subjects.append(subject)
    audit("user.created", "user", user.id)
    db.session.commit()
    return success(user.public_dict(), 201)


@api.put("/admin/users/<int:user_id>")
@roles_required("admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "User not found.")
    data = payload()
    for name, maximum in (("full_name", 120), ("email", 160), ("login_id", 80)):
        if name in data:
            value = required_text(data, name, maximum)
            setattr(user, name, value.lower() if name == "email" else value)
    if "is_active" in data:
        user.is_active = parse_bool(data, "is_active")
    if "department_id" in data:
        department_id = data["department_id"] or None
        if department_id and db.session.get(Department, department_id) is None:
            raise ApiError(400, "VALIDATION_ERROR", "Choose a valid department.")
        user.department_id = department_id
    if "semester_id" in data:
        semester_id = data["semester_id"] or None
        semester = db.session.get(Semester, semester_id) if semester_id else None
        if semester_id and (semester is None or semester.department_id != user.department_id):
            raise ApiError(400, "VALIDATION_ERROR", "Choose a semester in the selected department.")
        user.semester_id = semester_id
    if "password" in data:
        password = data["password"]
        if not isinstance(password, str) or len(password) < 8:
            raise ApiError(400, "VALIDATION_ERROR", "Password must contain at least 8 characters.")
        user.set_password(password)
    if user.id == g.user.id and not user.is_active:
        raise ApiError(400, "VALIDATION_ERROR", "You cannot deactivate your own account.")
    audit("user.updated", "user", user.id)
    db.session.commit()
    return success(user.public_dict())


@api.get("/admin/departments")
@roles_required("admin")
def list_departments():
    return success([item.public_dict() for item in Department.query.order_by(Department.name)])


@api.post("/admin/departments")
@roles_required("admin")
def create_department():
    data = payload()
    item = Department(
        code=required_text(data, "code", 20).upper(),
        name=required_text(data, "name", 120),
    )
    db.session.add(item)
    db.session.flush()
    audit("department.created", "department", item.id)
    db.session.commit()
    return success(item.public_dict(), 201)


@api.get("/admin/semesters")
@roles_required("admin")
def list_semesters():
    return success([item.public_dict() for item in Semester.query.order_by(Semester.department_id, Semester.number)])


@api.post("/admin/semesters")
@roles_required("admin")
def create_semester():
    data = payload()
    department_id = data.get("department_id")
    try:
        number = int(data.get("number"))
    except (TypeError, ValueError) as error:
        raise ApiError(400, "VALIDATION_ERROR", "Semester number must be a positive integer.") from error
    if db.session.get(Department, department_id) is None or number < 1 or number > 12:
        raise ApiError(400, "VALIDATION_ERROR", "Choose a department and a semester from 1 to 12.")
    item = Semester(
        department_id=department_id,
        number=number,
        academic_year=required_text(data, "academic_year", 20),
    )
    db.session.add(item)
    db.session.flush()
    audit("semester.created", "semester", item.id)
    db.session.commit()
    return success(item.public_dict(), 201)


@api.get("/admin/subjects")
@roles_required("admin")
def list_subjects():
    return success([item.public_dict() for item in Subject.query.order_by(Subject.name)])


@api.post("/admin/subjects")
@roles_required("admin")
def create_subject():
    data = payload()
    department_id = data.get("department_id")
    semester_id = data.get("semester_id")
    semester = db.session.get(Semester, semester_id) if semester_id else None
    if semester is None or semester.department_id != department_id:
        raise ApiError(400, "VALIDATION_ERROR", "Choose a semester in the selected department.")
    item = Subject(
        department_id=department_id,
        semester_id=semester_id,
        code=required_text(data, "code", 30).upper(),
        name=required_text(data, "name", 120),
    )
    db.session.add(item)
    db.session.flush()
    professor_ids = data.get("professor_ids", [])
    if not isinstance(professor_ids, list):
        raise ApiError(400, "VALIDATION_ERROR", "professor_ids must be a list.")
    for professor_id in professor_ids:
        professor = db.session.get(User, professor_id)
        if professor is None or professor.role != "professor":
            raise ApiError(400, "VALIDATION_ERROR", "One or more professors are invalid.")
        if professor.department_id and professor.department_id != department_id:
            raise ApiError(400, "VALIDATION_ERROR", "Professor must belong to the subject department.")
        item.professors.append(professor)
    audit("subject.created", "subject", item.id)
    db.session.commit()
    return success(item.public_dict(), 201)


@api.get("/admin/reports")
@roles_required("admin")
def admin_report():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Student", "USN / Login ID", "Department", "Semester", "Assignment", "Subject", "Submitted At", "Late", "Status", "Marks", "Feedback"]
    )
    for submission in Submission.query.order_by(Submission.submitted_at.desc()).all():
        evaluation = submission.evaluation
        published = evaluation is not None and evaluation.published_at is not None
        writer.writerow(
            [
                submission.student.full_name,
                submission.student.login_id,
                submission.student.department.name if submission.student.department else "",
                submission.student.semester.number if submission.student.semester else "",
                submission.assignment.title,
                submission.assignment.subject.name,
                submission.submitted_at.isoformat(),
                "Yes" if submission.is_late else "No",
                "Evaluated" if published else "Submitted",
                evaluation.marks if published else "",
                evaluation.feedback if published else "",
            ]
        )
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="ams-report.csv"'
    return response
