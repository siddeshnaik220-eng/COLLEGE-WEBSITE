from .extensions import db
from .models import Department, Semester, Subject, User


def seed_demo():
    if User.query.first():
        return

    department = Department(code="CSE", name="Computer Science and Engineering")
    db.session.add(department)
    db.session.flush()
    semester = Semester(department_id=department.id, number=5, academic_year="2025-2026")
    db.session.add(semester)
    db.session.flush()
    subject = Subject(
        department_id=department.id,
        semester_id=semester.id,
        code="CS501",
        name="Software Engineering",
    )
    db.session.add(subject)
    db.session.flush()

    admin = User(
        login_id="admin",
        email="admin@bmsit.edu.in",
        role="admin",
        full_name="System Administrator",
    )
    professor = User(
        login_id="faculty001",
        email="professor@bmsit.edu.in",
        role="professor",
        full_name="Dr. Ananya Rao",
        department_id=department.id,
    )
    student = User(
        login_id="1BM23CS001",
        email="student@bmsit.edu.in",
        role="student",
        full_name="Aarav Sharma",
        department_id=department.id,
        semester_id=semester.id,
    )
    another_student = User(
        login_id="1BM23CS002",
        email="student2@bmsit.edu.in",
        role="student",
        full_name="Mira Nair",
        department_id=department.id,
        semester_id=semester.id,
    )
    for user in (admin, professor, student, another_student):
        user.set_password("Demo123!")
        db.session.add(user)
    db.session.flush()
    professor.subjects.append(subject)
    db.session.commit()
