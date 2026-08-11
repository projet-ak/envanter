"""Mükerrer kayıt engelleri: içe aktarım, lokasyon adı, seri no + temizlik betiği."""

import importlib.util
from pathlib import Path

from app import models

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "mukerrer-temizle.py"
_spec = importlib.util.spec_from_file_location("mukerrer_temizle", _YOL)
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)


# --------------------------------------------------------------------------- #
# İçe aktarım: serisiz satırlar çoğalmasın
# --------------------------------------------------------------------------- #
def _satir(tag, **ek):
    return {"asset_tag": tag, "cihaz_tipi": "Masaüstü", "ozellikler": {},
            "kisi_mi": False, **ek}


def test_serisiz_satir_yeniden_aktarimda_cogalmaz(client):
    """B001'in ikinci aktarımda B001-2 olmasına yol açan hata."""
    r1 = client.post("/excel/aktar", json={"satirlar": [_satir("B001")]})
    assert r1.json()["eklenen"] == 1

    r2 = client.post("/excel/aktar", json={"satirlar": [_satir("B001")]})
    assert r2.json() ["eklenen"] == 0 and r2.json()["guncellenen"] == 1

    etiketler = [a["asset_tag"] for a in client.get("/assets").json()]
    assert etiketler.count("B001") == 1 and "B001-2" not in etiketler


def test_dosya_ici_tekrarli_etiket_ayri_cihaz_kalir(client):
    """Aynı dosyada iki B002 satırı iki ayrı cihazdır (B002, B002-2);
    yeniden aktarım bu ikisini günceller, B002-3 açmaz."""
    satirlar = [_satir("B002", notes="birinci"), _satir("B002", notes="ikinci")]
    r1 = client.post("/excel/aktar", json={"satirlar": satirlar})
    assert r1.json()["eklenen"] == 2

    r2 = client.post("/excel/aktar", json={"satirlar": satirlar})
    assert r2.json()["eklenen"] == 0 and r2.json()["guncellenen"] == 2

    etiketler = sorted(a["asset_tag"] for a in client.get("/assets").json()
                       if a["asset_tag"].startswith("B002"))
    assert etiketler == ["B002", "B002-2"]


def test_serili_eslesme_oncelikli_kalir(client):
    """Seri numarası varsa eşleşme yine seriden yapılır (etiket değişse bile)."""
    client.post("/excel/aktar", json={"satirlar": [_satir("S-ESKI", serial="SR1")]})
    r = client.post("/excel/aktar", json={"satirlar": [_satir("S-YENI", serial="SR1")]})
    assert r.json()["guncellenen"] == 1 and r.json()["eklenen"] == 0


# --------------------------------------------------------------------------- #
# Lokasyon: aynı adla ikinci kayıt yok
# --------------------------------------------------------------------------- #
def test_ayni_adli_lokasyon_reddedilir(client):
    ilk = client.post("/locations", json={"name": "ŞANTİYE U026"})
    assert ilk.status_code == 201
    # Büyük/küçük ve Türkçe harf farkları da aynı sayılır
    for varyant in ("ŞANTİYE U026", "Şantiye U026", "SANTIYE U026"):
        r = client.post("/locations", json={"name": varyant})
        assert r.status_code == 409, varyant
        assert "zaten var" in r.json()["detail"]


def test_lokasyon_guncellemede_de_engellenir(client):
    a = client.post("/locations", json={"name": "Depo"}).json()
    client.post("/locations", json={"name": "Merkez Ofis"})
    r = client.put(f"/locations/{a['id']}", json={"name": "merkez ofis"})
    assert r.status_code == 409
    # Kendi adıyla güncelleme serbest (başka alan değişiyor olabilir)
    r = client.put(f"/locations/{a['id']}", json={"name": "Depo", "city": "Ankara"})
    assert r.status_code == 200


def test_kategori_ve_uretici_de_essiz(client):
    client.post("/categories", json={"name": "Dizüstü"})
    assert client.post("/categories", json={"name": "DİZÜSTÜ"}).status_code == 409
    client.post("/manufacturers", json={"name": "HP"})
    assert client.post("/manufacturers", json={"name": "hp"}).status_code == 409


# --------------------------------------------------------------------------- #
# Cihaz: aynı seri numarasıyla ikinci kayıt yok
# --------------------------------------------------------------------------- #
def test_ayni_seri_ile_cihaz_acilamaz(client):
    client.post("/assets", json={"asset_tag": "SER-1", "serial": "ABC123"})
    r = client.post("/assets", json={"asset_tag": "SER-2", "serial": "ABC123"})
    assert r.status_code == 409
    assert "SER-1" in r.json()["detail"]


def test_guncellemede_seri_carpismasi_engellenir(client):
    client.post("/assets", json={"asset_tag": "SER-3", "serial": "XYZ1"})
    b = client.post("/assets", json={"asset_tag": "SER-4"}).json()
    assert client.put(f"/assets/{b['id']}",
                      json={"serial": "XYZ1"}).status_code == 409
    # Kendi serisini yeniden göndermek serbest
    a = next(x for x in client.get("/assets").json()
             if x["asset_tag"] == "SER-3")
    assert client.put(f"/assets/{a['id']}",
                      json={"serial": "XYZ1", "name": "Ad"}).status_code == 200


