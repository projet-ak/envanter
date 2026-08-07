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
    """Excel'deki 'Kullanılan Birim' (U023) lokasyonun proje kodudur."""
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

    lok = next(x for x in client.get("/locations").json() if x["name"] == "ŞANTİYE")
    assert lok["proje_kodu"] == "U023"


def test_mevcut_proje_kodu_ezilmez(client):
    """Elle girilen proje kodu içe aktarımda değiştirilmemeli."""
    client.post("/locations", json={"name": "ŞANTİYE", "proje_kodu": "ELLE-GIRILDI"})
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

    lok = next(x for x in client.get("/locations").json() if x["name"] == "ŞANTİYE")
    assert lok["proje_kodu"] == "ELLE-GIRILDI"


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
