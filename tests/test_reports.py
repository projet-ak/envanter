"""Rapor ve dashboard testleri."""

import datetime as dt


def _setup(client):
    cat = client.post("/categories", json={"name": "Laptop"}).json()
    man = client.post("/manufacturers", json={"name": "Dell"}).json()
    loc = client.post("/locations", json={"name": "Merkez Depo"}).json()
    model = client.post("/models", json={"name": "Latitude", "category_id": cat["id"],
                                         "manufacturer_id": man["id"]}).json()
    user = client.post("/users", json={"first_name": "Ali", "last_name": "Veli",
                                       "department": "BT"}).json()
    return cat, man, loc, model, user


def test_ozet(client):
    _cat, _man, loc, model, user = _setup(client)
    a1 = client.post("/assets", json={"asset_tag": "R-1", "model_id": model["id"],
                                      "location_id": loc["id"],
                                      "purchase_cost": 15000}).json()
    client.post("/assets", json={"asset_tag": "R-2", "purchase_cost": 5000})
    client.post(f"/assets/{a1['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": user["id"]})
    client.post("/accessories", json={"name": "Mouse", "qty": 3, "min_qty": 5})

    r = client.get("/reports/ozet").json()
    assert r["varlik_toplam"] == 2
    assert r["zimmetli"] == 1
    assert r["bosta"] == 1
    assert r["toplam_deger"] == 20000.0
    assert r["aksesuar"] == 1
    # conftest admin + viewer kullanıcılarını da oluşturur, +1 eklenen personel
    assert r["personel"] == 3


def test_dagilim(client):
    _cat, _man, loc, model, _user = _setup(client)
    client.post("/assets", json={"asset_tag": "D-1", "model_id": model["id"],
                                 "location_id": loc["id"]})
    r = client.get("/reports/dagilim").json()
    assert {"ad": "Laptop", "adet": 1} in r["kategori"]
    assert {"ad": "Merkez Depo", "adet": 1} in r["lokasyon"]
    assert {"ad": "Dell", "adet": 1} in r["uretici"]


def test_dusuk_stok(client):
    client.post("/accessories", json={"name": "Mouse", "qty": 2, "min_qty": 5})
    client.post("/accessories", json={"name": "Klavye", "qty": 50, "min_qty": 5})
    client.post("/consumables", json={"name": "Toner", "qty": 1, "min_qty": 3})
    client.post("/components", json={"name": "RAM", "qty": 10, "min_qty": 0})  # min=0 sayılmaz

    r = client.get("/reports/dusuk-stok").json()
    adlar = {x["ad"] for x in r}
    assert adlar == {"Mouse", "Toner"}
    mouse = next(x for x in r if x["ad"] == "Mouse")
    assert mouse["tur"] == "aksesuar" and mouse["adet"] == 2 and mouse["min"] == 5


def test_garanti_raporu(client):
    bugun = dt.date.today()
    client.post("/assets", json={"asset_tag": "G-BITMIS",
                                 "warranty_end": (bugun - dt.timedelta(days=10)).isoformat()})
    client.post("/assets", json={"asset_tag": "G-YAKIN",
                                 "warranty_end": (bugun + dt.timedelta(days=30)).isoformat()})
    client.post("/assets", json={"asset_tag": "G-UZAK",
                                 "warranty_end": (bugun + dt.timedelta(days=500)).isoformat()})

    r = client.get("/reports/garanti", params={"gun": 90}).json()
    etiketler = [x["asset_tag"] for x in r]
    assert "G-BITMIS" in etiketler and "G-YAKIN" in etiketler
    assert "G-UZAK" not in etiketler

    bitmis = next(x for x in r if x["asset_tag"] == "G-BITMIS")
    assert bitmis["bitti"] is True and bitmis["kalan_gun"] < 0
    yakin = next(x for x in r if x["asset_tag"] == "G-YAKIN")
    assert yakin["bitti"] is False and yakin["kalan_gun"] == 30


def test_personel_zimmet(client):
    _cat, _man, _loc, _model, user = _setup(client)
    for tag in ["P-1", "P-2"]:
        a = client.post("/assets", json={"asset_tag": tag}).json()
        client.post(f"/assets/{a['id']}/checkout",
                    json={"assigned_type": "user", "assigned_id": user["id"]})

    r = client.get("/reports/personel-zimmet").json()
    assert len(r) == 1
    assert r[0]["ad"] == "Ali Veli"
    assert r[0]["cihaz_sayisi"] == 2
    assert r[0]["departman"] == "BT"


def test_lisans_kullanim(client):
    bugun = dt.date.today()
    client.post("/licenses", json={"name": "Office", "seats": 50,
                                   "expiration_date": (bugun - dt.timedelta(days=1)).isoformat()})
    client.post("/licenses", json={"name": "Antivirüs", "seats": 100})

    r = client.get("/reports/lisans-kullanim").json()
    office = next(x for x in r if x["ad"] == "Office")
    assert office["suresi_doldu"] is True and office["koltuk"] == 50
    av = next(x for x in r if x["ad"] == "Antivirüs")
    assert av["suresi_doldu"] is False


def test_reports_require_auth(anon_client):
    assert anon_client.get("/reports/ozet").status_code == 401


def test_viewer_can_read_reports(viewer_client):
    assert viewer_client.get("/reports/ozet").status_code == 200
    assert viewer_client.get("/reports/dagilim").status_code == 200
