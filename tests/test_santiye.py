"""Şantiyelerin proje koduna göre ayrı lokasyonlara bölünmesi.

Gerçek veride "Bulunduğu Yer" her satırda aynı genel değerdi ("ŞANTİYE");
şantiye ayrımı "Kullanılan Birim" (U023, U026…) alanında duruyordu. Buradaki
testler hem yeni içe aktarımın hem de geçmiş veriyi düzelten `app.santiye`
modülünün aynı sonucu üretmesini güvenceye alır.
"""

import io

import openpyxl
import pytest

from app import models, santiye
from app.excel import sema


# --------------------------------------------------------------------------- #
# Ad üretimi (birim testleri)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ham,beklenen", [
    ("u023", "U023"),
    (" U023 ", "U023"),
    ("U 023", "U023"),
    ("", None),
    (None, None),
])
def test_proje_kodu_normalle(ham, beklenen):
    assert sema.proje_kodu_normalle(ham) == beklenen


@pytest.mark.parametrize("yer,kod,beklenen", [
    ("ŞANTİYE", "U026", "ŞANTİYE U026"),
    ("ŞANTİYE", None, "ŞANTİYE"),          # kod yoksa yer olduğu gibi kalır
    (None, "U026", "U026"),                # yer yoksa kodun kendisi
    ("ŞANTİYE U026", "U026", "ŞANTİYE U026"),   # kod zaten adın içinde
    ("Şantiye u026", "U026", "Şantiye u026"),   # büyük/küçük harf duyarsız
    (None, None, None),
])
def test_santiye_adi(yer, kod, beklenen):
    assert sema.santiye_adi(yer, kod) == beklenen


