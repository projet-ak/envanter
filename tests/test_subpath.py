"""Alt klasörde yayın (root_path, örn. /envanter) testleri."""

from fastapi.testclient import TestClient


def test_root_redirects_to_ui(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/ui/"


def test_root_redirect_respects_root_path(_app_db):
    """Alt klasörde çalışırken yönlendirme /envanter/ui/ olmalı."""
    from app.main import app

    with TestClient(app, root_path="/envanter") as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/envanter/ui/"


def test_openapi_served_under_root_path(_app_db):
    """OpenAPI şeması alt klasör bilgisiyle üretilmeli (Swagger için)."""
    from app.main import app

    with TestClient(app, root_path="/envanter") as c:
        schema = c.get("/openapi.json").json()
        servers = schema.get("servers", [])
        assert any(s.get("url", "").rstrip("/") == "/envanter" for s in servers), servers


def test_ui_uses_relative_base():
    """Arayüz, API adreslerini bulunduğu yola göre türetmeli.

    Arayüz mantığı `uygulama.js`'de (index.html yalnızca iskelet); statik
    dosya bağlantıları da göreli olmalı ki alt klasörde (/envanter) çalışsın.
    """
    from pathlib import Path

    js = Path("app/static/uygulama.js").read_text(encoding="utf-8")
    assert "const BASE = window.location.pathname.replace" in js
    assert "const url = (path) => BASE + path;" in js
    # Mutlak yol ile doğrudan fetch kalmamalı
    assert "fetch('/" not in js, "Arayüzde mutlak yollu fetch çağrısı kalmış"

    html = Path("app/static/index.html").read_text(encoding="utf-8")
    # Uzantısız + göreli bağlantı: panellerin `.css/.js` regex blokları
    # (aaPanel) uzantı görmeyince araya giremez; ../ ile alt klasörde de
    # doğru köke çözülür. Uzantı geri gelirse aaPanel'de sayfa çıplak açılır!
    assert 'src="../betik"' in html, "betik bağlantısı uzantısız/göreli olmalı"
    assert 'href="../stil"' in html, "stil bağlantısı uzantısız/göreli olmalı"
    assert 'src="/' not in html and 'href="/' not in html.replace(
        'href="data:', ''), \
        "index.html'de mutlak yollu bağlantı alt klasörde kırılır"


def test_stil_ve_betik_uclari_dogru_mime_ile_doner(client):
    """Uzantısız uçlar doğru MIME vermek zorunda.

    Tarayıcılar text/css olmayan stil dosyasını sessizce reddeder — uç 200
    dönse bile sayfa çıplak açılırdı.
    """
    r = client.get("/stil")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert ":root" in r.text
    assert r.headers.get("cache-control") == "no-cache"

    r = client.get("/betik")
    assert r.status_code == 200
    assert ("javascript" in r.headers["content-type"])
    assert "const BASE" in r.text
    assert r.headers.get("cache-control") == "no-cache"
