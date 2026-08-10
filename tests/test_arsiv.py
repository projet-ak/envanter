"""Arşivle/kaldır akışı + zimmetli cihaz silme koruması."""


def _cihaz(client, tag="ARS-1", **ek):
    r = client.post("/assets", json={"asset_tag": tag, **ek})
    assert r.status_code == 201, r.text
    return r.json()


def _kisi(client):
    return client.post("/users", json={"first_name": "Arşiv",
                                       "last_name": "Testi"}).json()


def _etiketler(client, **params):
    return [a["asset_tag"] for a in
            client.get("/assets", params=params).json()]


def test_arsivle_listeden_dusurur(client):
    a = _cihaz(client)
    r = client.post(f"/assets/{a['id']}/arsivle")
    assert r.status_code == 200, r.text

    assert "ARS-1" not in _etiketler(client)            # varsayılan liste
    assert "ARS-1" in _etiketler(client, arsiv="true")  # arşiv görünümü
    # Sayı ucu da aynı ayrımı yapar
    assert client.get("/assets/sayi").json()["toplam"] == 0
    assert client.get("/assets/sayi",
                      params={"arsiv": "true"}).json()["toplam"] == 1


def test_arsiv_islem_gecmisine_yazilir(client):
    a = _cihaz(client, "ARS-LOG")
    client.post(f"/assets/{a['id']}/arsivle")
    g = client.get(f"/detay/asset/{a['id']}").json()["gecmis"]
    assert g[0]["islem"] == "update" and "arşiv" in g[0]["not"].lower()
    assert g[0]["yapan"]


def test_zimmetli_cihaz_arsivlenemez_ve_silinemez(client):
    a, k = _cihaz(client, "ARS-Z"), _kisi(client)
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": k["id"]})

    r = client.post(f"/assets/{a['id']}/arsivle")
    assert r.status_code == 409 and "iade" in r.json()["detail"]

    r = client.delete(f"/assets/{a['id']}")
    assert r.status_code == 409
    assert "zimmetli" in r.json()["detail"] and "arşiv" in r.json()["detail"].lower()

    # İade sonrası ikisi de serbest
    client.post(f"/assets/{a['id']}/checkin", json={})
    assert client.delete(f"/assets/{a['id']}").status_code == 204


def test_arsivden_cikar_tedavule_donderir(client):
    a = _cihaz(client, "ARS-D")
    client.post(f"/assets/{a['id']}/arsivle")
    r = client.post(f"/assets/{a['id']}/arsivden-cikar")
    assert r.status_code == 200

    assert "ARS-D" in _etiketler(client)
    durumlar = {s["id"]: s for s in client.get("/status-labels").json()}
    yeni = client.get(f"/assets/{a['id']}").json()["status_id"]
    assert durumlar[yeni]["type"] == "deployable"


def test_cifte_arsiv_ve_yersiz_cikarma_reddedilir(client):
    a = _cihaz(client, "ARS-C")
    assert client.post(f"/assets/{a['id']}/arsivden-cikar").status_code == 409
    client.post(f"/assets/{a['id']}/arsivle")
    assert client.post(f"/assets/{a['id']}/arsivle").status_code == 409


def test_arsiv_yetki_ister(client, viewer_client, anon_client):
    a = _cihaz(client, "ARS-Y")
    assert viewer_client.post(f"/assets/{a['id']}/arsivle").status_code == 403
    assert anon_client.post(f"/assets/{a['id']}/arsivle").status_code == 401
