"""IFS sabit kıymet dökümünün envantere işlenmesi (scripts/ifs-aktar.py)."""

import datetime as dt
import importlib.util
from pathlib import Path

import openpyxl
import pytest

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "ifs-aktar.py"
_spec = importlib.util.spec_from_file_location("ifs_aktar", _YOL)
ifs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ifs)

BASLIK = ["Nesne No", "Acıklama", "Note", "Aıt Oldugu Sıte", "Mevcut Sıte",
          "Malzeme No", "Grup No", "Tedarıkcı", "Tedarıkcı Adı",
          "Mevcut Pozısyon", "Satınalma Tarıhı", "Satınalma Malıyetı",
          "Teknık Sınıf", "Teknık Sınıf Acıklaması", "Ozellık",
          "Ozellık Acıklaması", "Deger Metnı", "Bılgı"]


def _rapor(tmp_path: Path, satirlar: list[list]) -> Path:
    """IFS'in ürettiği uzun biçimli raporu taklit eden xlsx üretir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(BASLIK)
    for s in satirlar:
        ws.append(s)
    yol = tmp_path / "ifs.xlsx"
    wb.save(yol)
    return yol


def _satir(nesne, ozellik, deger="", bilgi="", *, aciklama="Dizüstü Bilgisayar",
           site="U038", tedarikci="ABC Bilişim", tarih=None, maliyet=None):
    """Tek özellik satırı (IFS her özelliği ayrı satırda verir)."""
    return [nesne, aciklama, "", "A001", site, "S255-0001", "", "", tedarikci,
            "U038 sitesinde", tarih, maliyet, "S55101", "Bilgisayar Sistemleri",
            "O002", ozellik, deger, bilgi]


# --------------------------------------------------------------------------- #
# Ayrıştırma
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ham, beklenen", [
    ("M0098-EVEREST", "EVEREST"),
    ("M0018-LENOVO", "LENOVO"),
    ("M0019 - ASUS", "ASUS"),
    ("HP", "HP"),                       # kodsuz gelen marka bozulmaz
    ("", ""),
])
def test_marka_ayikla(ham, beklenen):
    assert ifs.marka_ayikla(ham) == beklenen


@pytest.mark.parametrize("deger, bilgi, beklenen", [
    ("YB06781439", "", "YB06781439"),
    ("", "H9N0CV07C962370", "H9N0CV07C962370"),
    ("", "WB09071410 P/N: 59354223", "WB09071410"),   # parça no ayıklanır
    ("", "SERİ NO: PF0NRS1Q", "PF0NRS1Q"),
    ("", "", ""),
])
def test_seri_ayikla(deger, bilgi, beklenen):
    assert ifs.seri_ayikla(deger, bilgi) == beklenen


def test_model_ayikla_kisa_ad_ve_tam_metin():
    tam = "Z50-70 Model Name: 20354 MTM: 59432107 MO: YB04101586"
    assert ifs.model_ayikla("", tam) == ("Z50-70", tam)
    assert ifs.model_ayikla("", "ASUS X542UR") == ("ASUS X542UR", "ASUS X542UR")
    assert ifs.model_ayikla("HYUNDAI ROBEX 170W-7", "") == (
        "HYUNDAI ROBEX 170W-7", "HYUNDAI ROBEX 170W-7")
    assert ifs.model_ayikla("", "") == ("", "")


def test_ozellik_gruplari_uygulama_gruplarina_dagitir():
    gruplar = ifs.ozellik_gruplari({
        "İŞLEMCİ MARKA / MODEL": ("İntel i5", "Intel(R) Core(TM) i5-4210U"),
        "RAM TİPİ": ("16 GB", "DDR4 SDRAM"),
        "HDD BILGISI": ("1000GB", "Western Digital WD10EZEX SERİ NO:WD-WCC6Y4NK"),
        "EKRAN KARTI": ("NVIDA", "GeForce GTX 1050"),
        "ANAKART": ("", "ASUS H110M-K"),
        "EKRAN BOYUTU": ('15.6"', ""),
        "PLAKA NO": ("34 AB 1037", ""),
        "KULLANIM DURUMU": ("Kullanimda", ""),
    })
    assert gruplar["İşlemci"] == {
        "İşlemci Markası": "İntel i5",
        "İşlemci (Bütün)": "Intel(R) Core(TM) i5-4210U"}
    assert gruplar["Bellek"]["Ram Kapasitesi"] == "16 GB"
    assert "DDR4" in gruplar["Bellek"]["Ram (Bütün)"]
    # Disk serisi metnin içinden ayıklanır
    assert gruplar["Depolama"]["Harddisk Serial"] == "WD-WCC6Y4NK"
    assert gruplar["Anakart / Ekran Kartı"]["Ana Kart"] == "ASUS H110M-K"
    assert gruplar["Ekran"]["Ekran Boyutu"] == '15.6"'
    assert gruplar["Diğer"]["Plaka No"] == "34 AB 1037"
    assert gruplar["Diğer"]["IFS Kullanım Durumu"] == "Kullanimda"


def test_ifs_oku_satirlari_nesnede_birlestirir(tmp_path):
    yol = _rapor(tmp_path, [
        _satir("FRM-1", "MARKA", "M0018-LENOVO", tarih=dt.datetime(2023, 5, 4),
               maliyet=12000),
        _satir("FRM-1", "MODEL", "", "ideapad 310"),
        _satir("FRM-1", "ŞASİ NO/SERİ NO", "PF0NRS1Q"),
        _satir("FRM-1", "CIHAZ KODU", "N244"),
        _satir("FRM-2", "MARKA", "M0019-ASUS", aciklama="Monitör"),
        # Boş özellik satırı: nesne yine listelenir ama özelliği olmaz
        ["FRM-3", "Ranza", "", "A001", "U030", "S1", "", "", "", "", None,
         None, "", "", "", "", "", ""],
    ])
    kayitlar = {k["nesne_no"]: k for k in ifs.dosya_oku(yol)[0]}
    assert set(kayitlar) == {"FRM-1", "FRM-2", "FRM-3"}

    bir = kayitlar["FRM-1"]
    assert bir["aciklama"] == "Dizüstü Bilgisayar" and bir["site"] == "U038"
    assert bir["oz"]["CIHAZ KODU"][0] == "N244"
    assert bir["oz"]["MODEL"][1] == "ideapad 310"
    # Teknik verisi olmayan nesne "ilginç" değildir (mobilya elenir)
    assert ifs.ilginc_mi(bir) and not ifs.ilginc_mi(kayitlar["FRM-3"])


# --------------------------------------------------------------------------- #
# Eşleştirme ve zenginleştirme
# --------------------------------------------------------------------------- #
def _kayit(**ozellikler) -> dict:
    return {"nesne_no": ozellikler.pop("nesne_no", "FRM-1"),
            "aciklama": "Dizüstü Bilgisayar", "note": "", "site": "U038",
            "malzeme": "", "tedarikci": "", "pozisyon": "",
            "tarih": None, "maliyet": None, "sinif": "Bilgisayar Sistemleri",
            "oz": {ad: (d, b) for ad, (d, b) in ozellikler.items()}}


def test_eslestirme_sirasi(db_session):
    from app import models

    kod = models.Asset(asset_tag="N244")
    seri = models.Asset(asset_tag="ESKI-1", serial="PF0NRS1Q")
    ifsli = models.Asset(asset_tag="ESKI-2", muhasebe_kodu="FRM-9")
    db_session.add_all([kod, seri, ifsli])
    db_session.commit()

    etiketler = {"n244": kod}
    seriler = {"PF0NRS1Q": seri}
    ifs_kodlari = {"FRM-9": ifsli}

    # 1) Cihaz kodu en güçlü ölçüt
    varlik, olcut = ifs.eslestir(
        _kayit(**{"CIHAZ KODU": ("N244", ""), "ŞASİ NO/SERİ NO": ("PF0NRS1Q", "")}),
        etiketler, seriler, ifs_kodlari)
    assert varlik is kod and olcut == "cihaz kodu"

    # 2) Kod yoksa seri no (boşluk/tire farkı önemsiz)
    varlik, olcut = ifs.eslestir(
        _kayit(**{"ŞASİ NO/SERİ NO": ("pf0-nrs1q", "")}),
        etiketler, seriler, ifs_kodlari)
    assert varlik is seri and olcut == "seri no"

    # 3) Hiçbiri yoksa daha önce yazılmış IFS kodu (tekrar çalıştırma)
    varlik, olcut = ifs.eslestir(_kayit(nesne_no="FRM-9"),
                                 etiketler, seriler, ifs_kodlari)
    assert varlik is ifsli and olcut == "IFS no"

    # 4) Eşleşme yoksa None
    assert ifs.eslestir(_kayit(nesne_no="FRM-X"), etiketler, seriler,
                        ifs_kodlari)[0] is None


def test_dolu_alanlar_korunur(db_session):
    from app import models
    from app.excel.ice_aktar import _Onbellek

    varlik = models.Asset(asset_tag="N244", serial="ELLE-GIRILEN",
                          muhasebe_kodu=None)
    db_session.add(varlik)
    db_session.commit()

    kayit = _kayit(**{"ŞASİ NO/SERİ NO": ("PF0NRS1Q", "")})
    kayit["tarih"] = dt.datetime(2023, 5, 4)
    kayit["maliyet"] = 12000

    yeni, marka, model_adi = ifs.degisiklikler(
        varlik, kayit, _Onbellek(db_session), uzerine_yaz=False)
    # Dolu seri no korunur, boş alanlar dolar
    assert "serial" not in yeni
    assert yeni["muhasebe_kodu"][1] == "FRM-1"
    assert yeni["purchase_date"][1] == dt.date(2023, 5, 4)
    assert float(yeni["purchase_cost"][1]) == 12000.0

    # --uzerine-yaz verilirse seri no da güncellenir
    yeni2, _, _ = ifs.degisiklikler(varlik, kayit, _Onbellek(db_session),
                                    uzerine_yaz=True)
    assert yeni2["serial"] == ("ELLE-GIRILEN", "PF0NRS1Q")


def test_ozellikler_birlesir_mevcut_deger_bozulmaz(db_session):
    from app import models

    varlik = models.Asset(asset_tag="N244",
                          custom={"İşlemci": {"İşlemci Markası": "ELLE YAZILDI"}})
    db_session.add(varlik)
    db_session.commit()

    gruplar = ifs.ozellik_gruplari({
        "İŞLEMCİ MARKA / MODEL": ("İntel i5", "Intel Core i5-4210U"),
        "RAM TİPİ": ("16 GB", "DDR4"),
    })
    sayi = ifs.ozellik_birlestir(varlik, gruplar, uzerine_yaz=False)
    assert sayi > 0
    # Elle girilen değer korunur, eksikler eklenir
    assert varlik.custom["İşlemci"]["İşlemci Markası"] == "ELLE YAZILDI"
    assert varlik.custom["İşlemci"]["İşlemci (Bütün)"] == "Intel Core i5-4210U"
    assert varlik.custom["Bellek"]["Ram Kapasitesi"] == "16 GB"

    ifs.ozellik_birlestir(varlik, gruplar, uzerine_yaz=True)
    assert varlik.custom["İşlemci"]["İşlemci Markası"] == "İntel i5"


def test_kategori_adi_sistem_urununu_taniyor():
    assert ifs.kategori_adi({"aciklama": "Erişim Noktası Cihazı (Access Point)"}) \
        == "Access Point"
    assert ifs.kategori_adi({"aciklama": "Ip Kamera"}) == "IP Kamera"
    # Sistem ürünü olmayanlar normal kategori adlandırmasına düşer
    assert ifs.kategori_adi({"aciklama": "Dizüstü Bilgisayar"}) \
        == "Dizüstü Bilgisayar"


# --------------------------------------------------------------------------- #
# Zimmet listesi (geniş biçim) — her satır bir cihaz
# --------------------------------------------------------------------------- #
GENIS_BASLIK = ["Cıhaz Kodu", "Serı Nesne Kodu", "Serı Nesne Adı", "Ilk Proje",
                "Mevcut Proje", "Kısı", "Marka", "Model", "Sası No", "Serı No",
                "Islemcı Marka", "Islemcı Model", "Ram", "Ram Tıpı",
                "Ekran Kartı", "Ekran Kartı Modelı", "Hdd", "Hdd Modelı"]


def _zimmet_raporu(tmp_path: Path, satirlar: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(GENIS_BASLIK)
    for s in satirlar:
        ws.append(s)
    yol = tmp_path / "zimmet.xlsx"
    wb.save(yol)
    return yol


def test_zimmet_listesi_okunur(tmp_path):
    yol = _zimmet_raporu(tmp_path, [
        ["N141", "FRM-0002-DVR-2551902994", "Dizüstü Bilgisayar", "U011",
         "U039", "SERHAT CEMİL ÖZPAK", "M0018-LENOVO", "", "PF0J10UT",
         "MTM: 80SM009YTX MO: PF9XB6911026", "İntel i5",
         "Intel(R) Core(TM) i5-6200U", "12 GB", "4 + 8 Gbytes Kingston DDR4",
         "", "Intel HD Graphics 520", "", ""],
        ["M066", "FRM-0002-DVR-2551900702", "Monitör", "U013", "U023",
         "YUNUS EMRE YILMAZ", "M0026-AOC", "", "FUAE1HA035655", "",
         "", "", "", "", "", "", "", ""],
    ])
    kayitlar, bicim = ifs.dosya_oku(yol)
    assert bicim == "zimmet listesi" and len(kayitlar) == 2

    k = kayitlar[0]
    assert k["nesne_no"] == "FRM-0002-DVR-2551902994"
    assert k["aciklama"] == "Dizüstü Bilgisayar"
    assert k["site"] == "U039" and k["ilk_site"] == "U011"
    assert k["kisi"] == "SERHAT CEMİL ÖZPAK"
    assert k["oz"]["CIHAZ KODU"][0] == "N141"
    # Şasi no gerçek seri numarasıdır; "Seri No" sütunundaki MTM/MO kodları
    # seri sanılmaz ama not olarak saklanır
    assert ifs.seri_ayikla(*k["oz"]["ŞASİ NO/SERİ NO"]) == "PF0J10UT"
    gruplar = ifs.ozellik_gruplari(k["oz"])
    assert gruplar["İşlemci"] == {"İşlemci Markası": "İntel i5",
                                  "İşlemci (Bütün)": "Intel(R) Core(TM) i5-6200U"}
    assert gruplar["Bellek"]["Ram Kapasitesi"] == "12 GB"
    assert "Kingston" in gruplar["Bellek"]["Ram (Bütün)"]
    assert "MTM" in gruplar["Diğer"]["IFS Şasi / Seri Notu"]

    # Monitörde şasi no seri numarası olarak alınır
    assert ifs.seri_ayikla(*kayitlar[1]["oz"]["ŞASİ NO/SERİ NO"]) == "FUAE1HA035655"


def test_uzun_ve_genis_bicim_ayirt_edilir(tmp_path):
    """Aynı betik iki IFS raporunu da okur; biçimi başlıktan anlar."""
    (tmp_path / "a").mkdir()
    uzun = _rapor(tmp_path / "a", [_satir("FRM-1", "MARKA", "M0018-LENOVO")])
    assert ifs.dosya_oku(uzun)[1] == "seri nesne özellikleri"

    (tmp_path / "b").mkdir()
    genis = _zimmet_raporu(tmp_path / "b", [
        ["N141", "FRM-1", "Dizüstü Bilgisayar", "U011", "U039", "AD SOYAD",
         "", "", "", "", "", "", "", "", "", "", "", ""]])
    assert ifs.dosya_oku(genis)[1] == "zimmet listesi"


def test_zimmet_karari(db_session):
    """Cihaz başkasındaysa sessizce el değiştirmez."""
    from app import models

    kisi = models.User(first_name="YUNUS EMRE", last_name="YILMAZ")
    baska = models.User(first_name="BAŞKA", last_name="KİŞİ")
    db_session.add_all([kisi, baska])
    db_session.commit()

    bosta = models.Asset(asset_tag="M066")
    ayni = models.Asset(asset_tag="M067", assigned_type=models.AssignedType.user,
                        assigned_user_id=kisi.id)
    baskasinda = models.Asset(asset_tag="M068",
                              assigned_type=models.AssignedType.user,
                              assigned_user_id=baska.id)
    db_session.add_all([bosta, ayni, baskasinda])
    db_session.commit()

    assert ifs.zimmet_karari(bosta, kisi, degistir=False) == "yaz"
    assert ifs.zimmet_karari(ayni, kisi, degistir=False) == "ayni"
    assert ifs.zimmet_karari(baskasinda, kisi, degistir=False) == "baskasinda"
    # --zimmet-degistir verilirse IFS kazanır
    assert ifs.zimmet_karari(baskasinda, kisi, degistir=True) == "yaz"
    # Personel kaydı yoksa zimmet yazılmaz
    assert ifs.zimmet_karari(bosta, None, degistir=True) == "kisi-yok"