def test_bos_seri_serbest(client):
    assert client.post("/assets", json={"asset_tag": "BS-1"}).status_code == 201
    assert client.post("/assets", json={"asset_tag": "BS-2"}).status_code == 201


# --------------------------------------------------------------------------- #
# Temizlik betiği
# --------------------------------------------------------------------------- #
def test_lokasyon_birlestirme(db_session):
    db = db_session
    l1 = models.Location(name="ŞANTİYE U026")                    # 2 bağlantı
    l2 = models.Location(name="Şantiye U026", proje_kodu="U026")  # kod dolu → kalır
    l3 = models.Location(name="Merkez")                           # ilgisiz
    db.add_all([l1, l2, l3])
    db.flush()
    db.add_all([
        models.Asset(asset_tag="MK-1", location_id=l1.id),
        models.Asset(asset_tag="MK-2", assigned_location_id=l1.id),
        models.User(first_name="Mük", location_id=l1.id),
    ])
    db.commit()

    gruplar = mt.lokasyon_gruplari(db)
    assert len(gruplar) == 1 and {x.id for x in gruplar[0]} == {l1.id, l2.id}

    silinen, tasinan = mt.lokasyonlari_birlestir(
        db, gruplar, mt._referans_sayilari(db))
    assert (silinen, tasinan) == (1, 3)
    assert db.get(models.Location, l1.id) is None
    kalan = db.get(models.Location, l2.id)
    assert kalan.proje_kodu == "U026"
    assert db.query(models.Asset).filter_by(asset_tag="MK-1").one() \
        .location_id == l2.id
    assert db.query(models.User).filter_by(first_name="Mük").one() \
        .location_id == l2.id
    assert mt.lokasyon_gruplari(db) == []       # idempotent


def test_cihaz_gruplari_raporu(db_session):
    db = db_session
    db.add_all([
        models.Asset(asset_tag="B001"),
        models.Asset(asset_tag="B001-2"),
        models.Asset(asset_tag="B001-3"),
        models.Asset(asset_tag="C900", serial="AYNI-SERI"),
        models.Asset(asset_tag="C901", serial="AYNI-SERI"),
        models.Asset(asset_tag="TEK-1"),          # ilgisiz
        models.Asset(asset_tag="X-2"),            # taban "X" yok → grup değil
    ])
    db.commit()

    seri, etiket = mt.cihaz_gruplari(db)
    assert [sorted(a.asset_tag for a in g) for g in seri] == [["C900", "C901"]]
    assert [sorted(a.asset_tag for a in g) for g in etiket] == \
        [["B001", "B001-2", "B001-3"]]


# --------------------------------------------------------------------------- #
# Proje kodunda çift kayıt engeli
# --------------------------------------------------------------------------- #
def test_ayni_proje_kodlu_ikinci_kok_kayit_reddedilir(client):
    client.post("/locations", json={"name": "KARTAL ESENTEPE",
                                    "proje_kodu": "U030-U031"})
    r = client.post("/locations", json={"name": "KARTAL BAŞKA",
                                        "proje_kodu": "U030-U031"})
    assert r.status_code == 409
    assert "KARTAL ESENTEPE" in r.json()["detail"]
    assert "Üst lokasyon" in r.json()["detail"]


def test_alt_lokasyon_ayni_kodu_kullanabilir(client):
    ust = client.post("/locations", json={"name": "ANA PROJE",
                                          "proje_kodu": "U099"}).json()
    r = client.post("/locations", json={"name": "SATIŞ OFİSİ",
                                        "proje_kodu": "U099",
                                        "parent_id": ust["id"]})
    assert r.status_code == 201


def test_guncellemede_kod_carpismasi_ve_kendi_kodu(client):
    a = client.post("/locations", json={"name": "PROJE A",
                                        "proje_kodu": "U101"}).json()
    b = client.post("/locations", json={"name": "PROJE B"}).json()
    # Başka kök kayda aynı kod verilemez
    assert client.put(f"/locations/{b['id']}",
                      json={"proje_kodu": "U101"}).status_code == 409
    # Kendi kodunu yeniden göndermek serbest
    assert client.put(f"/locations/{a['id']}",
                      json={"proje_kodu": "U101",
                            "city": "İstanbul"}).status_code == 200
    # Üst seçilirse aynı kod alınabilir
    assert client.put(f"/locations/{b['id']}",
                      json={"proje_kodu": "U101",
                            "parent_id": a["id"]}).status_code == 200


