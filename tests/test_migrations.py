"""Alembic göç zinciri testleri.

Bu testler özellikle PostgreSQL'e özgü hataları yakalamak için vardır
(ör. ENUM tipleri tablolardan bağımsız nesnelerdir). SQLite'ta enum yalnızca
metin olduğu için bu sınıf hatalar orada görünmez.

PostgreSQL'de koşturmak için:
    TEST_DATABASE_URL=postgresql+psycopg2://kullanici:parola@localhost/testdb pytest
"""

import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def alembic_cfg(tmp_path):
    """Boş bir veritabanına işaret eden Alembic yapılandırması."""
    if TEST_DATABASE_URL:
        # İzole bir veritabanı yerine izole şema kullan
        base = create_engine(TEST_DATABASE_URL)
        sema = f"m_{uuid.uuid4().hex[:12]}"
        with base.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{sema}"'))
        base.dispose()
        ayirici = "&" if "?" in TEST_DATABASE_URL else "?"
        url = f"{TEST_DATABASE_URL}{ayirici}options=-csearch_path%3D{sema}"
    else:
        url = f"sqlite:///{tmp_path / 'mig.db'}"
        sema = None

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    # configparser '%' karakterini değişken olarak yorumlar; kaçış gerekir.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

    yield cfg, url

    if sema:
        temiz = create_engine(TEST_DATABASE_URL)
        with temiz.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{sema}" CASCADE'))
        temiz.dispose()


def _tablolar(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {t for t in inspect(engine).get_table_names() if t != "alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_head_creates_all_tables(alembic_cfg, monkeypatch):
    cfg, url = alembic_cfg
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(cfg, "head")

    tablolar = _tablolar(url)
    beklenen = {"assets", "users", "categories", "locations", "manufacturers",
                "suppliers", "companies", "status_labels", "asset_models",
                "custom_fields", "activity_logs", "accessories", "consumables",
                "components", "licenses", "asset_files"}
    eksik = beklenen - tablolar
    assert not eksik, f"Eksik tablolar: {eksik}"


def test_full_downgrade_then_upgrade(alembic_cfg, monkeypatch):
    """Sürüm geri alma sonrası tekrar kurulum çalışmalı.

    PostgreSQL'de ENUM tipleri tablo silinince kalkmaz; temizlenmezse
    ikinci upgrade "type ... already exists" hatası verir.
    """
    cfg, url = alembic_cfg
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tablolar(url) == set(), "Geri alma sonrası tablo kalmamalı"

    # Asıl sınav: tekrar kurulum
    command.upgrade(cfg, "head")
    assert "users" in _tablolar(url)


def test_single_step_rollback(alembic_cfg, monkeypatch):
    """Tek adım geri al + ileri (hatalı sürümü geri alma senaryosu)."""
    cfg, url = alembic_cfg
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    assert "users" in _tablolar(url)


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="PostgreSQL gerektirir")
def test_enum_types_created_on_postgres(alembic_cfg, monkeypatch):
    """Rol sütununun ENUM tipi gerçekten oluşmalı (add_column ile eklenir)."""
    cfg, url = alembic_cfg
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            degerler = conn.execute(
                text("SELECT unnest(enum_range(NULL::userrole))")
            ).scalars().all()
        assert set(degerler) == {"admin", "editor", "viewer"}
    finally:
        engine.dispose()
