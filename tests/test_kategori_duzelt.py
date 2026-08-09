"""kategori-duzelt betiği: yanlış kategorideki modelleri bulup taşıma.

Betik tire içerdiği için normal import edilemez — test_nginx_ekle'deki gibi
importlib ile yüklenir. Veritabanı testleri db_session fikstürüyle döner;
betiğin main() içindeki SessionLocal hiç devreye girmez.
"""

import importlib.util
from pathlib import Path

from app import models

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "kategori-duzelt.py"
_spec = importlib.util.spec_from_file_location("kategori_duzelt", _YOL)
kd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kd)


def _ligowave_sahnesi(db):
    """Gerçek durumun kopyası: LigoWave linkleri 'Projeksiyon' kategorisinde."""
    kat = models.Category(name="Projeksiyon")
    marka = models.Manufacturer(name="LigoWave")
    db.add_all([kat, marka])
    db.flush()
    mdl = models.AssetModel(name="LigoDLB 5-15", category_id=kat.id,
                            manufacturer_id=marka.id)
    db.add(mdl)
    db.flush()
    db.add_all([
        models.Asset(asset_tag="LGW-1", name="LigoWave LigoDLB 5-15",
                     model_id=mdl.id),
        models.Asset(asset_tag="LGW-2", name="LigoWave LigoDLB 5-15",
                     model_id=mdl.id),
    ])
    db.commit()
    return mdl


def test_yanlis_kategorideki_model_onerilir(db_session):
    mdl = _ligowave_sahnesi(db_session)
    oneriler = kd.oneri_listesi(db_session)
    assert len(oneriler) == 1
    o = oneriler[0]
    assert o["model"].id == mdl.id
    assert o["tahmin"] == "ptp"
    assert o["eski_kategori"] == "Projeksiyon"
    assert o["yeni_kategori_adi"] == "Noktadan Noktaya Link"
    assert o["adet"] == 2


def test_uygula_kategori_acar_tasir_ve_idempotenttir(db_session):
    mdl = _ligowave_sahnesi(db_session)
    acilan = kd.uygula(db_session, kd.oneri_listesi(db_session))
    assert acilan == 1
    db_session.refresh(mdl)
    kat = db_session.get(models.Category, mdl.category_id)
    assert kat.name == "Noktadan Noktaya Link"
    assert kd.oneri_listesi(db_session) == []     # ikinci koşuş: öneri yok


def test_hedef_kategori_farkli_yazimla_varsa_yenisi_acilmaz(db_session):
    mdl = _ligowave_sahnesi(db_session)
    hazir = models.Category(name="NOKTADAN NOKTAYA LİNK")
    db_session.add(hazir)
    db_session.commit()
    acilan = kd.uygula(db_session, kd.oneri_listesi(db_session))
    assert acilan == 0
    db_session.refresh(mdl)
    assert mdl.category_id == hazir.id


def test_marka_ile_birlesik_ad_da_ipucu_sayilir(db_session):
    """Model adı tek başına tür söylemese de 'marka + ad' söyleyebilir."""
    kat = models.Category(name="Projeksiyon")
    marka = models.Manufacturer(name="LigoWave")
    db_session.add_all([kat, marka])
    db_session.flush()
    db_session.add(models.AssetModel(name="PRO 5-20n", category_id=kat.id,
                                     manufacturer_id=marka.id))
    db_session.commit()
    assert [o["tahmin"] for o in kd.oneri_listesi(db_session)] == ["ptp"]


def test_cihaz_adlari_yedek_ipucu(db_session):
    """Model/marka tür söylemiyorsa cihaz adlarına bakılır — hepsi aynıysa."""
    kat = models.Category(name="Projeksiyon")
    db_session.add(kat)
    db_session.flush()
    mdl = models.AssetModel(name="DLB 5-90n", category_id=kat.id)
    db_session.add(mdl)
    db_session.flush()
    db_session.add(models.Asset(asset_tag="LNK-1", name="LigoWave DLB 5-90n",
                                model_id=mdl.id))
    db_session.commit()
    assert [o["tahmin"] for o in kd.oneri_listesi(db_session)] == ["ptp"]


def test_celisen_cihaz_adlari_tahmin_uretmez(db_session):
    kat = models.Category(name="Projeksiyon")
    db_session.add(kat)
    db_session.flush()
    mdl = models.AssetModel(name="Karışık Model", category_id=kat.id)
    db_session.add(mdl)
    db_session.flush()
    db_session.add_all([
        models.Asset(asset_tag="KRS-1", name="LigoWave Link", model_id=mdl.id),
        models.Asset(asset_tag="KRS-2", name="POE Switch 24 Port",
                     model_id=mdl.id),
    ])
    db_session.commit()
    assert kd.oneri_listesi(db_session) == []


def test_dogru_kategori_ve_sistem_disi_modeller_dokunulmaz(db_session):
    sw_kat = models.Category(name="Switch")
    pc_kat = models.Category(name="Dizüstü Bilgisayar")
    db_session.add_all([sw_kat, pc_kat])
    db_session.flush()
    db_session.add_all([
        # Zaten doğru türde: switch → switch
        models.AssetModel(name="HP Switch 1920", category_id=sw_kat.id),
        # Sistem ürünü değil: tür çıkmaz
        models.AssetModel(name="HP ProBook 450", category_id=pc_kat.id),
    ])
    db_session.commit()
    assert kd.oneri_listesi(db_session) == []
