from datetime import datetime, timedelta

import jwt
import pytest

from app import create_app, db
from app.config import TestingConfig
from app.models import User


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.sqlite"
    volumes_path = tmp_path / "volumes"
    uploads_path = tmp_path / "uploads"
    backups_path = tmp_path / "backups"

    volumes_path.mkdir(parents=True, exist_ok=True)
    uploads_path.mkdir(parents=True, exist_ok=True)
    backups_path.mkdir(parents=True, exist_ok=True)

    class LocalTestingConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        JWT_SECRET_KEY = "test-jwt-secret"
        SECRET_KEY = "test-secret"
        REDIS_URL = "redis://localhost:6379/15"
        SESSION_TYPE = "filesystem"
        SESSION_FILE_DIR = str(tmp_path / "flask_session")
        VOLUMES_PATH = str(volumes_path)
        UPLOAD_FOLDER = str(uploads_path)
        BACKUP_FOLDER = str(backups_path)

    flask_app = create_app(LocalTestingConfig)

    with flask_app.app_context():
        db.create_all()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    # Keep the app context open for the whole test (yield, not return): the
    # User stays attached to a live session, so accessing user.id / attributes
    # in later app contexts doesn't raise "weakly-referenced object no longer
    # exists" (expire-on-commit would otherwise try to reload via a dead session).
    with app.app_context():
        user = User(
            username="testuser",
            email="test@example.com",
            is_active=True,
            is_admin=False,
        )
        user.set_password("StrongPass123!")
        db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        yield user


@pytest.fixture()
def auth_headers(app):
    def _build(user_id, is_admin=False, jti="test-jti"):
        payload = {
            "user_id": user_id,
            "is_admin": is_admin,
            "jti": jti,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")
        # Auth now requires a real server-side session (48h absolute wall +
        # single-device enforcement): token_required → validate_session checks
        # Redis (authoritative when present) then the user_sessions DB mirror.
        # Register the session the same way login does so the token is accepted.
        from app.routes.auth import create_session
        with app.test_request_context():
            create_session(user_id, jti)
        return {"Authorization": f"Bearer {token}"}

    return _build
