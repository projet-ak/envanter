"""Mükerrer varlık tespiti ve birleştirme (app/mukerrer.py + /assets/mukerrer)."""

import pytest

from app import mukerrer


@pytest.mark.parametrize("etiket, beklenen", [
    ("B002", "b002"),
    ("B002-2", "b002"),
    ("B002-3", "b002"),
    ("B002_2", "b002"),
    ("B002 (2)", "b002"),
    ("N213", "n213"),
    # Etiketin kendisi rakamla bitiyorsa sonek sanılmamalı: ayıraç şart
    ("SW-4800", "sw-4800"),
    ("", ""),
])
def test_etiket_koku(etiket, beklenen):
    assert mukerrer.etiket_koku(etiket) == beklenen


def test_seri_anahtar_bicimden_bagimsiz():
    assert mukerrer.seri_anahtar("pf0-nrs 1q") == "PF0NRS1Q"
    assert mukerrer.seri_anahtar(None) == ""


def _varlik(db, **alanlar):
    from app import models

    a = models.Asset(**alanlar)
    db.add(a)
    db.commit()
    return a


def test_gruplar_etiket_kokunu_yakalar(db_session):
    _varlik(db_session, asset_tag="B002")
    _varlik(db_session, asset_tag="B002-2")
    _varlik(db_session, asset_tag="B009")          # tek başına: grupta olmaz

    gruplar = mukerrer.gruplar(db_session)
    assert len(gruplar) == 1
    grup = gruplar[0]
    assert {k["asset_tag"] for k in grup["kayitlar"]} == {"B002", "B002-2"}
    assert grup["kanit"] == ["etiket"] and grup["guc"] == 1


def test_gruplar_seri_ve_ifs_kodunu_yakalar(db_session):
    _varlik(db_session, asset_tag="N100", serial="PF0NRS1Q")
    _varlik(db_session, asset_tag="ESKI-7", serial="pf0-nrs1q")   # aynı seri
    _varlik(db_session, asset_tag="M50", muhasebe_kodu="FRM-1")
    _varlik(db_session, asset_tag="M77", muhasebe_kodu="FRM-1")

    gruplar = mukerrer.gruplar(db_session)
    assert len(gruplar) == 2
    # Seri/IFS kanıtı etiket kökünden güçlüdür, önce listelenir
    assert all(g["guc"] == 3 for g in gruplar)
    kanitlar = {g["kayitlar"][0]["asset_tag"]: g["kanit"] for g in gruplar}
    assert kanitlar["N100"] == ["seri"] or kanitlar["ESKI-7"] == ["seri"]


def test_ayni_cihaz_tek_grupta_toplanir(db_session):
    """Hem etiket kökü hem seri no eşleşiyorsa grup ikiye bölünmez."""
    _varlik(db_session, asset_tag="B002", serial="AYNI")
    _varlik(db_session, asset_tag="B002-2", serial="AYNI")
    _varlik(db_session, asset_tag="B002-3", demirbas_no="DMR-1")
    _varlik(db_session, asset_tag="X1", demirbas_no="DMR-1")

    gruplar = mukerrer.gruplar(db_session)
    assert len(gruplar) == 1                       # dördü de aynı zincirde
    assert len(gruplar[0]["kayitlar"]) == 4
    assert set(gruplar[0]["kanit"]) == {"seri", "demirbas", "etiket"}


def test_onerilen_hedef_en_dolu_kayit(db_session):
    bos = _varlik(db_session, asset_tag="B002-2")
    dolu = _varlik(db_session, asset_tag="B002", serial="S1",
                   demirbas_no="D1", notes="not")
    grup = mukerrer.gruplar(db_session)[0]
    assert grup["onerilen_hedef"] == dolu.id
    assert grup["kayitlar"][0]["id"] == dolu.id and grup["kayitlar"][-1]["id"] == bos.id


def test_zimmetli_kayit_hedef_olarak_onerilir(db_session):
    """Kullanımdaki cihazın etiketi zimmet fişlerinde geçer — o kalsın."""
    from app import models

    kisi = models.User(first_name="Ali", last_name="Veli")
    db_session.add(kisi)
    db_session.commit()
    zimmetli = _varlik(db_session, asset_tag="B003",
                       assigned_type=models.AssignedType.user,
                       assigned_user_id=kisi.id)
    daha_dolu = _varlik(db_session, asset_tag="B003-2", serial="S1",
                        demirbas_no="D1", muhasebe_kodu="FRM-1", notes="n")

    grup = mukerrer.gruplar(db_session)[0]
    assert grup["onerilen_hedef"] == zimmetli.id
    # Birleştirme yönü ne olursa olsun bilgi kaybolmaz
    mukerrer.birlestir(db_session, zimmetli.id, [daha_dolu.id])
    assert zimmetli.serial == "S1" and zimmetli.muhasebe_kodu == "FRM-1"
    assert zimmetli.assigned_user_id == kisi.id


