"""Veritabanı bağlantısı ve oturum yönetimi."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args: dict = {}
engine_kwargs: dict = {}

if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.database_url.startswith("mysql"):
    # MySQL/MariaDB: Türkçe karakterler ve emoji için utf8mb4 şart.
    connect_args = {"charset": "utf8mb4"}
    # MySQL boştaki bağlantıları kapatır (wait_timeout, varsayılan 8 saat);
    # bağlantıları erken geri dönüştürerek "server has gone away" hatasını önle.
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    **engine_kwargs,
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
