"""Test fixtures — izole veritabanı + kimlik doğrulamalı istemciler.

Varsayılan olarak geçici SQLite kullanılır (hızlı, kurulum gerektirmez).
Üretimdeki PostgreSQL'e özgü hataları (ör. ENUM tipleri) yakalamak için
testleri gerçek PostgreSQL'de de koşturabilirsin:

    TEST_DATABASE_URL=postgresql+psycopg2://kullanici:parola@localhost/testdb \\
    pytest
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.seed import seed_defaults

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def db_session_factory(tmp_path):
    if TEST_DATABASE_URL:
        # Her test kendi şemasında çalışsın (izolasyon + paralel koşuma uygun)
        engine = create_engine(TEST_DATABASE_URL)
        sema = f"t_{uuid.uuid4().hex[:12]}"
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{sema}"'))
        engine.dispose()
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={sema}"},
        )
    else:
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

    yield Session

    # PostgreSQL'de test şemasını temizle
    if TEST_DATABASE_URL:
        engine.dispose()
        temiz = create_engine(TEST_DATABASE_URL)
        with temiz.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{sema}" CASCADE'))
        temiz.dispose()


@pytest.fixture
def db_session(db_session_factory):
    """HTTP katmanı olmadan servis kodunu sınamak için doğrudan oturum."""
    db = db_session_factory()
    try:
        yield db
    finally:
        db.close()


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
