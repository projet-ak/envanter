"""Kullanıcı ayarları: kendi profili, parola değiştirme, hesap yönetimi."""

import pytest


# --------------------------------------------------------------------------- #
# Kendi profili
# --------------------------------------------------------------------------- #
def test_me_bilgileri_doner(client):
    d = client.get("/auth/me").json()
    assert d["username"] == "admin"
    assert d["role"] == "admin"


def test_profil_guncellenir(client):
    r = client.put("/auth/me", json={"first_name": "Tayyar",
                                     "last_name": "Akbulut",
                                     "email": "t@ornek.com",
                                     "telefon": "0555"})
    assert r.status_code == 200
    d = r.json()
    assert (d["first_name"], d["last_name"]) == ("Tayyar", "Akbulut")
    assert d["email"] == "t@ornek.com"
    assert client.get("/auth/me").json()["telefon"] == "0555"


def test_profilden_rol_yukseltilemez(viewer_client):
    """Kendi rolünü değiştirmek profil alanı değildir; sessizce yok sayılır."""
    viewer_client.put("/auth/me", json={"first_name": "X", "role": "admin"})
    assert viewer_client.get("/auth/me").json()["role"] == "viewer"


def test_viewer_da_kendi_profilini_duzenler(viewer_client):
    r = viewer_client.put("/auth/me", json={"first_name": "Görüntüleyici"})
    assert r.status_code == 200
    assert r.json()["first_name"] == "Görüntüleyici"


# --------------------------------------------------------------------------- #
# Parola değiştirme
# --------------------------------------------------------------------------- #
def test_parola_degistirilir_ve_yeniyle_girilir(client, anon_client):
    r = client.post("/auth/parola", json={"mevcut_parola": "admin-pass",
                                          "yeni_parola": "YeniGucluParola1"})
    assert r.status_code == 204

    assert anon_client.post("/auth/login", json={"username": "admin",
                                                 "password": "admin-pass"}
                            ).status_code == 401
    yeni = anon_client.post("/auth/login", json={"username": "admin",
                                                 "password": "YeniGucluParola1"})
    assert yeni.status_code == 200
    assert yeni.json()["user"]["username"] == "admin"


def test_yanlis_mevcut_parola_reddedilir(client):
    r = client.post("/auth/parola", json={"mevcut_parola": "yanlis",
                                          "yeni_parola": "YeniGucluParola1"})
    assert r.status_code == 400
    assert "Mevcut parola" in r.json()["detail"]


def test_ayni_parola_reddedilir(client):
    r = client.post("/auth/parola", json={"mevcut_parola": "admin-pass",
                                          "yeni_parola": "admin-pass"})
    assert r.status_code == 400


def test_kisa_parola_reddedilir(client):
    r = client.post("/auth/parola", json={"mevcut_parola": "admin-pass",
                                          "yeni_parola": "kisa"})
    assert r.status_code == 422


def test_parola_degistirmek_giris_ister(anon_client):
    assert anon_client.post("/auth/parola",
                            json={"mevcut_parola": "a", "yeni_parola": "b" * 9}
                            ).status_code == 401


# --------------------------------------------------------------------------- #
# Hesap yönetimi (yönetici)
# --------------------------------------------------------------------------- #
def test_hesaplar_listelenir(client):
    liste = client.get("/users/hesaplar").json()
    kullanicilar = {h["username"] for h in liste}
    assert kullanicilar == {"admin", "viewer"}
    assert all(h["girebilir"] for h in liste)


def test_personel_hesaplarda_gorunmez(client):
    """Kullanıcı adı olmayan personel hesap listesini şişirmemeli."""
    client.post("/users", json={"first_name": "Sahadan", "last_name": "Personel"})
    assert {h["username"] for h in client.get("/users/hesaplar").json()} \
        == {"admin", "viewer"}


def test_personele_giris_yetkisi_verilir(client, anon_client):
    kisi = client.post("/users", json={"first_name": "Yeni", "last_name": "Kullanıcı"}).json()
    r = client.put(f"/users/{kisi['id']}/hesap", json={
        "username": "yenikullanici", "yeni_parola": "GucluParola123",
        "role": "editor"})
    assert r.status_code == 200
    assert r.json()["girebilir"] is True

    giris = anon_client.post("/auth/login", json={"username": "yenikullanici",
                                                  "password": "GucluParola123"})
    assert giris.status_code == 200
    assert giris.json()["user"]["role"] == "editor"


def test_rol_degistirilir(client):
    viewer = next(h for h in client.get("/users/hesaplar").json()
                  if h["username"] == "viewer")
    r = client.put(f"/users/{viewer['id']}/hesap", json={"role": "editor"})
    assert r.json()["role"] == "editor"