def test_birlestirme_bilgi_kaybetmez(db_session):
    from app import models

    hedef = _varlik(db_session, asset_tag="B002", serial="S1")
    kaynak = _varlik(db_session, asset_tag="B002-2", demirbas_no="DMR-9",
                     notes="eski not", custom={"İşlemci": {"İşlemci Markası": "İntel i5"}})
    kisi = models.User(first_name="Ali", last_name="Veli")
    db_session.add(kisi)
    db_session.commit()
    kaynak.assigned_type = models.AssignedType.user
    kaynak.assigned_user_id = kisi.id
    db_session.add(models.AssetFile(asset_id=kaynak.id, tur=models.DosyaTuru.gorsel,
                                    dosya_adi="a.png", yol="x/a.png"))
    db_session.add(models.ActivityLog(action=models.ActivityAction.update,
                                      item_type="asset", item_id=kaynak.id))
    db_session.commit()

    sonuc = mukerrer.birlestir(db_session, hedef.id, [kaynak.id], aktor="test")

    assert sonuc["silinen"] == ["B002-2"] and sonuc["dosya"] == 1
    db_session.expire_all()
    assert db_session.get(models.Asset, kaynak.id) is None
    assert hedef.serial == "S1"                    # dolu alan korunur
    assert hedef.demirbas_no == "DMR-9"            # boş alan kaynaktan dolar
    assert hedef.notes == "eski not"
    assert hedef.custom["İşlemci"]["İşlemci Markası"] == "İntel i5"
    assert hedef.assigned_user_id == kisi.id       # zimmet devralınır

    # Dosya ve geçmiş hedefe taşındı, birleştirme geçmişe yazıldı
    dosyalar = db_session.scalars(
        __import__("sqlalchemy").select(models.AssetFile)).all()
    assert [d.asset_id for d in dosyalar] == [hedef.id]
    notlar = [g.note or "" for g in db_session.scalars(
        __import__("sqlalchemy").select(models.ActivityLog)).all()]
    assert any("Mükerrer kayıt birleştirildi" in n and "B002-2" in n for n in notlar)


def test_dolu_alanin_ustune_yazilmaz(db_session):
    hedef = _varlik(db_session, asset_tag="B002", serial="DOGRU", notes="hedef notu")
    kaynak = _varlik(db_session, asset_tag="B002-2", serial=None, notes="kaynak notu")
    mukerrer.birlestir(db_session, hedef.id, [kaynak.id])
    assert hedef.serial == "DOGRU" and hedef.notes == "hedef notu"


