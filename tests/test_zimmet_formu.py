"""Demirbaş zimmet formu — kurumun örnek formuna uygunluk.

Örnek form (YILDIZLAR GRUP) tek sayfadır ve şu bölümleri taşır: künye,
Özellikler, Notlar, Kullanıcı Bilgileri, taahhüt metni, TESLİM EDEN /
TESLİM ALAN imza bloğu.
"""

import io
import re

import pypdf
import pytest

from app import models
from app.pdf.zimmet import build_zimmet_pdf, ozellik


def _metin(pdf: bytes) -> str:
    return "\n".join(s.extract_text() for s in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def _duz(pdf: bytes) -> str:
    """Satır sarmalarını yok sayan düz metin (uzun değerler satıra bölünebilir)."""
    return re.sub(r"\s+", " ", _metin(pdf))


def _sayfa_sayisi(pdf: bytes) -> int:
    return len(pypdf.PdfReader(io.BytesIO(pdf)).pages)


@pytest.fixture
def cihaz(db_session):
    marka = models.Manufacturer(name="LENOVO")
    kategori = models.Category(name="Dizüstü Bilgisayar")
    db_session.add_all([marka, kategori])
    db_session.flush()
    model = models.AssetModel(name="IdeaPad Gaming 3", manufacturer_id=marka.id,
                              category_id=kategori.id)
    lokasyon = models.Location(name="ŞANTİYE U023", proje_kodu="U023")
    durum = models.StatusLabel(name="Kullanımda", type=models.StatusType.deployable)
    db_session.add_all([model, lokasyon, durum])
    db_session.flush()
    a = models.Asset(
        asset_tag="FRM-0002", name="Dizüstü Bilgisayar", serial="PF2XDDZL",
        demirbas_no="N411", model_id=model.id, location_id=lokasyon.id,
        status_id=durum.id,
        custom={
            "İşlemci": {"İşlemci (Bütün)": "Intel(R) Core(TM) i5-10300H"},
            "Bellek": {"Ram (Bütün)": "16 GB Kingston DDR4"},
            "Depolama": {"Harddisk (Bütün)": "SSD - HFM512GDHTNI",
                         "Harddisk Kapasitesi": "512 GB"},
            "Anakart / Ekran Kartı": {"Ekran Kartı (Bütün)": "NVIDIA GTX 1650",
                                      "Ana Kart": "LNVNB161216"},
            "Ekran": {"Dizüstü Ekran Boyut": '15,6"'},
            "Yazılım": {"İşletim Sistemi": "Windows 10 Pro"},
        },
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


@pytest.fixture
def personel(db_session):
    k = models.User(first_name="FATMA NUR", last_name="ERTEKİN",
                    employee_num="1031199", email="fatma@ornek.com",
                    department="Bilgi İşlem")
    db_session.add(k)
    db_session.commit()
    db_session.refresh(k)
    return k


# --------------------------------------------------------------------------- #
# Yerleşim
# --------------------------------------------------------------------------- #
def test_form_tek_sayfa(cihaz, personel):
    assert _sayfa_sayisi(build_zimmet_pdf(assets=[cihaz], user=personel)) == 1


def test_ornek_formun_bolumleri_var(cihaz, personel):
    m = _metin(build_zimmet_pdf(assets=[cihaz], user=personel))
    for bolum in ["DEMİRBAŞ ZİMMET FORMU", "Nesne No", "Nesne Açıklama",
                  "Nesne Türü / Kategori", "Özellikler", "Notlar",
                  "Kullanıcı Bilgileri", "TESLİM EDEN", "TESLİM ALAN",
                  "Ad Soyad", "İmza", "Tarih"]:
        assert bolum in m, f"'{bolum}' formda yok"


def test_ozellik_satirlari_ornekle_ayni(cihaz, personel):
    m = _metin(build_zimmet_pdf(assets=[cihaz], user=personel))
    for satir in ["MARKA", "MODEL", "ŞASİ NO / SERİ NO", "KULLANIM DURUMU",
                  "ZİMMETLENEN PERSONEL", "LOKASYON", "KİRALANAN FİRMA",
                  "KAPASİTE", "İŞLEMCİ MARKA / MODEL", "RAM TİPİ",
                  "EKRAN KARTI", "HDD BİLGİSİ", "ANAKART", "EKRAN BOYUTU",
                  "CİHAZ KODU"]:
        assert satir in m, f"'{satir}' özellik satırı yok"


def test_cihaz_verileri_forma_basilir(cihaz, personel):
    m = _metin(build_zimmet_pdf(assets=[cihaz], user=personel))
    for deger in ["FRM-0002", "PF2XDDZL", "N411", "LENOVO", "IdeaPad Gaming 3",
                  "Dizüstü Bilgisayar", "ŞANTİYE U023", "Kullanımda",
                  "512 GB", "Intel(R) Core(TM) i5-10300H", "16 GB Kingston DDR4",
                  "NVIDIA GTX 1650", "LNVNB161216", "Windows 10 Pro"]:
        assert deger in m, f"'{deger}' formda yok"


def test_personel_bilgileri_basilir(cihaz, personel):
    m = _metin(build_zimmet_pdf(assets=[cihaz], user=personel))
    assert "FATMA NUR ERTEKİN" in m
    assert "1031199" in m
    assert "fatma@ornek.com" in m


def test_taahhut_metni_kurum_adini_icerir(cihaz, personel):
    m = _duz(build_zimmet_pdf(assets=[cihaz], user=personel,
                              org_name="YILDIZLAR GRUP"))
    assert "YILDIZLAR GRUP'a ait" in m
    assert "teslim aldım" in m
    assert "emeklilik, istifa veya görevden ayrılma" in m


def test_iade_formu_farkli_baslik_ve_metin(cihaz, personel):
    m = _metin(build_zimmet_pdf(assets=[cihaz], user=personel, doc_type="iade"))
    assert "DEMİRBAŞ İADE FORMU" in m
    assert "iade edilmiş" in m
    assert "teslim aldım" not in m


def test_cihaz_basina_ayri_sayfa(db_session, cihaz, personel):
    """Her cihaz ayrı imzalanır -> her biri kendi sayfasında."""
    ikinci = models.Asset(asset_tag="FRM-0003", name="Monitör")
    db_session.add(ikinci)
    db_session.commit()
    pdf = build_zimmet_pdf(assets=[cihaz, ikinci], user=personel)
    assert _sayfa_sayisi(pdf) == 2
    assert "FRM-0003" in _metin(pdf)


def test_uzun_ozellikler_de_tek_sayfada_kalir(db_session, personel):
    """Uzun ekran kartı/anakart metinleri formu ikinci sayfaya taşırmamalı."""
    a = models.Asset(
        asset_tag="UZUN-1",
        name="Lenovo ideapad 320-15IKB Model Name: 80XL MTM: 80XL00LTTX MO: PF9XB",
        custom={"g": {
            "Ekran Kartı (Bütün)": ("Intel HD Graphics 620 1024 Mbytes + NVIDIA "
                                    "GeForce 920MX (GM108) [Lenovo] 2048 MBytes "
                                    "of GDDR5 SDRAM [Elpida]"),
            "Ram (Bütün)": ("4 + 8 Gbytes Crucial Technology DDR4 SDRAM 1067.2 "
                            "MHz (DDR4-2134 / PC4-17000)"),
            "Ana Kart": "LENOVO LNVNB161216 Intel Kaby Lake-U + iHDCP 2.2 Premium PCH",
            "Harddisk (Bütün)": "SDSSDA240G Sandisk SSD Plus 240GB SATA III 2.5 inch",
        }},
    )
    db_session.add(a)
    db_session.commit()
    pdf = build_zimmet_pdf(assets=[a], user=personel)
    assert _sayfa_sayisi(pdf) == 1
    # Küçültme veriyi kırpmamalı
    assert "GDDR5 SDRAM [Elpida]" in _duz(pdf)


def test_imei_yalniz_telefonlarda_basilir(db_session, personel):
    telefon = models.Asset(asset_tag="TEL-1", imei="356938035643809")
    bilgisayar = models.Asset(asset_tag="PC-1")
    db_session.add_all([telefon, bilgisayar])
    db_session.commit()
    assert "IMEI / HAT NO" in _metin(build_zimmet_pdf(assets=[telefon]))
    assert "IMEI / HAT NO" not in _metin(build_zimmet_pdf(assets=[bilgisayar]))


def test_personelsiz_form_uretilir(cihaz):
    """Boştaki cihaz için de form basılabilmeli (elle doldurulur)."""
    pdf = build_zimmet_pdf(assets=[cihaz])
    assert _sayfa_sayisi(pdf) == 1
    assert "TESLİM ALAN" in _metin(pdf)


# --------------------------------------------------------------------------- #
# Özellik okuma yardımcısı
# --------------------------------------------------------------------------- #
def test_ozellik_grup_farketmeksizin_bulunur(cihaz):
    assert ozellik(cihaz, "Ana Kart") == "LNVNB161216"
    assert ozellik(cihaz, "Yok Böyle Bir Alan") == ""
    # ilk dolu olan kazanır
    assert ozellik(cihaz, "Yok Böyle Bir Alan", "İşletim Sistemi") == "Windows 10 Pro"


def test_ozellik_bos_cihazda_patlamaz():
    assert ozellik(models.Asset(asset_tag="X"), "Ana Kart") == ""


# --------------------------------------------------------------------------- #
# API ucu
# --------------------------------------------------------------------------- #
def test_zimmet_ucu_pdf_dondurur(client):
    a = client.post("/assets", json={"asset_tag": "API-1", "name": "Laptop"}).json()
    r = client.get(f"/documents/zimmet/asset/{a['id']}.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert "DEMİRBAŞ ZİMMET FORMU" in _metin(r.content)


def test_logo_varsa_forma_girer_ve_tek_sayfa_kalir(client, monkeypatch, tmp_path):
    """logo-rapor.png konduğunda fiş logolu üretilmeli, sayfa taşmamalı."""
    from PIL import Image as PILImage

    from app.pdf import zimmet as z

    yol = tmp_path / "logo-rapor.png"
    PILImage.new("RGBA", (600, 420), (0, 61, 53, 255)).save(yol)
    monkeypatch.setattr(z, "LOGO_YOLU", yol)

    kisi = client.post("/users", json={"first_name": "Logo",
                                       "last_name": "Testi"}).json()
    cihaz = client.post("/assets", json={"asset_tag": "LOGO-PDF-1",
                                         "name": "Laptop"}).json()
    client.post(f"/assets/{cihaz['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})

    r = client.get(f"/documents/zimmet/user/{kisi['id']}.pdf")
    assert r.status_code == 200
    assert _sayfa_sayisi(r.content) == 1
    assert "DEMİRBAŞ ZİMMET FORMU" in _metin(r.content)
    # Logosuz üretimden bariz büyük olmalı (görsel gömüldü kanıtı)
    monkeypatch.setattr(z, "LOGO_YOLU", tmp_path / "yok.png")
    logosuz = client.get(f"/documents/zimmet/user/{kisi['id']}.pdf").content
    assert len(r.content) > len(logosuz) + 500
