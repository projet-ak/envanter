"""Alt klasörde yayın (root_path, örn. /envanet) testleri."""

from fastapi.testclient import TestClient


def test_root_redirects_to_ui(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/ui/"


def test_root_redirect_respects_root_path(_app_db):
    """Alt klasörde çalışırken yönlendirme /envanet/ui/ olmalı."""
    from app.main import app

    with TestClient(app, root_path="/envanet") as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/envanet/ui/"


def test_openapi_served_under_root_path(_app_db):
    """OpenAPI şeması alt klasör bilgisiyle üretilmeli (Swagger için)."""
    from app.main import app

    with TestClient(app, root_path="/envanet") as c:
        schema = c.get("/openapi.json").json()
        servers = schema.get("servers", [])
        assert any(s.get("url", "").rstrip("/") == "/envanet" for s in servers), servers


def test_ui_uses_relative_base():
    """Arayüz, API adreslerini bulunduğu yola göre türetmeli."""
    html = (
        __import__("pathlib").Path("app/static/index.html").read_text(encoding="utf-8")
    )
    # Taban yol türetimi mevcut
    assert "const BASE = window.location.pathname.replace" in html
    assert "const url = (path) => BASE + path;" in html
    # Mutlak yol ile doğrudan fetch kalmamalı
    assert "fetch('/" not in html, "Arayüzde mutlak yollu fetch çağrısı kalmış"
