"""Veritabanı bağlantısı ve oturum yönetimi."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Tüm ORM modellerinin türediği temel sınıf."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI bağımlılığı — istek başına bir DB oturumu sağlar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
