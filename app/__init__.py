import hmac
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError

from .config import Config
from .extensions import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    from .routes import api

    app.register_blueprint(api, url_prefix="/api/v1")

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            max_upload_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        )

    @app.before_request
    def protect_state_changes():
        if request.path.startswith("/api/v1") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not supplied or not hmac.compare_digest(supplied, expected):
                return jsonify(
                    success=False,
                    error={"code": "CSRF_FAILED", "message": "Refresh the page and try again."},
                ), 400

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(_):
        db.session.rollback()
        return jsonify(
            success=False,
            error={"code": "CONFLICT", "message": "A record with the same unique details already exists."},
        ), 409

    @app.errorhandler(413)
    def handle_large_upload(_):
        return jsonify(
            success=False,
            error={"code": "FILE_TOO_LARGE", "message": "The uploaded file exceeds the configured size limit."},
        ), 413

    with app.app_context():
        db.create_all()
        if app.config.get("SEED_DEMO", True):
            from .seed import seed_demo

            seed_demo()

    return app
