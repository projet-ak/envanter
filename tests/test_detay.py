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


def test_kisi_gecmisi_ve_cihaz_kullanim_listesi(client):
    """Zimmet al-ver döngüsü iki yönden de izlenebilmeli."""
    a = client.post("/users", json={"first_name": "Önceki",
                                    "last_name": "Kullanıcı"}).json()
    b = client.post("/users", json={"first_name": "Yeni",
                                    "last_name": "Kullanıcı"}).json()
    cihaz = client.post("/assets", json={"asset_tag": "GEC-1"}).json()

    client.post(f"/assets/{cihaz['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": a["id"]})
    client.post(f"/assets/{cihaz['id']}/checkin", json={})
    client.post(f"/assets/{cihaz['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": b["id"]})

    # Kişi geçmişi: eski kullanıcının kaydında aldı + iade etti var
    g = client.get(f"/detay/user/{a['id']}").json()["gecmis"]
    assert [(x["asset_tag"], x["islem"]) for x in g] == \
        [("GEC-1", "iade etti"), ("GEC-1", "aldı")]

    # Cihaz: kimler kullandı — en yeni üstte, açık zimmet iadesiz
    ku = client.get(f"/detay/asset/{cihaz['id']}").json()["kullanim_gecmisi"]
    assert [x["kime"] for x in ku] == ["Yeni Kullanıcı", "Önceki Kullanıcı"]
    assert ku[0]["iade"] is None and ku[1]["iade"] is not None


def test_isten_cikis_tarihi_kaydedilir(client):
    k = client.post("/users", json={"first_name": "Ayrılan",
                                    "ise_giris": "2024-01-10",
                                    "isten_cikis": "2026-06-30"}).json()
    assert k["isten_cikis"] == "2026-06-30"
    d = client.get(f"/detay/user/{k['id']}").json()["kisi"]
    assert d["ise_giris"] == "2024-01-10" and d["isten_cikis"] == "2026-06-30"


def test_islem_gecmisi_okunur_ve_yapanli(client):
    """History log: alan değişiklikleri Türkçe etiket ve adlarla, yapan dolu."""
    lok1 = client.post("/locations", json={"name": "Depo"}).json()
    lok2 = client.post("/locations", json={"name": "ŞANTİYE U070"}).json()
    a = client.post("/assets", json={"asset_tag": "LOG-1", "name": "Log Cihazı",
                                     "location_id": lok1["id"]}).json()
    client.put(f"/assets/{a['id']}",
               json={"location_id": lok2["id"], "name": "Yeni Ad"})

    g = client.get(f"/detay/asset/{a['id']}").json()["gecmis"]
    assert [x["islem"] for x in g] == ["update", "create"]   # en yeni üstte
    assert all(x["yapan"] for x in g), "yapan boş kalmamalı"

    metinler = g[0]["degisim_metinleri"]
    assert "Lokasyon: Depo → ŞANTİYE U070" in metinler       # id değil ad
    assert "Ad: Log Cihazı → Yeni Ad" in metinler


def test_islem_gecmisi_zimmet_ve_iade_kayitlari(client):
    k = client.post("/users", json={"first_name": "Log",
                                    "last_name": "Kişisi"}).json()
    a = client.post("/assets", json={"asset_tag": "LOG-2"}).json()
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": k["id"]})
    client.post(f"/assets/{a['id']}/checkin", json={})

    g = client.get(f"/detay/asset/{a['id']}").json()["gecmis"]
    assert [x["islem"] for x in g] == ["checkin", "checkout", "create"]
    assert all(x["yapan"] for x in g)


def test_lokasyon_detayi_cihaz_ve_kisileri_verir(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE U099",
                                          "proje_kodu": "U099",
                                          "renk": "#15803d"}).json()
    assert lok["renk"] == "#15803d"
    k = client.post("/users", json={"first_name": "Saha", "last_name": "Şefi",
                                    "job_title": "Şef",
                                    "location_id": lok["id"]}).json()
    a1 = client.post("/assets", json={"asset_tag": "LD-1", "name": "Dizüstü",
                                      "location_id": lok["id"]}).json()
    client.post("/assets", json={"asset_tag": "LD-2", "location_id": lok["id"]})
    client.post(f"/assets/{a1['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": k["id"]})

    d = client.get(f"/detay/location/{lok['id']}").json()
    assert d["lokasyon"]["renk"] == "#15803d"
    assert d["cihaz_sayisi"] == 2 and d["zimmetli_sayisi"] == 1
    assert [x["ad"] for x in d["kisiler"]] == ["Saha Şefi"]
    c = next(x for x in d["cihazlar"] if x["asset_tag"] == "LD-1")
    assert c["zimmetli"] == "Saha Şefi"

    sayilar = client.get("/detay/lokasyon-sayilari").json()
    s = next(x for x in sayilar if x["location_id"] == lok["id"])
    assert (s["cihaz"], s["zimmetli"], s["kisi"]) == (2, 1, 1)


def test_lokasyon_rengi_dogrulanir(client):
    r = client.post("/locations", json={"name": "Renk Testi",
                                        "renk": "kırmızı"})
    assert r.status_code == 422        # yalnız #RRGGBB kabul
    lok = client.post("/locations", json={"name": "Renk Testi"}).json()
    r = client.put(f"/locations/{lok['id']}", json={"renk": "#b91c1c"})
    assert r.status_code == 200 and r.json()["renk"] == "#b91c1c"


def test_alt_projeler_detayda_listelenir(client):
    ust = client.post("/locations", json={"name": "KARTAL ESENTEPE 1. VE 2. ETAP",
                                          "proje_kodu": "U030-U031"}).json()
    satis = client.post("/locations", json={"name": "SATIŞ OFİSİ",
                                            "parent_id": ust["id"]}).json()
    client.post("/locations", json={"name": "YÖNETİM OFİSİ",
                                    "parent_id": ust["id"]})
    client.post("/assets", json={"asset_tag": "ALT-1",
                                 "location_id": satis["id"]})

    d = client.get(f"/detay/location/{ust['id']}").json()
    assert d["ust"] is None
    altlar = {a["name"]: a for a in d["alt_lokasyonlar"]}
    assert set(altlar) == {"SATIŞ OFİSİ", "YÖNETİM OFİSİ"}
    assert altlar["SATIŞ OFİSİ"]["cihaz"] == 1

    d2 = client.get(f"/detay/location/{satis['id']}").json()
    assert d2["ust"]["name"] == "KARTAL ESENTEPE 1. VE 2. ETAP"
    assert d2["alt_lokasyonlar"] == []


def test_lokasyon_detayinda_stok_kayitlari_listelenir(client):
    lok = client.post("/locations", json={"name": "STOK ŞANTİYESİ",
                                          "proje_kodu": "U088"}).json()
    client.post("/accessories", json={"name": "Depo Klavyesi", "qty": 5,
                                      "location_id": lok["id"]})
    client.post("/consumables", json={"name": "Depo Toneri", "qty": 2,
                                      "location_id": lok["id"]})

    d = client.get(f"/detay/location/{lok['id']}").json()
    assert d["stok_sayisi"] == 2
    stoklar = {(s["tur"], s["name"]): s for s in d["stoklar"]}
    assert stoklar[("accessory", "Depo Klavyesi")]["qty"] == 5
    assert stoklar[("consumable", "Depo Toneri")]["qty"] == 2

    sayilar = client.get("/detay/lokasyon-sayilari").json()
    s = next(x for x in sayilar if x["location_id"] == lok["id"])
    assert s["stok"] == 2
