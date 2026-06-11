"""Test fixtures — izole geçici sqlite + kimlik doğrulamalı istemciler."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.seed import seed_defaults


@pytest.fixture
def db_session_factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        seed_defaults(db)
        db.add(User(username="admin", first_name="Admin",
                    password_hash=hash_password("admin-pass"), role=UserRole.admin))
        db.add(User(username="viewer", first_name="Viewer",
                    password_hash=hash_password("viewer-pass"), role=UserRole.viewer))
        db.commit()
    return Session


@pytest.fixture
def _app_db(db_session_factory):
    def override():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    # Lifespan'i tetiklememek için TestClient context manager olmadan kullanılır.
    app.dependency_overrides[get_db] = override
    yield db_session_factory
    app.dependency_overrides.clear()


def _token(session_factory, username: str) -> str:
    with session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        return create_access_token(user)


@pytest.fixture
def anon_client(_app_db):
    """Kimlik doğrulaması olmayan istemci."""
    return TestClient(app)


@pytest.fixture
def client(_app_db):
    """Admin olarak yetkili istemci (varsayılan)."""
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {_token(_app_db, 'admin')}"})
    return c


@pytest.fixture
def viewer_client(_app_db):
    """Sadece-okuma (viewer) yetkili istemci."""
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {_token(_app_db, 'viewer')}"})
    return c
