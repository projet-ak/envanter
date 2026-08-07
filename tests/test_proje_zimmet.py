"""Lokasyon proje kodu ve zimmet atama akışı testleri."""

import io

import openpyxl

from app.excel import sema


# --------------------------------------------------------------------------- #
# Lokasyon proje kodu
# --------------------------------------------------------------------------- #
def test_lokasyona_proje_kodu_eklenir(client):
    r = client.post("/locations", json={"name": "Şantiye A", "proje_kodu": "U023",
                                        "city": "İstanbul"})
    assert r.status_code == 201
    assert r.json()["proje_kodu"] == "U023"


def test_proje_kodu_guncellenir(client):
    loc = client.post("/locations", json={"name": "Şantiye B"}).json()
    assert loc["proje_kodu"] is None
    r = client.put(f"/locations/{loc['id']}", json={"proje_kodu": "U026"})
    assert r.status_code == 200
    assert r.json()["proje_kodu"] == "U026"
    assert r.json()["name"] == "Şantiye B"      # diğer alanlar korunmalı


def test_excel_kullanilan_birim_proje_koduna_yazilir(client):
    """'Kullanılan Birim' (U023) hem şantiye adına hem proje koduna yansır.

    Ayrım kuralları ayrıntılı olarak tests/test_santiye.py'de sınanır.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(sema.STANDART_SUTUNLAR)
    satir = {"Cihaz NO": "PK-1", "Serial": "PKS1", "Bulunduğu Yer": "ŞANTİYE",
             "Kullanılan Birim": "U023", "Cihaz Tipi": "Monitör"}
    ws.append([satir.get(b) for b in sema.STANDART_SUTUNLAR])
    tampon = io.BytesIO()
    wb.save(tampon)

    CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    on = client.post("/excel/oku",
                     files={"file": ("t.xlsx", io.BytesIO(tampon.getvalue()), CT)})
    client.post("/excel/aktar", json={"satirlar": on.json()["satirlar"]})

    lok = next(x for x in client.get("/locations").json()
               if x["name"] == "ŞANTİYE U023")
    assert lok["proje_kodu"] == "U023"


def test_mevcut_proje_kodu_ezilmez(client):
    """Elle girilen proje kodu içe aktarımda değiştirilmemeli."""
    client.post("/locations", json={"name": "ŞANTİYE U099",
                                    "proje_kodu": "ELLE-GIRILDI"})
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(sema.STANDART_SUTUNLAR)
    satir = {"Cihaz NO": "PK-2", "Serial": "PKS2", "Bulunduğu Yer": "ŞANTİYE",
             "Kullanılan Birim": "U099"}
    ws.append([satir.get(b) for b in sema.STANDART_SUTUNLAR])
    tampon = io.BytesIO()
    wb.save(tampon)

    CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    on = client.post("/excel/oku",
                     files={"file": ("t.xlsx", io.BytesIO(tampon.getvalue()), CT)})
    client.post("/excel/aktar", json={"satirlar": on.json()["satirlar"]})

    # Satır bu lokasyona düşer ("ŞANTİYE" + "U099"), ama kodu ezilmez
    lok = next(x for x in client.get("/locations").json()
               if x["name"] == "ŞANTİYE U099")
    assert lok["proje_kodu"] == "ELLE-GIRILDI"
    assert client.get("/assets", params={"q": "PK-2"}).json()[0]["location_id"] \
        == lok["id"]


# --------------------------------------------------------------------------- #
# Zimmet atama akışı
# --------------------------------------------------------------------------- #
def test_yeni_personele_zimmet_atama(client):
    """Personel eklendikten sonra doğrudan cihaz zimmetlenebilmeli."""
    kisi = client.post("/users", json={"first_name": "Zeynep",
                                       "last_name": "Şahinoğlu",
                                       "employee_num": "P-999"}).json()
    a = client.post("/assets", json={"asset_tag": "Z-1", "name": "Laptop"}).json()

    # Boştaki cihazlar arasında görünmeli (zimmet panelinin kullandığı sorgu)
    bosta = client.get("/assets", params={"assigned": "false", "q": "Z-1"}).json()
    assert len(bosta) == 1

    r = client.post(f"/assets/{a['id']}/checkout",
                    json={"assigned_type": "user", "assigned_id": kisi["id"]})
    assert r.status_code == 200

    d = client.get(f"/detay/user/{kisi['id']}").json()
    assert d["cihaz_sayisi"] == 1
    assert d["cihazlar"][0]["asset_tag"] == "Z-1"

    # Artık boştakiler listesinde olmamalı
    assert client.get("/assets", params={"assigned": "false", "q": "Z-1"}).json() == []


def test_zimmet_iade_alinir(client):
    kisi = client.post("/users", json={"first_name": "İade", "last_name": "Test"}).json()
    a = client.post("/assets", json={"asset_tag": "I-1"}).json()
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})
    assert client.get(f"/detay/user/{kisi['id']}").json()["cihaz_sayisi"] == 1

    r = client.post(f"/assets/{a['id']}/checkin", json={})
    assert r.status_code == 200
    assert client.get(f"/detay/user/{kisi['id']}").json()["cihaz_sayisi"] == 0


def test_bosta_arama_zimmetliyi_getirmez(client):
    """Zimmet panelinde yalnızca boştaki cihazlar çıkmalı."""
    kisi = client.post("/users", json={"first_name": "A", "last_name": "B"}).json()
    a1 = client.post("/assets", json={"asset_tag": "BOS-1"}).json()
    a2 = client.post("/assets", json={"asset_tag": "DOLU-1"}).json()
    client.post(f"/assets/{a2['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})

    bosta = {x["asset_tag"] for x in
             client.get("/assets", params={"assigned": "false"}).json()}
    assert "BOS-1" in bosta and "DOLU-1" not in bosta


def test_personel_ekleme_kimligi_dondurur(client):
    """Popup akışı, eklenen kişinin id'siyle detay sayfasını açar."""
    r = client.post("/users", json={"first_name": "Yeni", "last_name": "Kişi"})
    assert r.status_code == 201
    kisi_id = r.json()["id"]
    assert client.get(f"/detay/user/{kisi_id}").json()["kisi"]["ad"] == "Yeni Kişi"


