"""Stok hareketleri: giriş (+), kişiye zimmet (−), tarihçe ve geri alma."""


def _sarf(client, ad="Klavye Mouse Set", qty=10):
    return client.post("/consumables",
                       json={"name": ad, "qty": qty, "min_qty": 2}).json()


def _kisi(client, ad="Stok", soyad="Alan"):
    return client.post("/users", json={"first_name": ad, "last_name": soyad,
                                       "employee_num": f"SH-{ad}"}).json()


def test_giris_adet_arttirir_ve_kayda_gecer(client):
    s = _sarf(client)
    r = client.post(f"/stok/consumable/{s['id']}/giris",
                    json={"adet": 5, "aciklama": "Fatura 2026/41"})
    assert r.status_code == 201, r.text
    assert r.json()["islem"] == "giris" and r.json()["adet"] == 5

    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 15
    hareketler = client.get(f"/stok/consumable/{s['id']}/hareketler").json()
    assert len(hareketler) == 1
    assert hareketler[0]["aciklama"] == "Fatura 2026/41"
    assert hareketler[0]["yapan"]          # kim yaptı boş kalmaz


def test_zimmet_adet_dusurur_kisiyi_yazar(client):
    s, k = _sarf(client), _kisi(client)
    r = client.post(f"/stok/consumable/{s['id']}/zimmet",
                    json={"user_id": k["id"], "adet": 2})
    assert r.status_code == 201, r.text
    assert r.json()["kisi"] == "Stok Alan"

    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 8
    h = client.get(f"/stok/consumable/{s['id']}/hareketler").json()[0]
    assert h["islem"] == "zimmet" and h["adet"] == 2
    assert h["kisi"] == "Stok Alan" and h["user_id"] == k["id"]
    assert h["created_at"]


def test_hareketler_yeniden_eskiye(client):
    s, k = _sarf(client), _kisi(client)
    client.post(f"/stok/consumable/{s['id']}/giris", json={"adet": 1})
    client.post(f"/stok/consumable/{s['id']}/zimmet",
                json={"user_id": k["id"], "adet": 1})
    islemler = [h["islem"] for h in
                client.get(f"/stok/consumable/{s['id']}/hareketler").json()]
    assert islemler == ["zimmet", "giris"]      # en yeni başta


def test_stok_yetersizse_zimmet_reddedilir(client):
    s, k = _sarf(client, qty=1), _kisi(client)
    r = client.post(f"/stok/consumable/{s['id']}/zimmet",
                    json={"user_id": k["id"], "adet": 3})
    assert r.status_code == 400
    assert "yetersiz" in r.json()["detail"].lower()
    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 1  # değişmedi


def test_bilinmeyen_kisi_ve_kayit(client):
    s = _sarf(client)
    assert client.post(f"/stok/consumable/{s['id']}/zimmet",
                       json={"user_id": 99999, "adet": 1}).status_code == 404
    assert client.post("/stok/consumable/99999/giris",
                       json={"adet": 1}).status_code == 404


def test_lisans_koltuk_mantigi(client):
    """Lisansta koltuk TOPLAM kapasitedir: zimmet koltuğu doldurur ama
    seats azalmaz; giriş koltuk ekler; kapasite aşımı 400."""
    lis = client.post("/licenses", json={"name": "Ofis", "seats": 5}).json()
    k = _kisi(client, "Lisans", "Kullanan")

    r = client.post(f"/stok/license/{lis['id']}/zimmet",
                    json={"user_id": k["id"], "adet": 3})
    assert r.status_code == 201, r.text
    assert client.get(f"/licenses/{lis['id']}").json()["seats"] == 5  # değişmez

    # 2 koltuk boşta: 3 istenirse reddedilir
    r = client.post(f"/stok/license/{lis['id']}/zimmet",
                    json={"user_id": k["id"], "adet": 3})
    assert r.status_code == 400 and "Koltuk yetersiz" in r.json()["detail"]

    # Koltuk girişi kapasiteyi büyütür → artık sığar
    client.post(f"/stok/license/{lis['id']}/giris", json={"adet": 1})
    assert client.get(f"/licenses/{lis['id']}").json()["seats"] == 6
    assert client.post(f"/stok/license/{lis['id']}/zimmet",
                       json={"user_id": k["id"], "adet": 3}).status_code == 201

    # Dağılım: kişide 6 koltuk görünür
    d = client.get(f"/stok/license/{lis['id']}/dagilim").json()
    assert d["kisiler"][0]["adet"] == 6

    # Tüm koltuklar doluyken koltuk girişi geri alınamaz
    hareketler = client.get(f"/stok/license/{lis['id']}/hareketler").json()
    giris = next(h for h in hareketler if h["islem"] == "giris")
    assert client.delete(
        f"/stok/hareketleri/{giris['id']}").status_code == 400
    # Zimmet geri alınınca koltuk boşalır, giriş de geri alınabilir
    zimmet = next(h for h in hareketler if h["islem"] == "zimmet")
    assert client.delete(
        f"/stok/hareketleri/{zimmet['id']}").status_code == 204
    assert client.delete(
        f"/stok/hareketleri/{giris['id']}").status_code == 204
    assert client.get(f"/licenses/{lis['id']}").json()["seats"] == 5


