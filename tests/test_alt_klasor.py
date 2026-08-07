"""Alt klasörde yayın (ROOT_PATH) — arayüz yolu bozulmamalı.

Nginx `/envanter` ön ekini kırpar, yani uygulamaya `/ui/` gelir. Uygulamaya
kurucu üzerinden `root_path` verilirse StaticFiles bağlaması yolu ön ekle
bekliyor ve `/ui/` 404 dönüyor. Bu testler o tuzağı kapalı tutar.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def _uygulama(monkeypatch, onek: str):
    """ROOT_PATH ayarıyla uygulamayı baştan kurar."""
    from app import config

    monkeypatch.setattr(config.settings, "root_path", onek)
    import app.main

    return importlib.reload(app.main)


@pytest.mark.parametrize("onek", ["", "/envanter", "/envanter/"])
def test_arayuz_onekten_bagimsiz_acilir(monkeypatch, onek):
    """Ön ek ayarlı olsa da uygulama kırpılmış yolu (/ui/) tanımalı."""
    ana = _uygulama(monkeypatch, onek)
    with TestClient(ana.app) as c:
        assert c.get("/ui/").status_code == 200, f"ROOT_PATH={onek!r} ile /ui/ açılmıyor"
        assert c.get("/login").status_code == 200
        assert c.get("/health").status_code == 200


def test_onek_openapi_adresine_yansir(monkeypatch):
    """Alt klasördeyken API dokümanı doğru adresi göstermeli."""
    ana = _uygulama(monkeypatch, "/envanter")
    with TestClient(ana.app) as c:
        sema = c.get("/openapi.json").json()
    assert sema.get("servers") == [{"url": "/envanter"}]


def test_onek_yokken_servers_bos(monkeypatch):
    ana = _uygulama(monkeypatch, "")
    with TestClient(ana.app) as c:
        assert "servers" not in c.get("/openapi.json").json()


def test_kurucuya_root_path_verilmemeli(monkeypatch):
    """Yönlendirmeyi bozan ayarın geri gelmediğini doğrular."""
    ana = _uygulama(monkeypatch, "/envanter")
    assert ana.app.root_path == "", (
        "FastAPI kurucusuna root_path verilmiş — StaticFiles bağlaması kırılır, "
        "ön ek için servers= kullanılmalı"
    )


@pytest.fixture(autouse=True)
def _modulu_geri_yukle():
    """Diğer testler özgün ayarlarla kurulmuş uygulamayı görsün."""
    yield
    import app.main

    importlib.reload(app.main)
