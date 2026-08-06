"""Cihaz ve kişi detay uçlarının testleri."""


def _hazirla(client):
    cat = client.post("/categories", json={"name": "Dizüstü Bilgisayar"}).json()
    man = client.post("/manufacturers", json={"name": "ASUS"}).json()
    loc = client.post("/locations", json={"name": "ŞANTİYE"}).json()
    mdl = client.post("/models", json={"name": "X542UR", "category_id": cat["id"],
                                       "manufacturer_id": man["id"]}).json()
    kisi = client.post("/users", json={
        "first_name": "Nurettin", "last_name": "Eren", "employee_num": "P-77",
        "department": "U026", "job_title": "İnce İşler", "sube": "Şantiye",
    }).json()
    varlik = client.post("/assets", json={
        "asset_tag": "N200", "name": "ASUS X542UR", "serial": "H9N0CV07C962370",
        "model_id": mdl["id"], "location_id": loc["id"], "purchase_cost": 28500,
        "custom": {
            "İşlemci": {"İşlemci (Bütün)": "Intel Core i5-7200U", "İşlemci Modeli": "i5"},
            "Bellek": {"Ram Kapasitesi (mB)": "12 Gb"},
            "Depolama": {"Harddisk Tipi": "SSD", "Harddisk Kapasitesi": "240 Gb"},
        },
    }).json()
    client.post(f"/assets/{varlik['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})
    return kisi, varlik


def test_cihaz_detayi(client):
    _kisi, varlik = _hazirla(client)
    d = client.get(f"/detay/asset/{varlik['id']}").json()

    k = d["kunye"]
    assert k["asset_tag"] == "N200"
    assert k["kategori"] == "Dizüstü Bilgisayar"
    assert k["marka"] == "ASUS"
    assert k["model"] == "X542UR"
    assert k["lokasyon"] == "ŞANTİYE"

    assert d["zimmet"]["kisi"] == "Nurettin Eren"
    assert d["zimmet"]["departman"] == "U026"

    # Teknik özellikler gruplu gelmeli
    assert d["ozellikler"]["İşlemci"]["İşlemci (Bütün)"] == "Intel Core i5-7200U"
    assert d["ozellikler"]["Depolama"]["Harddisk Tipi"] == "SSD"

    assert any(g["islem"] == "checkout" for g in d["gecmis"])


def test_kisi_detayi_cihaz_sayisi(client):
    kisi, _varlik = _hazirla(client)
    # ikinci cihaz: farklı tür
    m2 = client.post("/assets", json={"asset_tag": "M012", "name": "AOC Monitör"}).json()
    client.post(f"/assets/{m2['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})

    d = client.get(f"/detay/user/{kisi['id']}").json()
    assert d["kisi"]["ad"] == "Nurettin Eren"
    assert d["kisi"]["employee_num"] == "P-77"
    assert d["cihaz_sayisi"] == 2
    assert d["toplam_deger"] == 28500.0
    assert d["tur_dagilimi"]["Dizüstü Bilgisayar"] == 1
    etiketler = {c["asset_tag"] for c in d["cihazlar"]}
    assert etiketler == {"N200", "M012"}
    # Cihaz özellikleri de listede gelmeli
    n200 = next(c for c in d["cihazlar"] if c["asset_tag"] == "N200")
    assert n200["ozellikler"]["Bellek"]["Ram Kapasitesi (mB)"] == "12 Gb"


def test_zimmetsiz_kisi(client):
    kisi = client.post("/users", json={"first_name": "Boş", "last_name": "Kişi"}).json()
    d = client.get(f"/detay/user/{kisi['id']}").json()
    assert d["cihaz_sayisi"] == 0
    assert d["cihazlar"] == []
    assert d["toplam_deger"] == 0


def test_olmayan_kayit_404(client):
    assert client.get("/detay/asset/99999").status_code == 404
    assert client.get("/detay/user/99999").status_code == 404


def test_detay_giris_ister(anon_client):
    assert anon_client.get("/detay/asset/1").status_code == 401
    assert anon_client.get("/detay/user/1").status_code == 401


def test_viewer_detay_gorebilir(viewer_client):
    """Sadece-okuma kullanıcısı detayları görebilmeli."""
    assert viewer_client.get("/detay/asset/99999").status_code == 404  # 403 değil