def test_hedef_kaynak_ayni_olamaz(db_session):
    hedef = _varlik(db_session, asset_tag="B002")
    with pytest.raises(ValueError):
        mukerrer.birlestir(db_session, hedef.id, [hedef.id])


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_mukerrer_ucu_ve_birlestirme(client):
    a = client.post("/assets", json={"asset_tag": "B002", "serial": "S1"}).json()
    b = client.post("/assets", json={"asset_tag": "B002-2",
                                     "demirbas_no": "DMR-9"}).json()
    client.post("/assets", json={"asset_tag": "TEK"})

    gruplar = client.get("/assets/mukerrer").json()
    assert len(gruplar) == 1
    assert {k["asset_tag"] for k in gruplar[0]["kayitlar"]} == {"B002", "B002-2"}

    r = client.post("/assets/mukerrer/birlestir",
                    json={"hedef_id": a["id"], "kaynak_idler": [b["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["silinen"] == ["B002-2"]
    assert client.get(f"/assets/{b['id']}").status_code == 404
    assert client.get(f"/assets/{a['id']}").json()["demirbas_no"] == "DMR-9"
    assert client.get("/assets/mukerrer").json() == []


def test_viewer_birlestiremez(viewer_client):
    assert viewer_client.get("/assets/mukerrer").status_code == 200
    assert viewer_client.post("/assets/mukerrer/birlestir",
                              json={"hedef_id": 1, "kaynak_idler": [2]}
                              ).status_code == 403


def test_ayni_demirbas_ve_ifs_kodu_ikinci_kez_girilemez(client):
    client.post("/assets", json={"asset_tag": "A1", "demirbas_no": "DMR-1",
                                 "muhasebe_kodu": "FRM-1"})
    ayni_demirbas = client.post("/assets", json={"asset_tag": "A2",
                                                 "demirbas_no": "DMR-1"})
    assert ayni_demirbas.status_code == 409
    assert "A1" in ayni_demirbas.json()["detail"]

    ayni_ifs = client.post("/assets", json={"asset_tag": "A3",
                                            "muhasebe_kodu": "FRM-1"})
    assert ayni_ifs.status_code == 409

    # Güncellemede de aynı denetim var; kendi değerini korumak serbest
    kayit = client.post("/assets", json={"asset_tag": "A4"}).json()
    assert client.put(f"/assets/{kayit['id']}",
                      json={"demirbas_no": "DMR-1"}).status_code == 409
    assert client.put(f"/assets/{kayit['id']}",
                      json={"demirbas_no": "DMR-4"}).status_code == 200
    assert client.put(f"/assets/{kayit['id']}",
                      json={"demirbas_no": "DMR-4", "notes": "x"}).status_code == 200


def test_karsilastirma_alanlari_ozette_gelir(db_session):
    from app import models

    kat = models.Category(name="Dizüstü Bilgisayar")
    marka = models.Manufacturer(name="LENOVO")
    db_session.add_all([kat, marka])
    db_session.flush()
    mdl = models.AssetModel(name="Z50-70", category_id=kat.id,
                            manufacturer_id=marka.id)
    lok = models.Location(name="KARTAL PROJESİ")
    db_session.add_all([mdl, lok])
    db_session.commit()

    _varlik(db_session, asset_tag="B002", serial="S1", model_id=mdl.id,
            location_id=lok.id,
            custom={"İşlemci": {"İşlemci Markası": "İntel i5"}})
    _varlik(db_session, asset_tag="B002-2", serial="S1", notes="ikinci kayıt")

    grup = mukerrer.gruplar(db_session)[0]
    ilk = next(k for k in grup["kayitlar"] if k["asset_tag"] == "B002")
    # Kimlik alanları ada çevrilmiş olarak gelir (karşılaştırma okunabilsin)
    assert ilk["alanlar"]["model_id"] == "LENOVO Z50-70"
    assert ilk["alanlar"]["location_id"] == "KARTAL PROJESİ"
    assert ilk["alanlar"]["serial"] == "S1"
    assert ilk["ozellikler"] == {"İşlemci / İşlemci Markası": "İntel i5"}
    ikinci = next(k for k in grup["kayitlar"] if k["asset_tag"] == "B002-2")
    assert ikinci["alanlar"]["notes"] == "ikinci kayıt"
    assert ikinci["alanlar"]["model_id"] == ""


def test_secimle_birlestirme_celiskiyi_cozer(db_session):
    """Çakışan alanda kullanıcının seçtiği değer kazanır."""
    hedef = _varlik(db_session, asset_tag="B002", serial="YANLIS",
                    notes="hedef notu")
    kaynak = _varlik(db_session, asset_tag="B002-2", serial="DOGRU",
                     notes="kaynak notu")

    mukerrer.birlestir(db_session, hedef.id, [kaynak.id],
                       secimler={"serial": kaynak.id, "notes": hedef.id})
    assert hedef.serial == "DOGRU"          # seçilen kaynak değeri
    assert hedef.notes == "hedef notu"      # hedefin değeri seçilmişti


def test_zimmet_secilen_kayittan_devralinir(db_session):
    from app import models

    ali = models.User(first_name="ALİ", last_name="VELİ")
    ayse = models.User(first_name="AYŞE", last_name="YILMAZ")
    db_session.add_all([ali, ayse])
    db_session.commit()

    hedef = _varlik(db_session, asset_tag="B003",
                    assigned_type=models.AssignedType.user,
                    assigned_user_id=ali.id)
    kaynak = _varlik(db_session, asset_tag="B003-2",
                     assigned_type=models.AssignedType.user,
                     assigned_user_id=ayse.id)

    # Seçim yoksa hedefin zimmeti korunur (dolu veriye dokunulmaz)
    sonuc = mukerrer.birlestir(db_session, hedef.id, [kaynak.id])
    assert hedef.assigned_user_id == ali.id
    assert "B003-2" in sonuc["silinen"]


def test_zimmet_secimi_kaynaktan_alinir(db_session):
    from app import models

    ali = models.User(first_name="ALİ", last_name="VELİ")
    ayse = models.User(first_name="AYŞE", last_name="YILMAZ")
    db_session.add_all([ali, ayse])
    db_session.commit()
    hedef = _varlik(db_session, asset_tag="B003",
                    assigned_type=models.AssignedType.user,
                    assigned_user_id=ali.id)
    kaynak = _varlik(db_session, asset_tag="B003-2",
                     assigned_type=models.AssignedType.user,
                     assigned_user_id=ayse.id)

    mukerrer.birlestir(db_session, hedef.id, [kaynak.id],
                       secimler={"zimmet": kaynak.id})
    assert hedef.assigned_user_id == ayse.id
    assert hedef.assigned_type == models.AssignedType.user


def test_api_secimlerle_birlestirir(client):
    a = client.post("/assets", json={"asset_tag": "B005", "serial": "ESKI"}).json()
    b = client.post("/assets", json={"asset_tag": "B005-2",
                                     "demirbas_no": "D5"}).json()
    r = client.post("/assets/mukerrer/birlestir",
                    json={"hedef_id": a["id"], "kaynak_idler": [b["id"]],
                          "secimler": {"demirbas_no": b["id"]}})
    assert r.status_code == 200, r.text
    kalan = client.get(f"/assets/{a['id']}").json()
    assert kalan["serial"] == "ESKI" and kalan["demirbas_no"] == "D5"