def test_aksesuar_ve_bilesen_de_calisir(client):
    aks = client.post("/accessories", json={"name": "Kulaklık", "qty": 3}).json()
    bil = client.post("/components", json={"name": "RAM 8GB", "qty": 4}).json()
    assert client.post(f"/stok/accessory/{aks['id']}/giris",
                       json={"adet": 2}).status_code == 201
    assert client.get(f"/accessories/{aks['id']}").json()["qty"] == 5
    k = _kisi(client, "Aks", "Bil")
    assert client.post(f"/stok/component/{bil['id']}/zimmet",
                       json={"user_id": k["id"], "adet": 4}).status_code == 201
    assert client.get(f"/components/{bil['id']}").json()["qty"] == 0


def test_geri_alma_adedi_ters_yonde_duzeltir(client):
    s, k = _sarf(client), _kisi(client)
    giris = client.post(f"/stok/consumable/{s['id']}/giris",
                        json={"adet": 5}).json()
    zimmet = client.post(f"/stok/consumable/{s['id']}/zimmet",
                         json={"user_id": k["id"], "adet": 3}).json()
    # 10 + 5 - 3 = 12
    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 12

    assert client.delete(f"/stok/hareketleri/{zimmet['id']}").status_code == 204
    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 15
    assert client.delete(f"/stok/hareketleri/{giris['id']}").status_code == 204
    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 10
    assert client.get(f"/stok/consumable/{s['id']}/hareketler").json() == []


def test_dagitilmis_giris_geri_alinamaz(client):
    """Giriş sonrası ürünler dağıtıldıysa girişin geri alınması stoku eksiye
    düşürürdü — reddedilir."""
    s, k = _sarf(client, qty=0), _kisi(client)
    giris = client.post(f"/stok/consumable/{s['id']}/giris",
                        json={"adet": 5}).json()
    client.post(f"/stok/consumable/{s['id']}/zimmet",
                json={"user_id": k["id"], "adet": 4})
    assert client.delete(f"/stok/hareketleri/{giris['id']}").status_code == 400
    assert client.get(f"/consumables/{s['id']}").json()["qty"] == 1


def test_kayit_silinince_hareketleri_de_silinir(client, db_session):
    from app import models

    s, k = _sarf(client), _kisi(client)
    client.post(f"/stok/consumable/{s['id']}/zimmet",
                json={"user_id": k["id"], "adet": 1})
    client.delete(f"/consumables/{s['id']}")
    kalan = db_session.query(models.StockMove).filter_by(
        kayit_turu=models.StokTuru.consumable, kayit_id=s["id"]).count()
    assert kalan == 0


def test_yazma_yetkisi_gerekir(viewer_client, client, anon_client):
    s = _sarf(client)
    assert viewer_client.post(f"/stok/consumable/{s['id']}/giris",
                              json={"adet": 1}).status_code == 403
    assert anon_client.get(
        f"/stok/consumable/{s['id']}/hareketler").status_code == 401


def test_dagilim_ozeti_ve_kisi_dagilimi(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE U070",
                                          "proje_kodu": "U070"}).json()
    merkez = client.post("/locations", json={"name": "MERKEZ OFİS"}).json()
    k1 = client.post("/users", json={"first_name": "Saha", "last_name": "Bir",
                                     "location_id": lok["id"]}).json()
    k2 = client.post("/users", json={"first_name": "Ofis", "last_name": "İki",
                                     "location_id": merkez["id"]}).json()
    s = client.post("/consumables", json={"name": "Dağıtım Seti",
                                          "qty": 10}).json()
    client.post(f"/stok/consumable/{s['id']}/zimmet",
                json={"user_id": k1["id"], "adet": 3})
    client.post(f"/stok/consumable/{s['id']}/zimmet",
                json={"user_id": k2["id"], "adet": 1})

    ozet = client.get("/stok/consumable/dagilim-ozet").json()
    o = next(x for x in ozet if x["kayit_id"] == s["id"])
    assert (o["dagitilan"], o["kisi"]) == (4, 2)

    d = client.get(f"/stok/consumable/{s['id']}/dagilim").json()
    assert [(x["ad"], x["adet"]) for x in d["kisiler"]] == \
        [("Saha Bir", 3), ("Ofis İki", 1)]         # adede göre azalan
    assert d["kisiler"][0]["proje_kodu"] == "U070"
    loklar = {x["lokasyon"]: x for x in d["lokasyonlar"]}
    assert loklar["ŞANTİYE U070"]["adet"] == 3
    assert loklar["MERKEZ OFİS"]["kisi"] == 1


def test_dagilim_geri_almayla_gunceller(client):
    k = client.post("/users", json={"first_name": "Geri",
                                    "last_name": "Alan"}).json()
    s = client.post("/accessories", json={"name": "İade Kulaklık",
                                          "qty": 5}).json()
    h = client.post(f"/stok/accessory/{s['id']}/zimmet",
                    json={"user_id": k["id"], "adet": 2}).json()
    client.delete(f"/stok/hareketleri/{h['id']}")

    ozet = client.get("/stok/accessory/dagilim-ozet").json()
    assert not any(x["kayit_id"] == s["id"] for x in ozet)
    assert client.get(
        f"/stok/accessory/{s['id']}/dagilim").json()["kisiler"] == []
