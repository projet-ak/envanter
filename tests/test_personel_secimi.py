"""Zimmet verirken personel seçme.

Arayüz eskiden kullanıcı kimliğini `prompt()` ile soruyordu — kimse kimlik
ezberleyemez. Artık kişi ada göre aranıp seçiliyor; bu uç onu besler.
"""

import pytest


@pytest.fixture
def veri(client):
    cok = client.post("/users", json={
        "first_name": "FATMA NUR", "last_name": "ERTEKİN",
        "employee_num": "1031199", "department": "Bilgi İşlem"}).json()
    az = client.post("/users", json={
        "first_name": "Süleyman", "last_name": "Ateşoğlu",
        "employee_num": "2044", "sube": "Merkez"}).json()
    bos = client.post("/users", json={"first_name": "Cihazsız",
                                      "last_name": "Kişi"}).json()
    for i in range(3):
        a = client.post("/assets", json={"asset_tag": f"C-{i}"}).json()
        client.post(f"/assets/{a['id']}/checkout",
                    json={"assigned_type": "user", "assigned_id": cok["id"]})
    a = client.post("/assets", json={"asset_tag": "T-1"}).json()
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": az["id"]})
    return {"cok": cok, "az": az, "bos": bos}


def _adlar(client, q=""):
    return [k["ad"] for k in client.get("/users/ara", params={"q": q}).json()]


# --------------------------------------------------------------------------- #
# Arama
# --------------------------------------------------------------------------- #
def test_ada_gore_bulunur(client, veri):
    assert _adlar(client, "fatma") == ["FATMA NUR ERTEKİN"]


def test_turkce_harf_takilmaz(client, veri):
    """'ertekin' -> ERTEKİN, 'atesoglu' -> Ateşoğlu."""
    assert _adlar(client, "ertekin") == ["FATMA NUR ERTEKİN"]
    assert _adlar(client, "atesoglu") == ["Süleyman Ateşoğlu"]


def test_sicil_departman_sube_ile_bulunur(client, veri):
    assert _adlar(client, "1031199") == ["FATMA NUR ERTEKİN"]
    assert _adlar(client, "bilgi işlem") == ["FATMA NUR ERTEKİN"]
    assert _adlar(client, "merkez") == ["Süleyman Ateşoğlu"]


def test_bos_terimde_cok_cihazli_once_gelir(client, veri):
    """Kutu açılır açılmaz seçilebilir isimler görünsün."""
    adlar = _adlar(client)
    assert adlar[0] == "FATMA NUR ERTEKİN"      # 3 cihaz
    assert adlar[1] == "Süleyman Ateşoğlu"      # 1 cihaz
    assert "Cihazsız Kişi" in adlar             # cihazı olmayan da seçilebilmeli


def test_cihaz_sayisi_dogru(client, veri):
    kayit = {k["ad"]: k["cihaz_sayisi"]
             for k in client.get("/users/ara").json()}
    assert kayit["FATMA NUR ERTEKİN"] == 3
    assert kayit["Süleyman Ateşoğlu"] == 1
    assert kayit["Cihazsız Kişi"] == 0


def test_pasif_personel_listelenmez(client, veri):
    client.put(f"/users/{veri['bos']['id']}", json={"active": False})
    assert "Cihazsız Kişi" not in _adlar(client)


def test_limit_uygulanir(client, veri):
    for i in range(30):
        client.post("/users", json={"first_name": f"Kişi{i}", "last_name": "Test"})
    assert len(client.get("/users/ara", params={"limit": 5}).json()) == 5


def test_eslesmeyen_terim_bos_liste(client, veri):
    assert client.get("/users/ara", params={"q": "zzzyok"}).json() == []


# --------------------------------------------------------------------------- #
# Yol sırası — /users/ara, /users/{id} tarafından yutulmamalı
# --------------------------------------------------------------------------- #
def test_ara_yolu_kimlik_sanilmaz(client, veri):
    r = client.get("/users/ara")
    assert r.status_code == 200, "'/users/ara' kimlik olarak yorumlanıyor (422?)"
    assert isinstance(r.json(), list)


def test_kimlikle_erisim_hala_calisiyor(client, veri):
    r = client.get(f"/users/{veri['cok']['id']}")
    assert r.status_code == 200
    assert r.json()["first_name"] == "FATMA NUR"


# --------------------------------------------------------------------------- #
# Yetki
# --------------------------------------------------------------------------- #
def test_viewer_arayabilir(viewer_client):
    assert viewer_client.get("/users/ara").status_code == 200


def test_giris_sart(anon_client):
    assert anon_client.get("/users/ara").status_code == 401


# --------------------------------------------------------------------------- #
# Seçimden sonra zimmet
# --------------------------------------------------------------------------- #
def test_secilen_kisiye_zimmetlenir(client, veri):
    a = client.post("/assets", json={"asset_tag": "YENI-1"}).json()
    secim = client.get("/users/ara", params={"q": "atesoglu"}).json()[0]

    r = client.post(f"/assets/{a['id']}/checkout",
                    json={"assigned_type": "user", "assigned_id": secim["id"]})
    assert r.status_code == 200
    assert client.get(f"/detay/user/{secim['id']}").json()["cihaz_sayisi"] == 2


def test_lokasyona_zimmetlenir(client, veri):
    """Kişi yerine yere zimmetleme (depo, şantiye) de mümkün olmalı."""
    lok = client.post("/locations", json={"name": "Merkez Depo"}).json()
    a = client.post("/assets", json={"asset_tag": "YENI-2"}).json()

    r = client.post(f"/assets/{a['id']}/checkout",
                    json={"assigned_type": "location", "assigned_id": lok["id"]})
    assert r.status_code == 200
    assert r.json()["assigned_type"] == "location"
    assert client.get(f"/detay/asset/{a['id']}").json()["zimmet"]["lokasyon"] \
        == "Merkez Depo"


def test_yeni_eklenen_personel_hemen_bulunur(client):
    """Pencereden 'yeni personel' eklenince aramada anında çıkmalı."""
    client.post("/users", json={"first_name": "Yepyeni", "last_name": "Çalışan"})
    assert _adlar(client, "calisan") == ["Yepyeni Çalışan"]
