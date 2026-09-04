"""Cihaz numarası önekinden kategori işleme (scripts/kod-kategori.py)."""

import importlib.util
from pathlib import Path

import pytest

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "kod-kategori.py"
_spec = importlib.util.spec_from_file_location("kod_kategori", _YOL)
kk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kk)

KURALLAR = kk.VARSAYILAN_KURALLAR


@pytest.mark.parametrize("etiket, beklenen", [
    ("N245", "Dizüstü Bilgisayar"),
    ("n245", "Dizüstü Bilgisayar"),          # küçük harf de eşleşir
    ("N019", "Dizüstü Bilgisayar"),
    ("N141-2", "Dizüstü Bilgisayar"),        # mükerrer soneki eşleşmeyi bozmaz
    ("M229", "Monitör"),
    ("M066", "Monitör"),
    ("B002", None),                          # kural yok
    ("NVR-01", None),                        # harften sonra rakam şart
    ("MFC-7360", None),                      # yazıcı modeli dizüstü sanılmasın
    ("", None),
    (None, None),
])
def test_kategori_bul(etiket, beklenen):
    assert kk.kategori_bul(etiket, KURALLAR) == beklenen


def test_kural_coz_ek_kural_alir():
    kurallar = kk.kural_coz(["B=Masaüstü Bilgisayar", "t = Tablet Bilgisayar"])
    assert kurallar["B"] == "Masaüstü Bilgisayar"
    assert kurallar["T"] == "Tablet Bilgisayar"
    assert kurallar["N"] == "Dizüstü Bilgisayar"     # varsayılanlar korunur
    with pytest.raises(ValueError):
        kk.kural_coz(["bozuk-kural"])


def _kur(db):
    """Tekil model, paylaşımlı model, modelsiz cihaz ve kural dışı kayıt."""
    from app import models

    masaustu = models.Category(name="Masaüstü Bilgisayar")
    db.add(masaustu)
    db.flush()
    lenovo = models.Manufacturer(name="LENOVO")
    db.add(lenovo)
    db.flush()
    paylasimli = models.AssetModel(name="Nirvana", category_id=masaustu.id)
    tekil = models.AssetModel(name="Z50-70", category_id=masaustu.id,
                              manufacturer_id=lenovo.id)
    db.add_all([paylasimli, tekil])
    db.flush()
    kayitlar = {
        "N245": models.Asset(asset_tag="N245", model_id=tekil.id),
        "N246": models.Asset(asset_tag="N246", model_id=paylasimli.id),
        "M229": models.Asset(asset_tag="M229"),
        "B002": models.Asset(asset_tag="B002", model_id=paylasimli.id),
        "NVR-01": models.Asset(asset_tag="NVR-01", model_id=paylasimli.id),
    }
    db.add_all(kayitlar.values())
    db.commit()
    return kayitlar, paylasimli, tekil


def _kategori_adi(db, varlik):
    from app import models

    mdl = db.get(models.AssetModel, varlik.model_id) if varlik.model_id else None
    kat = db.get(models.Category, mdl.category_id) if mdl and mdl.category_id else None
    return kat.name if kat else None


def test_oneriler_yalniz_kurala_uymayanlari_listeler(db_session):
    _kur(db_session)
    liste = kk.oneriler(db_session, KURALLAR)
    etiketler = {o["varlik"].asset_tag for o in liste}
    assert etiketler == {"N245", "N246", "M229"}
    n245 = next(o for o in liste if o["varlik"].asset_tag == "N245")
    assert n245["model_tekil"] is True and n245["eski_kategori"] == "Masaüstü Bilgisayar"
    n246 = next(o for o in liste if o["varlik"].asset_tag == "N246")
    assert n246["model_tekil"] is False        # model paylaşımlı
    m229 = next(o for o in liste if o["varlik"].asset_tag == "M229")
    assert m229["model"] is None and m229["eski_kategori"] is None


def test_uygula_modeli_ve_cihazi_dogru_baglar(db_session):
    from app import models

    kayitlar, paylasimli, tekil = _kur(db_session)
    sonuc = kk.uygula(db_session, kk.oneriler(db_session, KURALLAR))
    db_session.expire_all()

    # 1) Tekil model taşındı, markası korundu
    assert _kategori_adi(db_session, kayitlar["N245"]) == "Dizüstü Bilgisayar"
    assert kayitlar["N245"].model_id == tekil.id
    assert db_session.get(models.AssetModel, tekil.id).manufacturer_id is not None

    # 2) Paylaşımlı modeldeki cihaz yeni modele bağlandı, diğerleri bozulmadı
    assert _kategori_adi(db_session, kayitlar["N246"]) == "Dizüstü Bilgisayar"
    assert kayitlar["N246"].model_id != paylasimli.id
    assert kayitlar["B002"].model_id == paylasimli.id
    assert _kategori_adi(db_session, kayitlar["B002"]) == "Masaüstü Bilgisayar"

    # 3) Modelsiz cihaza kategori adıyla model açıldı
    assert _kategori_adi(db_session, kayitlar["M229"]) == "Monitör"

    # 4) NVR-01 kurala girmedi
    assert _kategori_adi(db_session, kayitlar["NVR-01"]) == "Masaüstü Bilgisayar"

    assert sonuc == {"tasinan_model": 1, "acilan_model": 1, "baglanan_cihaz": 1}
    # Değişiklikler cihaz geçmişine yazıldı
    from sqlalchemy import select

    notlar = [g.note for g in db_session.scalars(
        select(models.ActivityLog).where(
            models.ActivityLog.actor == "kod-kategori")).all()]
    assert len(notlar) == 3
    assert any("Masaüstü Bilgisayar → Dizüstü Bilgisayar" in n for n in notlar)


def test_ikinci_calistirma_degisiklik_yapmaz(db_session):
    _kur(db_session)
    kk.uygula(db_session, kk.oneriler(db_session, KURALLAR))
    assert kk.oneriler(db_session, KURALLAR) == []


def test_ek_kuralla_masaustu_de_islenir(db_session):
    kayitlar, *_ = _kur(db_session)
    kurallar = kk.kural_coz(["B=Masaüstü Bilgisayar"])
    liste = kk.oneriler(db_session, kurallar)
    # B002 zaten doğru kategoride: kural eklense de listeye girmez
    assert "B002" not in {o["varlik"].asset_tag for o in liste}
