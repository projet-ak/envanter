"""Kimlik doğrulama ve rol tabanlı erişim testleri."""


def test_unauthenticated_blocked(anon_client):
    assert anon_client.get("/assets").status_code == 401
    assert anon_client.post("/categories", json={"name": "X"}).status_code == 401
    assert anon_client.post("/search", json={"q": "x"}).status_code == 401


def test_login_success_and_failure(anon_client):
    r = anon_client.post("/auth/login", json={"username": "admin", "password": "admin-pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "admin"
    assert body["access_token"]

    bad = anon_client.post("/auth/login", json={"username": "admin", "password": "yanlis"})
    assert bad.status_code == 401


def test_login_then_use_token(anon_client):
    tok = anon_client.post(
        "/auth/login", json={"username": "admin", "password": "admin-pass"}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert anon_client.get("/assets", headers=h).status_code == 200
    assert anon_client.get("/auth/me", headers=h).json()["username"] == "admin"


def test_viewer_can_read_not_write(viewer_client):
    # okuma serbest
    assert viewer_client.get("/assets").status_code == 200
    assert viewer_client.post("/search", json={"q": "x"}).status_code == 200
    # yazma yasak (403)
    assert viewer_client.post("/categories", json={"name": "X"}).status_code == 403
    assert viewer_client.post("/assets", json={"asset_tag": "NO"}).status_code == 403


def test_admin_can_write(client):
    assert client.post("/categories", json={"name": "Laptop"}).status_code == 201
    assert client.post("/assets", json={"asset_tag": "OK-1"}).status_code == 201


def test_invalid_token_rejected(anon_client):
    h = {"Authorization": "Bearer not-a-real-token"}
    assert anon_client.get("/assets", headers=h).status_code == 401


# --------------------------------------------------------------------------- #
# Hesap yönetim betiği (parola sıfırlama)
# --------------------------------------------------------------------------- #
def _hy():
    import importlib.util
    from pathlib import Path

    yol = Path(__file__).resolve().parent.parent / "scripts" / "hesap-yonet.py"
    spec = importlib.util.spec_from_file_location("hesap_yonet", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_uretilen_parola_gucludur():
    hy = _hy()
    p = hy.parola_uret()
    assert len(p) == 14
    assert any(c.islower() for c in p) and any(c.isupper() for c in p)
    assert any(c.isdigit() for c in p) and any(c in hy.SIMGE for c in p)
    # Karışan karakterler havuzda yok
    assert not set("0O1lI") & set(p)
    assert hy.parola_uret() != hy.parola_uret()      # rastgele


def test_hesap_listesi_yalniz_giris_yapabilenler(db_session):
    from app import models
    from app.auth import hash_password

    hy = _hy()
    db_session.add(models.User(first_name="Girişsiz", last_name="Personel"))
    db_session.add(models.User(first_name="Girişli", username="girisli",
                               password_hash=hash_password("x" * 10)))
    db_session.commit()

    adlar = {k.username for k in hy.hesaplari_listele(db_session)}
    assert "girisli" in adlar and None not in adlar
