"""Test fixtures — her test için izole, geçici sqlite veritabanı."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.seed import seed_defaults


@pytest.fixture
def db_session_factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        seed_defaults(db)
    return Session


@pytest.fixture
def client(db_session_factory):
    def override():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    # TestClient'ı context manager OLMADAN kullanıyoruz; böylece uygulamanın
    # lifespan'i (ve varsayılan ./envanter.db oluşturma) tetiklenmez.
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