# --------------------------------------------------------------------------- #
# Proje koduna göre filtreleme
# --------------------------------------------------------------------------- #
def _proje_kur(client):
    u23 = client.post("/locations", json={"name": "Şantiye A",
                                          "proje_kodu": "U023"}).json()
    u26 = client.post("/locations", json={"name": "Şantiye B",
                                          "proje_kodu": "U026"}).json()
    kodsuz = client.post("/locations", json={"name": "Merkez"}).json()
    client.post("/assets", json={"asset_tag": "A-1", "location_id": u23["id"]})
    client.post("/assets", json={"asset_tag": "A-2", "location_id": u23["id"]})
    client.post("/assets", json={"asset_tag": "B-1", "location_id": u26["id"]})
    client.post("/assets", json={"asset_tag": "M-1", "location_id": kodsuz["id"]})
    client.post("/assets", json={"asset_tag": "YOK-1"})   # lokasyonsuz
    return u23, u26


def test_proje_koduna_gore_filtre(client):
    _proje_kur(client)
    r = client.get("/assets", params={"proje_kodu": "U023"}).json()
    assert {a["asset_tag"] for a in r} == {"A-1", "A-2"}

    r2 = client.get("/assets", params={"proje_kodu": "U026"}).json()
    assert {a["asset_tag"] for a in r2} == {"B-1"}


def test_proje_filtresi_sayida_da_calisir(client):
    _proje_kur(client)
    assert client.get("/assets/sayi",
                      params={"proje_kodu": "U023"}).json()["toplam"] == 2
    assert client.get("/assets/sayi").json()["toplam"] == 5


def test_proje_filtresi_diger_filtrelerle_birlesir(client):
    u23, _ = _proje_kur(client)
    kisi = client.post("/users", json={"first_name": "X", "last_name": "Y"}).json()
    a = client.get("/assets", params={"q": "A-1"}).json()[0]
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})

    r = client.get("/assets", params={"proje_kodu": "U023", "assigned": "true"}).json()
    assert {x["asset_tag"] for x in r} == {"A-1"}


def test_proje_kodlari_listesi(client):
    _proje_kur(client)
    kodlar = client.get("/assets/proje-kodlari").json()
    harita = {k["proje_kodu"]: k["cihaz_sayisi"] for k in kodlar}
    assert harita == {"U023": 2, "U026": 1}     # kodsuz lokasyon listelenmez


def test_kodsuz_lokasyon_proje_listesinde_yok(client):
    client.post("/locations", json={"name": "Kodsuz Yer"})
    client.post("/locations", json={"name": "Boş Kodlu", "proje_kodu": ""})
    kodlar = client.get("/assets/proje-kodlari").json()
    assert kodlar == []


def test_proje_filtresi_viewer_icin_de_calisir(viewer_client):
    assert viewer_client.get("/assets", params={"proje_kodu": "U023"}).status_code == 200
    assert viewer_client.get("/assets/proje-kodlari").status_code == 200