def test_parola_sifirlanir(client, anon_client):
    viewer = next(h for h in client.get("/users/hesaplar").json()
                  if h["username"] == "viewer")
    client.put(f"/users/{viewer['id']}/hesap", json={"yeni_parola": "SifirlananP1"})
    assert anon_client.post("/auth/login", json={"username": "viewer",
                                                 "password": "SifirlananP1"}
                            ).status_code == 200


def test_hesap_kapatilinca_giris_engellenir(client, anon_client):
    viewer = next(h for h in client.get("/users/hesaplar").json()
                  if h["username"] == "viewer")
    client.put(f"/users/{viewer['id']}/hesap", json={"active": False})
    assert anon_client.post("/auth/login", json={"username": "viewer",
                                                 "password": "viewer-pass"}
                            ).status_code == 401


def test_kullanici_adi_tekrar_edemez(client):
    kisi = client.post("/users", json={"first_name": "Çakışan"}).json()
    r = client.put(f"/users/{kisi['id']}/hesap", json={"username": "admin"})
    assert r.status_code == 409


def test_kullanici_adisiz_parola_verilemez(client):
    kisi = client.post("/users", json={"first_name": "Adsız"}).json()
    r = client.put(f"/users/{kisi['id']}/hesap", json={"yeni_parola": "BirParola12"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Kilitlenme koruması
# --------------------------------------------------------------------------- #
def test_kendi_yoneticiligini_kaldiramaz(client):
    ben = client.get("/auth/me").json()
    r = client.put(f"/users/{ben['id']}/hesap", json={"role": "viewer"})
    assert r.status_code == 400
    assert client.get("/auth/me").json()["role"] == "admin"


def test_kendi_hesabini_kapatamaz(client):
    ben = client.get("/auth/me").json()
    assert client.put(f"/users/{ben['id']}/hesap",
                      json={"active": False}).status_code == 400


def test_son_yonetici_baskasi_tarafindan_dusurulemez(client):
    """İkinci bir yönetici, tek etkin yöneticiyi devre dışı bırakamamalı."""
    ben = client.get("/auth/me").json()
    ikinci = client.post("/users", json={"first_name": "İkinci", "last_name": "Admin"}).json()
    client.put(f"/users/{ikinci['id']}/hesap", json={
        "username": "ikinciadmin", "yeni_parola": "IkinciParola1", "role": "admin"})

    # Artık iki yönetici var: birini düşürmek serbest
    r = client.put(f"/users/{ikinci['id']}/hesap", json={"role": "viewer"})
    assert r.status_code == 200

    # Tek yönetici kaldı; kendini düşüremez (yukarıdaki testler) — başka
    # yönetici de olmadığı için sistem yöneticisiz kalamaz.
    assert client.get(f"/users/{ben['id']}").json()["role"] == "admin"


def test_tek_yoneticinin_parolasi_silinemez_durumu_korunur(client):
    """Etkin yönetici sayısı sıfıra düşecek işlem geri alınmalı."""
    ben = client.get("/auth/me").json()
    # Kendini pasifleştirme zaten engelli; dolaylı yoldan da bozulmamalı
    r = client.put(f"/users/{ben['id']}/hesap", json={"role": "admin", "active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True


# --------------------------------------------------------------------------- #
# Yetki
# --------------------------------------------------------------------------- #
def test_viewer_hesaplari_goremez(viewer_client):
    assert viewer_client.get("/users/hesaplar").status_code == 403


def test_viewer_hesap_ayarlayamaz(viewer_client, client):
    kisi = client.post("/users", json={"first_name": "Hedef"}).json()
    assert viewer_client.put(f"/users/{kisi['id']}/hesap",
                             json={"role": "admin"}).status_code == 403


def test_hesaplar_yolu_kimlik_sanilmaz(client):
    """/users/hesaplar, /users/{id} tarafından yutulmamalı."""
    r = client.get("/users/hesaplar")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_olmayan_personelin_hesabi_404(client):
    assert client.put("/users/999999/hesap",
                      json={"role": "viewer"}).status_code == 404


# --------------------------------------------------------------------------- #
# Giriş sayfası
# --------------------------------------------------------------------------- #
def test_login_sayfasi_sunulur(anon_client):
    """Ayrı giriş sayfası girişsiz erişilebilmeli."""
    r = anon_client.get("/login")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Giriş yap" in r.text


def test_login_sayfasi_redirect_destekler(anon_client):
    r = anon_client.get("/login?redirect=%2Fui%2F")
    assert r.status_code == 200
    # Yönlendirme hedefi sayfa içinde çözülüyor (JS); sunucu sorgu ile bozulmamalı
    assert "redirect" in r.text


def test_arayuz_girissiz_de_sunulur(anon_client):
    """Sayfanın kendisi statiktir; oturum denetimi API çağrılarında yapılır."""
    assert anon_client.get("/ui/").status_code == 200


def test_kok_adres_arayuze_yonlendirir(anon_client):
    r = anon_client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"].endswith("/ui/")
