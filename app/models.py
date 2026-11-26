from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


professor_subjects = db.Table(
    "professor_subjects",
    db.Column("professor_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("subject_id", db.Integer, db.ForeignKey("subjects.id"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    semester = db.relationship("Semester", foreign_keys=[semester_id])
    subjects = db.relationship("Subject", secondary=professor_subjects, back_populates="professors")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def public_dict(self):
        return {
            "id": self.id,
            "login_id": self.login_id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "department_id": self.department_id,
            "department": self.department.name if self.department else None,
            "semester_id": self.semester_id,
            "semester": self.semester.number if self.semester else None,
            "is_active": self.is_active,
        }


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def public_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name, "is_active": self.is_active}


class Semester(db.Model):
    __tablename__ = "semesters"
    __table_args__ = (
        db.UniqueConstraint("department_id", "number", "academic_year", name="uq_semester_scope"),
    )

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)

    department = db.relationship("Department")

    def public_dict(self):
        return {
            "id": self.id,
            "department_id": self.department_id,
            "department": self.department.name,
            "number": self.number,
            "academic_year": self.academic_year,
        }


class Subject(db.Model):
    __tablename__ = "subjects"
    __table_args__ = (
        db.UniqueConstraint("department_id", "semester_id", "code", name="uq_subject_scope"),
    )

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)

    department = db.relationship("Department")
    semester = db.relationship("Semester")
    professors = db.relationship("User", secondary=professor_subjects, back_populates="subjects")

    def public_dict(self):
        return {
            "id": self.id,
            "department_id": self.department_id,
            "department": self.department.name,
            "semester_id": self.semester_id,
            "semester": self.semester.number,
            "code": self.code,
            "name": self.name,
            "professor_ids": [user.id for user in self.professors],
        }


class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_at = db.Column(db.DateTime, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Draft")
    allow_late = db.Column(db.Boolean, nullable=False, default=True)
    allow_resubmission = db.Column(db.Boolean, nullable=False, default=True)
    reference_name = db.Column(db.String(255))
    reference_key = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    professor = db.relationship("User", foreign_keys=[professor_id])
    department = db.relationship("Department")
    semester = db.relationship("Semester")
    subject = db.relationship("Subject")

    def public_dict(self, student=None):
        latest = None
        if student is not None:
            latest = latest_submission(self.id, student.id)
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "department_id": self.department_id,
            "department": self.department.name,
            "semester_id": self.semester_id,
            "semester": self.semester.number,
            "subject_id": self.subject_id,
            "subject": self.subject.name,
            "subject_code": self.subject.code,
            "professor": self.professor.full_name,
            "due_at": self.due_at.isoformat() + "Z",
            "max_marks": self.max_marks,
            "status": self.status,
            "allow_late": self.allow_late,
            "allow_resubmission": self.allow_resubmission,
            "reference_name": self.reference_name,
            "submission": latest.public_dict() if latest else None,
        }


class Submission(db.Model):
    __tablename__ = "submissions"
    __table_args__ = (
        db.UniqueConstraint("assignment_id", "student_id", "attempt", name="uq_submission_attempt"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    attempt = db.Column(db.Integer, nullable=False, default=1)
    original_name = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(80), nullable=False, unique=True)
    mime_type = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_late = db.Column(db.Boolean, nullable=False, default=False)

    assignment = db.relationship("Assignment")
    student = db.relationship("User", foreign_keys=[student_id])
    evaluation = db.relationship("Evaluation", uselist=False, back_populates="submission")

    def public_dict(self):
        evaluation = self.evaluation
        published = evaluation is not None and evaluation.published_at is not None
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "assignment": self.assignment.title,
            "student_id": self.student_id,
            "student": self.student.full_name,
            "login_id": self.student.login_id,
            "attempt": self.attempt,
            "file_name": self.original_name,
            "size": self.size,
            "max_marks": self.assignment.max_marks,
            "submitted_at": self.submitted_at.isoformat() + "Z",
            "is_late": self.is_late,
            "status": "Evaluated" if published else "Submitted",
            "evaluation": evaluation.public_dict() if published else None,
        }


class Evaluation(db.Model):
    __tablename__ = "evaluations"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), unique=True, nullable=False)
    evaluator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    marks = db.Column(db.Float, nullable=False)
    feedback = db.Column(db.Text, nullable=False, default="")
    published_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    submission = db.relationship("Submission", back_populates="evaluation")
    evaluator = db.relationship("User", foreign_keys=[evaluator_id])

    def public_dict(self):
        return {
            "marks": self.marks,
            "feedback": self.feedback,
            "published": self.published_at is not None,
            "published_at": self.published_at.isoformat() + "Z" if self.published_at else None,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(400), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime)

    def public_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "message": self.message,
            "created_at": self.created_at.isoformat() + "Z",
            "read": self.read_at is not None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    actor = db.relationship("User")


def latest_submission(assignment_id, student_id):
    return (
        Submission.query.filter_by(assignment_id=assignment_id, student_id=student_id)
        .order_by(Submission.attempt.desc())
        .first()
    )
