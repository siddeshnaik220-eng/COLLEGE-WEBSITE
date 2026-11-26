import io
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Department, Semester, Subject


class AssignmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "UPLOAD_FOLDER": str(Path(self.temporary.name) / "uploads"),
                "SEED_DEMO": True,
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            self.department = Department.query.filter_by(code="CSE").one()
            self.semester = Semester.query.filter_by(department_id=self.department.id).one()
            self.subject = Subject.query.filter_by(code="CS501").one()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temporary.cleanup()

    def sign_in(self, login_id):
        csrf = self.client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        response = self.client.post(
            "/api/v1/auth/login",
            json={"login_id": login_id, "password": "Demo123!"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.csrf = response.get_json()["data"]["csrf_token"]
        return self.csrf

    def post(self, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self.csrf
        return self.client.post(path, headers=headers, **kwargs)

    def test_homepage_and_health_endpoint(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'data-max-upload-mb="20"', page.data)
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["data"]["status"], "ok")

    def create_published_assignment(self):
        self.sign_in("faculty001")
        due_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        response = self.post(
            "/api/v1/professor/assignments",
            json={
                "title": "Design a Library API",
                "description": "Submit your implementation and a short explanation.",
                "department_id": self.department.id,
                "semester_id": self.semester.id,
                "subject_id": self.subject.id,
                "due_at": due_at,
                "max_marks": 20,
                "status": "Published",
                "allow_late": True,
                "allow_resubmission": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["data"]["id"]

    def test_student_cannot_use_professor_api_and_csrf_is_required(self):
        response = self.client.get("/api/v1/professor/dashboard")
        self.assertEqual(response.status_code, 401)
        csrf = self.client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        login = self.client.post(
            "/api/v1/auth/login",
            json={"login_id": "1BM23CS001", "password": "Demo123!"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        forbidden = self.client.get("/api/v1/professor/dashboard")
        self.assertEqual(forbidden.status_code, 403)
        denied = self.client.post("/api/v1/auth/logout", json={})
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(denied.get_json()["error"]["code"], "CSRF_FAILED")

    def test_logout_refreshes_csrf_for_the_next_sign_in(self):
        self.sign_in("admin")
        logged_out = self.post("/api/v1/auth/logout", json={})
        self.assertEqual(logged_out.status_code, 200)
        new_csrf = self.client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        response = self.client.post(
            "/api/v1/auth/login",
            json={"login_id": "faculty001", "password": "Demo123!"},
            headers={"X-CSRF-Token": new_csrf},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_student_only_sees_assignments_for_their_semester(self):
        self.create_published_assignment()
        with self.app.app_context():
            other_semester = Semester(
                department_id=self.department.id,
                number=6,
                academic_year="2025-2026",
            )
            db.session.add(other_semester)
            db.session.flush()
            from app.models import User

            student = User(
                login_id="1BM23CS006",
                email="student6@bmsit.edu.in",
                role="student",
                full_name="Semester Six Student",
                department_id=self.department.id,
                semester_id=other_semester.id,
            )
            student.set_password("Demo123!")
            db.session.add(student)
            db.session.commit()
        other_client = self.app.test_client()
        csrf = other_client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        login = other_client.post(
            "/api/v1/auth/login",
            json={"login_id": "1BM23CS006", "password": "Demo123!"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        assignments = other_client.get("/api/v1/student/assignments").get_json()["data"]
        self.assertEqual(assignments, [])

    def test_professor_can_edit_and_close_their_assignment(self):
        assignment_id = self.create_published_assignment()
        response = self.client.put(
            f"/api/v1/professor/assignments/{assignment_id}",
            json={"title": "Updated assignment", "status": "Closed"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["data"]["title"], "Updated assignment")
        self.assertEqual(response.get_json()["data"]["status"], "Closed")

    def test_publish_submit_evaluate_and_protect_private_file(self):
        assignment_id = self.create_published_assignment()
        self.sign_in("1BM23CS001")
        response = self.post(
            f"/api/v1/student/assignments/{assignment_id}/submissions",
            data={"file": (io.BytesIO(b"%PDF-1.4\nDemo assignment"), "work.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        submission_id = response.get_json()["data"]["id"]
        self.assertEqual(response.get_json()["data"]["attempt"], 1)

        resubmission = self.post(
            f"/api/v1/student/assignments/{assignment_id}/submissions",
            data={"file": (io.BytesIO(b"%PDF-1.4\nUpdated work"), "work-v2.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resubmission.status_code, 201, resubmission.get_json())
        self.assertEqual(resubmission.get_json()["data"]["attempt"], 2)

        self.sign_in("faculty001")
        latest_id = resubmission.get_json()["data"]["id"]
        invalid_marks = self.post(
            f"/api/v1/professor/submissions/{latest_id}/evaluation",
            json={"marks": 21, "feedback": "Great work", "publish": True},
        )
        self.assertEqual(invalid_marks.status_code, 400)
        result = self.post(
            f"/api/v1/professor/submissions/{latest_id}/evaluation",
            json={"marks": 18, "feedback": "Clear explanation.", "publish": True},
        )
        self.assertEqual(result.status_code, 200, result.get_json())

        self.sign_in("1BM23CS001")
        history = self.client.get("/api/v1/student/submissions").get_json()["data"]
        evaluated = next(item for item in history if item["id"] == latest_id)
        self.assertEqual(evaluated["status"], "Evaluated")
        self.assertEqual(evaluated["evaluation"]["marks"], 18)
        self.assertEqual(len(history), 2)

        other_client = self.app.test_client()
        other_csrf = other_client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        other_client.post(
            "/api/v1/auth/login",
            json={"login_id": "1BM23CS002", "password": "Demo123!"},
            headers={"X-CSRF-Token": other_csrf},
        )
        private_file = other_client.get(f"/api/v1/files/submissions/{submission_id}")
        self.assertEqual(private_file.status_code, 404)

    def test_rejects_non_pdf_and_docx_upload(self):
        assignment_id = self.create_published_assignment()
        self.sign_in("1BM23CS001")
        response = self.post(
            f"/api/v1/student/assignments/{assignment_id}/submissions",
            data={"file": (io.BytesIO(b"not a document"), "notes.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["error"]["code"], "UNSUPPORTED_FILE_TYPE")

    def test_accepts_valid_docx_upload(self):
        assignment_id = self.create_published_assignment()
        self.sign_in("1BM23CS001")
        document = io.BytesIO()
        with zipfile.ZipFile(document, "w") as archive:
            archive.writestr("word/document.xml", "<document/>")
        document.seek(0)
        response = self.post(
            f"/api/v1/student/assignments/{assignment_id}/submissions",
            data={"file": (document, "report.docx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_json())


if __name__ == "__main__":
    unittest.main()
