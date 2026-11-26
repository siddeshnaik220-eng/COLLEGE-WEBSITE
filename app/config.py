import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("AMS_SECRET_KEY", "local-demo-key-change-before-deployment")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "AMS_DATABASE_URL", f"sqlite:///{ROOT / 'instance' / 'ams.sqlite3'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get("AMS_MAX_UPLOAD_MB", "20")) * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get("AMS_UPLOAD_FOLDER", str(ROOT / "private_uploads"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("AMS_COOKIE_SECURE", "0") == "1"