# --------------------------------------------------------------------------- #
# Arayüzden birleştirme ucu
# --------------------------------------------------------------------------- #
def test_lokasyon_birlestirme_ucu(client):
    h = client.post("/locations", json={"name": "KARTAL ESENTEPE ETAP",
                                        "proje_kodu": "U030"}).json()
    k = client.post("/locations", json={"name": "Kartal Esentepe Etap X"}).json()
    # kaynağa bağlı veri: cihaz, kişi, alt lokasyon
    client.post("/assets", json={"asset_tag": "BR-1", "location_id": k["id"]})
    kisi = client.post("/users", json={"first_name": "Taşınan",
                                       "location_id": k["id"]}).json()
    alt = client.post("/locations", json={"name": "BİRLEŞEN OFİS",
                                          "parent_id": k["id"]}).json()

    r = client.post("/detay/lokasyon-birlestir",
                    json={"kaynak_id": k["id"], "hedef_id": h["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["tasinan"] == 2          # cihaz + kişi

    assert client.get(f"/locations/{k['id']}").status_code == 404
    varlik = next(a for a in client.get("/assets").json()
                  if a["asset_tag"] == "BR-1")
    assert varlik["location_id"] == h["id"]
    assert client.get(f"/users/{kisi['id']}").json()["location_id"] == h["id"]
    assert client.get(f"/locations/{alt['id']}").json()["parent_id"] == h["id"]


def test_birlestirme_hedef_kaynagin_altindaysa_yukari_alinir(client):
    k = client.post("/locations", json={"name": "ESKİ PROJE"}).json()
    h = client.post("/locations", json={"name": "YENİ PROJE",
                                        "parent_id": k["id"]}).json()
    r = client.post("/detay/lokasyon-birlestir",
                    json={"kaynak_id": k["id"], "hedef_id": h["id"]})
    assert r.status_code == 200
    assert client.get(f"/locations/{h['id']}").json()["parent_id"] is None


def test_birlestirme_hatalari_ve_yetki(client, viewer_client):
    a = client.post("/locations", json={"name": "TEK"}).json()
    assert client.post("/detay/lokasyon-birlestir",
                       json={"kaynak_id": a["id"],
                             "hedef_id": a["id"]}).status_code == 400
    assert client.post("/detay/lokasyon-birlestir",
                       json={"kaynak_id": a["id"],
                             "hedef_id": 9999}).status_code == 404
    assert viewer_client.post("/detay/lokasyon-birlestir",
                              json={"kaynak_id": 1,
                                    "hedef_id": 2}).status_code == 403


# --------------------------------------------------------------------------- #
# Lokasyon silme: gizli bağlantılar anlaşılır 409 ile engellenir
# --------------------------------------------------------------------------- #
def test_zimmet_yeri_olan_lokasyon_silinemez_aciklamali(client):
    lok = client.post("/locations", json={"name": "GİZLİ BAĞLI"}).json()
    a = client.post("/assets", json={"asset_tag": "GB-1"}).json()
    client.post(f"/assets/{a['id']}/checkout",
                json={"assigned_type": "location", "assigned_id": lok["id"]})

    r = client.delete(f"/locations/{lok['id']}")
    assert r.status_code == 409
    assert "zimmet yeri" in r.json()["detail"]
    assert "Birleştir" in r.json()["detail"]

    # Detay da gizli bağlantıyı gösterir
    d = client.get(f"/detay/location/{lok['id']}").json()
    assert d["zimmet_yeri_sayisi"] == 1 and d["cihaz_sayisi"] == 0


def test_stok_kaydi_olan_lokasyon_silinemez(client):
    lok = client.post("/locations", json={"name": "STOKLU"}).json()
    client.post("/accessories", json={"name": "Depodaki Klavye", "qty": 3,
                                      "location_id": lok["id"]})
    r = client.delete(f"/locations/{lok['id']}")
    assert r.status_code == 409 and "aksesuar" in r.json()["detail"]
    assert client.get(
        f"/detay/location/{lok['id']}").json()["stok_sayisi"] == 1


def test_alt_lokasyonu_olan_silinemez_bos_olan_silinir(client):
    ust = client.post("/locations", json={"name": "ÜSTLÜ"}).json()
    client.post("/locations", json={"name": "ALTI", "parent_id": ust["id"]})
    r = client.delete(f"/locations/{ust['id']}")
    assert r.status_code == 409 and "alt lokasyon" in r.json()["detail"]

    bos = client.post("/locations", json={"name": "BOŞ KAYIT"}).json()
    assert client.delete(f"/locations/{bos['id']}").status_code == 204


def test_birlestirme_stok_kayitlarini_da_tasir(client):
    h = client.post("/locations", json={"name": "STOK HEDEF"}).json()
    k = client.post("/locations", json={"name": "Stok Hedef X"}).json()
    aks = client.post("/accessories", json={"name": "Taşınan Mouse", "qty": 2,
                                            "location_id": k["id"]}).json()
    r = client.post("/detay/lokasyon-birlestir",
                    json={"kaynak_id": k["id"], "hedef_id": h["id"]})
    assert r.status_code == 200 and r.json()["tasinan"] == 1
    assert client.get(
        f"/accessories/{aks['id']}").json()["location_id"] == h["id"]
    # Kaynak artık silinebilir durumda değil — zaten silindi
    assert client.get(f"/locations/{k['id']}").status_code == 404
