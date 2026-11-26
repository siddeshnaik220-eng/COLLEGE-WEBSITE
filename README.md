<<<<<<< HEAD
# BMSIT Assignment Management System

A local full-stack assignment workflow demo based on the provided SRS and Software Design Document. It uses Flask REST APIs, Flask-SQLAlchemy, SQLite, private local file storage, and a responsive HTML/CSS/JavaScript interface.

## Run on Windows

From the AMS folder in PowerShell:

```powershell
.\myenv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The first run creates `instance\ams.sqlite3`, private file storage under `private_uploads\`, and sample CSE accounts.

| Role | Login ID | Password |
| --- | --- | --- |
| Administrator | `admin` | `Demo123!` |
| Professor | `faculty001` | `Demo123!` |
| Student | `1BM23CS001` | `Demo123!` |
| Additional student (privacy tests) | `1BM23CS002` | `Demo123!` |

The sample professor is mapped to Software Engineering (CS501), Semester 5. Use the administrator's Academic setup page to add academic records and map professors to subjects.

## Demonstration workflow

1. Sign in as `faculty001`, create and publish an assignment, set a future deadline and choose whether late work or resubmissions are allowed.
2. Sign in as `1BM23CS001`, open Assignments and upload a PDF or DOCX.
3. Sign back in as `faculty001`, open the assignment submissions, download the private file and publish marks with written feedback.
4. Sign in as the student to see the evaluation and submission history. Sign in as `admin` to manage users, academic records and CSV reports.

## Implementation notes

- API prefix: `/api/v1`; success and error responses use a consistent JSON envelope.
- The app enforces session authentication, CSRF tokens, role checks and academic-group visibility on the backend.
- Uploads are limited to PDF/DOCX, content-checked and stored outside `static`; downloads are authorization-checked.
- Resubmissions are preserved as separate attempts. SQLite and the local filesystem are for demonstration; configure PostgreSQL, HTTPS, secure cookies, a secret manager, backups and private object storage before production.
- Notifications are in-app. Email delivery and scheduled deadline reminders need the institution's SMTP/provider configuration. Password-reset requests direct users to an administrator in this demo.
- Seed accounts and their password are for local demonstration only. Set `AMS_SECRET_KEY` and disable/replace demo seeding for a real deployment.

## Tests

```powershell
python -m unittest discover -s tests -v
```
=======
# COLLEGE-WEBSITE
CREATING MY  COLLEGE WEBSITE
>>>>>>> 9c9659f522840f5678f9d4914c5a358cbb46566b
