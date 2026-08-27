"""Kimlik doğrulama ve rol tabanlı erişim testleri."""

import pathlib


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


# --------------------------------------------------------------------------- #
# Kaba kuvvet koruması: 3 hatalı denemeden sonra 15 dk kilit
# --------------------------------------------------------------------------- #
def _giris(client, parola: str, kullanici: str = "admin"):
    return client.post("/auth/login",
                       json={"username": kullanici, "password": parola})


def test_ucuncu_hatali_denemede_kilit(anon_client):
    """İlk iki hata 401; üçüncüde hesap kilitlenir ve 429 döner."""
    assert _giris(anon_client, "yanlis1").status_code == 401
    assert _giris(anon_client, "yanlis2").status_code == 401
    r = _giris(anon_client, "yanlis3")
    assert r.status_code == 429
    assert "kilitlendi" in r.json()["detail"]
    # Kalan süre saniye cinsinden başlıkta: sayaç ekranda geri sayabilsin
    kalan = int(r.headers["Retry-After"])
    assert 14 * 60 < kalan <= 15 * 60


def test_kilitliyken_dogru_parola_da_kabul_edilmez(anon_client):
    for _ in range(3):
        _giris(anon_client, "yanlis")
    r = _giris(anon_client, "admin-pass")
    assert r.status_code == 429


def test_basarili_giris_sayaci_sifirlar(anon_client):
    """İki hatadan sonra doğru parola girilirse sayaç sıfırlanır."""
    _giris(anon_client, "yanlis")
    _giris(anon_client, "yanlis")
    assert _giris(anon_client, "admin-pass").status_code == 200
    # Sayaç sıfırlandığı için yeniden üç hakkı var
    assert _giris(anon_client, "yanlis").status_code == 401
    assert _giris(anon_client, "yanlis").status_code == 401
    assert _giris(anon_client, "admin-pass").status_code == 200


def test_401_mesaji_kalan_hak_sizdirmaz(anon_client):
    """Hatalı deneme mesajı geneldir — hesabın varlığını ele vermez."""
    var = _giris(anon_client, "yanlis").json()["detail"]
    yok = _giris(anon_client, "yanlis", "boyle-biri-yok").json()["detail"]
    assert var == yok
    assert "3 hatalı denemeden sonra" in var and "15 dakika" in var


def test_kilit_suresi_dolunca_kendiliginden_acilir(anon_client, db_session):
    import datetime as dt

    from app import models

    for _ in range(3):
        _giris(anon_client, "yanlis")
    assert _giris(anon_client, "admin-pass").status_code == 429

    kisi = db_session.query(models.User).filter_by(username="admin").one()
    kisi.kilit_bitis = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    db_session.commit()

    assert _giris(anon_client, "admin-pass").status_code == 200


def test_parola_degistirmek_kilidi_kaldirir(anon_client, client, db_session):
    import datetime as dt

    from app import models

    kisi = db_session.query(models.User).filter_by(username="admin").one()
    kisi.kilit_bitis = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)
    kisi.basarisiz_giris = 3
    db_session.commit()
    assert _giris(anon_client, "admin-pass").status_code == 429

    # Oturumu açık olan kullanıcı parolasını değiştirirse kilit kalkar
    r = client.post("/auth/parola", json={"mevcut_parola": "admin-pass",
                                          "yeni_parola": "YeniGizli.2026"})
    assert r.status_code == 204
    assert _giris(anon_client, "YeniGizli.2026").status_code == 200


def test_yonetici_kilidi_acabilir(client, db_session):
    import datetime as dt

    from app import models

    kisi = db_session.query(models.User).filter_by(username="admin").one()
    kisi.kilit_bitis = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)
    kisi.basarisiz_giris = 2
    db_session.commit()

    hesap = next(h for h in client.get("/users/hesaplar").json()
                 if h["username"] == "admin")
    assert hesap["kilitli"] is True and hesap["kilit_kalan_dk"] == 15

    r = client.put(f"/users/{kisi.id}/hesap", json={"kilidi_ac": True})
    assert r.status_code == 200
    assert r.json()["kilitli"] is False
    db_session.expire_all()
    assert kisi.kilit_bitis is None and kisi.basarisiz_giris == 0


def test_yeni_parola_atamak_kilidi_kaldirir(client, db_session):
    import datetime as dt

    from app import models

    kisi = models.User(first_name="Kilitli", last_name="Kişi",
                       username="kilitli", password_hash="x",
                       basarisiz_giris=2,
                       kilit_bitis=dt.datetime.now(dt.timezone.utc)
                       + dt.timedelta(minutes=15))
    db_session.add(kisi)
    db_session.commit()

    r = client.put(f"/users/{kisi.id}/hesap",
                   json={"yeni_parola": "BaskaGizli.2026"})
    assert r.status_code == 200 and r.json()["kilitli"] is False


def test_betik_kilit_durumunu_gosterir(db_session):
    """Hesap yönetim betiği kilitli hesabı ayırt edebilmeli."""
    import datetime as dt

    from app import models
    from app.auth import kilit_kalan_saniye

    hy = _hy()
    kisi = models.User(first_name="Kilitli", username="kilitli2",
                       password_hash="x", basarisiz_giris=3,
                       kilit_bitis=dt.datetime.now(dt.timezone.utc)
                       + dt.timedelta(minutes=15))
    db_session.add(kisi)
    db_session.commit()

    listede = {k.username: kilit_kalan_saniye(k)
               for k in hy.hesaplari_listele(db_session)}
    assert listede["kilitli2"] > 0

    # --kilidi-ac seçeneği betikte tanımlı
    kaynak = pathlib.Path(hy.__file__).read_text()
    assert "--kilidi-ac" in kaynak