# --------------------------------------------------------------------------- #
# Excel içe aktarımı
# --------------------------------------------------------------------------- #
CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _excel(satirlar: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(sema.STANDART_SUTUNLAR)
    for s in satirlar:
        ws.append([s.get(b) for b in sema.STANDART_SUTUNLAR])
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def _aktar(client, satirlar: list[dict]) -> dict:
    on = client.post("/excel/oku",
                     files={"file": ("t.xlsx", io.BytesIO(_excel(satirlar)), CT)})
    assert on.status_code == 200, on.text
    return client.post("/excel/aktar", json={"satirlar": on.json()["satirlar"]}).json()


def _lokasyonlar(client) -> dict[str, str | None]:
    return {l["name"]: l["proje_kodu"] for l in client.get("/locations").json()}


def test_ayni_yer_farkli_proje_ayri_lokasyon_olur(client):
    """Tek bir 'ŞANTİYE' değeri projelere göre bölünmeli."""
    _aktar(client, [
        {"Cihaz NO": "S-1", "Serial": "SS1", "Bulunduğu Yer": "ŞANTİYE",
         "Kullanılan Birim": "U023"},
        {"Cihaz NO": "S-2", "Serial": "SS2", "Bulunduğu Yer": "ŞANTİYE",
         "Kullanılan Birim": "U026"},
        {"Cihaz NO": "S-3", "Serial": "SS3", "Bulunduğu Yer": "ŞANTİYE",
         "Kullanılan Birim": "U026"},
    ])
    lok = _lokasyonlar(client)
    assert lok == {"ŞANTİYE U023": "U023", "ŞANTİYE U026": "U026"}
    assert client.get("/assets/sayi",
                      params={"proje_kodu": "U026"}).json()["toplam"] == 2


def test_kucuk_harfli_kod_ayri_santiye_acmaz(client):
    """'u023' ve 'U023' aynı projedir (Türkçe İ/I tuzağı dahil)."""
    _aktar(client, [
        {"Cihaz NO": "K-1", "Serial": "KS1", "Bulunduğu Yer": "ŞANTİYE",
         "Kullanılan Birim": "U023"},
        {"Cihaz NO": "K-2", "Serial": "KS2", "Bulunduğu Yer": "şantiye",
         "Kullanılan Birim": "u023"},
    ])
    assert list(_lokasyonlar(client)) == ["ŞANTİYE U023"]
    assert client.get("/assets/sayi",
                      params={"proje_kodu": "U023"}).json()["toplam"] == 2


def test_yersiz_satir_projenin_santiyesine_katilir(client):
    """'Bulunduğu Yer' boş olan satır 'U023' diye ikinci lokasyon açmamalı."""
    _aktar(client, [
        {"Cihaz NO": "Y-1", "Serial": "YS1", "Bulunduğu Yer": "ŞANTİYE",
         "Kullanılan Birim": "U023"},
        {"Cihaz NO": "Y-2", "Serial": "YS2", "Kullanılan Birim": "U023"},
    ])
    assert list(_lokasyonlar(client)) == ["ŞANTİYE U023"]
    assert client.get("/assets/sayi",
                      params={"proje_kodu": "U023"}).json()["toplam"] == 2


def test_yersiz_satir_onceki_aktarimin_santiyesine_katilir(client):
    """Şantiye başka bir dosyada oluşmuşsa da tek lokasyon kalmalı."""
    _aktar(client, [{"Cihaz NO": "A-1", "Serial": "AS1",
                     "Bulunduğu Yer": "ŞANTİYE", "Kullanılan Birim": "U023"}])
    _aktar(client, [{"Cihaz NO": "A-2", "Serial": "AS2",
                     "Kullanılan Birim": "U023"}])
    assert list(_lokasyonlar(client)) == ["ŞANTİYE U023"]


def test_yersiz_satir_yalniz_kalirsa_kod_adiyla_acilir(client):
    """Projeye ait başka bilgi yoksa kodun kendisi lokasyon adı olur."""
    _aktar(client, [{"Cihaz NO": "T-1", "Serial": "TS1",
                     "Kullanılan Birim": "U099"}])
    assert _lokasyonlar(client) == {"U099": "U099"}


def test_kodsuz_satir_genel_lokasyonda_kalir(client):
    _aktar(client, [{"Cihaz NO": "N-1", "Serial": "NS1",
                     "Bulunduğu Yer": "MERKEZ DEPO"}])
    assert _lokasyonlar(client) == {"MERKEZ DEPO": None}


# --------------------------------------------------------------------------- #
# Geçmiş veriyi düzeltme (app.santiye.ayir)
# --------------------------------------------------------------------------- #
def _eski_veri(db):
    """Şantiye ayrımı yapılmamış eski hâli kurar: hepsi tek 'ŞANTİYE'de."""
    genel = models.Location(name="ŞANTİYE")
    db.add(genel)
    db.flush()
    for etiket, kod in [("E-1", "U023"), ("E-2", "U023"), ("E-3", "U026"),
                        ("E-4", None)]:
        db.add(models.Asset(
            asset_tag=etiket,
            location_id=genel.id,
            custom={"Diğer": {"Kullanılan Birim": kod}} if kod else {},
        ))
    db.commit()
    return genel


def test_ayir_projelere_boler(db_session):
    _eski_veri(db_session)
    rapor = santiye.ayir(db_session)

    assert rapor["tasinan"] == 3
    assert rapor["kodsuz"] == 1          # kodsuz cihaza dokunulmaz
    assert rapor["olusan"] == 2
    assert {ad: sayi for ad, _, sayi in santiye.santiye_ozeti(db_session)} == {
        "ŞANTİYE": 1, "ŞANTİYE U023": 2, "ŞANTİYE U026": 1,
    }


def test_ayir_kuru_calistirma_yazmaz(db_session):
    genel = _eski_veri(db_session)
    rapor = santiye.ayir(db_session, uygula=False)

    assert rapor["tasinan"] == 3
    assert rapor["olusan"] == 0
    db_session.expire_all()
    assert [l.name for l in db_session.query(models.Location).all()] == ["ŞANTİYE"]
    assert all(a.location_id == genel.id
               for a in db_session.query(models.Asset).all())


def test_ayir_tekrar_calistirilabilir(db_session):
    _eski_veri(db_session)
    santiye.ayir(db_session)
    ilk = santiye.santiye_ozeti(db_session)

    ikinci_rapor = santiye.ayir(db_session)
    assert ikinci_rapor["tasinan"] == 0
    assert ikinci_rapor["olusan"] == 0
    assert santiye.santiye_ozeti(db_session) == ilk


def test_ayir_lokasyonsuz_cihazi_projeye_katar(db_session):
    """Lokasyonsuz cihaz 'U023' diye ayrı bir lokasyon açmamalı."""
    _eski_veri(db_session)
    db_session.add(models.Asset(asset_tag="L-1",
                                custom={"Diğer": {"Kullanılan Birim": "U023"}}))
    db_session.commit()

    santiye.ayir(db_session)
    adlar = {ad for ad, _, _ in santiye.santiye_ozeti(db_session)}
    assert "U023" not in adlar
    assert dict((ad, sayi) for ad, _, sayi in
                santiye.santiye_ozeti(db_session))["ŞANTİYE U023"] == 3


def test_ayir_bosalan_lokasyonun_eski_kodunu_temizler(db_session):
    """Genel 'ŞANTİYE' eski aktarımdan kalan kodu taşımamalı (hayalet filtre)."""
    genel = _eski_veri(db_session)
    genel.proje_kodu = "U023"           # eski içe aktarımın bıraktığı kod
    # kodsuz cihazı da taşı ki lokasyon tamamen boşalsın
    db_session.query(models.Asset).filter_by(asset_tag="E-4").delete()
    db_session.commit()

    rapor = santiye.ayir(db_session)
    assert rapor["temizlenen"] == 1
    db_session.refresh(genel)
    assert genel.proje_kodu is None
    # U023 cihazları genel lokasyona geri düşmemeli
    ozet = {ad: sayi for ad, _, sayi in santiye.santiye_ozeti(db_session)}
    assert "ŞANTİYE" not in ozet and ozet["ŞANTİYE U023"] == 2


def test_ayir_projeye_ozel_lokasyonun_kodu_korunur(db_session):
    """Adı zaten projeye özel olan lokasyonun kodu, boş olsa da silinmez."""
    db_session.add(models.Location(name="ŞANTİYE U030", proje_kodu="U030"))
    _eski_veri(db_session)

    santiye.ayir(db_session)
    l = db_session.query(models.Location).filter_by(name="ŞANTİYE U030").one()
    assert l.proje_kodu == "U030"


def test_ayir_kaynak_secilebilir(db_session):
    """--kaynak yalnızca o lokasyondakileri ayırmalı."""
    _eski_veri(db_session)
    baska = models.Location(name="DEPO")
    db_session.add(baska)
    db_session.flush()
    db_session.add(models.Asset(asset_tag="D-1", location_id=baska.id,
                                custom={"Diğer": {"Kullanılan Birim": "U055"}}))
    db_session.commit()

    santiye.ayir(db_session, kaynak="ŞANTİYE")
    adlar = {ad for ad, _, _ in santiye.santiye_ozeti(db_session)}
    assert "DEPO U055" not in adlar and "DEPO" in adlar
    assert "ŞANTİYE U023" in adlar


def test_birim_farkli_ozellik_gruplarindan_okunur(db_session):
    a = models.Asset(asset_tag="B-1",
                     custom={"Satın Alma": {"X": "1"},
                             "Diğer": {"Kullanilan Birim": "U077"}})
    assert santiye.birim(a) == "U077"
    assert santiye.birim(models.Asset(asset_tag="B-2", custom={})) is None
    assert santiye.birim(models.Asset(asset_tag="B-3")) is None
