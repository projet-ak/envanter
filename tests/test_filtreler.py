"""Varlık listesi filtreleri ve güncelleme testleri."""


def _kur(client):
    laptop = client.post("/categories", json={"name": "Dizüstü Bilgisayar"}).json()
    kamera = client.post("/categories", json={"name": "IP Kamera"}).json()
    dell = client.post("/manufacturers", json={"name": "Dell"}).json()
    hik = client.post("/manufacturers", json={"name": "Hikvision"}).json()
    depo = client.post("/locations", json={"name": "Merkez Depo"}).json()
    santiye = client.post("/locations", json={"name": "ŞANTİYE"}).json()

    m_lap = client.post("/models", json={"name": "Latitude", "category_id": laptop["id"],
                                         "manufacturer_id": dell["id"]}).json()
    m_kam = client.post("/models", json={"name": "DS-2CD", "category_id": kamera["id"],
                                         "manufacturer_id": hik["id"]}).json()
    kisi = client.post("/users", json={"first_name": "Test", "last_name": "Kişi"}).json()

    a1 = client.post("/assets", json={"asset_tag": "L-1", "model_id": m_lap["id"],
                                      "location_id": depo["id"], "serial": "SL1"}).json()
    client.post("/assets", json={"asset_tag": "L-2", "model_id": m_lap["id"],
                                 "location_id": santiye["id"]})
    client.post("/assets", json={"asset_tag": "K-1", "model_id": m_kam["id"],
                                 "location_id": santiye["id"], "demirbas_no": "DMR-K1"})
    client.post(f"/assets/{a1['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})
    return {"laptop": laptop, "kamera": kamera, "dell": dell, "depo": depo,
            "santiye": santiye, "kisi": kisi, "m_lap": m_lap}


def test_kategori_filtresi(client):
    v = _kur(client)
    r = client.get("/assets", params={"category_id": v["laptop"]["id"]}).json()
    assert {a["asset_tag"] for a in r} == {"L-1", "L-2"}

    r2 = client.get("/assets", params={"category_id": v["kamera"]["id"]}).json()
    assert {a["asset_tag"] for a in r2} == {"K-1"}


def test_lokasyon_filtresi(client):
    v = _kur(client)
    r = client.get("/assets", params={"location_id": v["santiye"]["id"]}).json()
    assert {a["asset_tag"] for a in r} == {"L-2", "K-1"}


def test_kategori_ve_lokasyon_birlikte(client):
    v = _kur(client)
    r = client.get("/assets", params={"category_id": v["laptop"]["id"],
                                      "location_id": v["santiye"]["id"]}).json()
    assert {a["asset_tag"] for a in r} == {"L-2"}


def test_marka_filtresi(client):
    v = _kur(client)
    r = client.get("/assets", params={"manufacturer_id": v["dell"]["id"]}).json()
    assert {a["asset_tag"] for a in r} == {"L-1", "L-2"}


def test_kisi_filtresi(client):
    v = _kur(client)
    r = client.get("/assets", params={"user_id": v["kisi"]["id"]}).json()
    assert {a["asset_tag"] for a in r} == {"L-1"}


def test_zimmet_filtresi(client):
    _kur(client)
    zimmetli = client.get("/assets", params={"assigned": "true"}).json()
    bosta = client.get("/assets", params={"assigned": "false"}).json()
    assert {a["asset_tag"] for a in zimmetli} == {"L-1"}
    assert {a["asset_tag"] for a in bosta} == {"L-2", "K-1"}


def test_arama_demirbas_ve_ip(client):
    _kur(client)
    assert len(client.get("/assets", params={"q": "DMR-K1"}).json()) == 1
    client.post("/assets", json={"asset_tag": "IP-1", "ip_address": "10.0.0.55"})
    assert len(client.get("/assets", params={"q": "10.0.0.55"}).json()) == 1


def test_sayi_ucu_filtreye_uyar(client):
    v = _kur(client)
    assert client.get("/assets/sayi").json()["toplam"] == 3
    assert client.get("/assets/sayi",
                      params={"category_id": v["laptop"]["id"]}).json()["toplam"] == 2
    assert client.get("/assets/sayi",
                      params={"assigned": "true"}).json()["toplam"] == 1


def test_sayi_sayfalamadan_bagimsiz(client):
    """limit sonucu kısar ama toplam sayı değişmemeli."""
    _kur(client)
    liste = client.get("/assets", params={"limit": 1}).json()
    assert len(liste) == 1
    assert client.get("/assets/sayi").json()["toplam"] == 3


# --------------------------------------------------------------------------- #
# Güncelleme
# --------------------------------------------------------------------------- #
def test_cihaz_iliskileri_guncellenir(client):
    v = _kur(client)
    a = client.get("/assets", params={"q": "K-1"}).json()[0]
    r = client.put(f"/assets/{a['id']}", json={
        "model_id": v["m_lap"]["id"], "location_id": v["depo"]["id"],
        "notes": "Güncellendi",
    })
    assert r.status_code == 200
    g = r.json()
    assert g["model_id"] == v["m_lap"]["id"]
    assert g["location_id"] == v["depo"]["id"]
    assert g["notes"] == "Güncellendi"
    # Artık laptop kategorisinde görünmeli
    assert "K-1" in {x["asset_tag"] for x in
                     client.get("/assets", params={"category_id": v["laptop"]["id"]}).json()}


def test_personel_guncellenir(client):
    kisi = client.post("/users", json={"first_name": "Eski", "last_name": "Ad"}).json()
    loc = client.post("/locations", json={"name": "Yeni Yer"}).json()
    r = client.put(f"/users/{kisi['id']}", json={
        "first_name": "Yeni", "department": "BT", "sube": "Merkez",
        "location_id": loc["id"], "telefon": "05551112233",
    })
    assert r.status_code == 200
    g = r.json()
    assert g["first_name"] == "Yeni" and g["department"] == "BT"
    assert g["location_id"] == loc["id"] and g["telefon"] == "05551112233"


def test_lokasyon_guncellenir(client):
    loc = client.post("/locations", json={"name": "Depo A"}).json()
    r = client.put(f"/locations/{loc['id']}",
                   json={"name": "Depo A (yeni)", "city": "İstanbul"})
    assert r.status_code == 200
    assert r.json()["name"] == "Depo A (yeni)"
    assert r.json()["city"] == "İstanbul"


def test_viewer_guncelleyemez(viewer_client):
    assert viewer_client.put("/locations/1", json={"name": "X"}).status_code == 403
    assert viewer_client.put("/users/1", json={"first_name": "X"}).status_code == 403


def test_viewer_filtreleyebilir(viewer_client):
    assert viewer_client.get("/assets", params={"assigned": "false"}).status_code == 200
    assert viewer_client.get("/assets/sayi").status_code == 200
