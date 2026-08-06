"""Kurumun Excel envanter formatının şeması ve normalizasyon kuralları.

Excel sütunları üç gruba ayrılır:
  1. Doğrudan varlık alanına yazılanlar  (ALAN_ESLEME)
  2. Referans tabloya çevrilenler          (marka, model, lokasyon, kullanıcı…)
  3. Teknik özellik olarak `custom` JSON'a yazılanlar (OZELLIK_GRUPLARI)
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------- #
# Doğrudan Asset sütunlarına eşlenen Excel başlıkları
# --------------------------------------------------------------------------- #
ALAN_ESLEME: dict[str, str] = {
    "Cihaz NO": "asset_tag",
    "Serial": "serial",
    "IFS KOD": "muhasebe_kodu",
    "Fatura No": "fatura_no",
    "IP": "ip_address",
    "Açıklama": "notes",
}

# Referans tablolara / ilişkilere giden sütunlar
MARKA = "Marka"
MODEL = "Model"
CIHAZ_TIPI = "Cihaz Tipi"
KULLANICI = "Kullanıcı Adı"
LOKASYON = "Bulunduğu Yer"
BIRIM = "Kullanılan Birim"
UNVAN = "Unvan"
SIRKET = "Alınan Şirket"
TEDARIKCI = "Tedarikçi Firma Adı"
FATURA_TARIHI = "Fatura Tarihi"
FIYAT_TL = "Fiyat (TL)"
FIYAT_USD = "Fiyat (USD)"

# --------------------------------------------------------------------------- #
# `custom` JSON'a gruplanarak yazılan teknik özellikler
# --------------------------------------------------------------------------- #
OZELLIK_GRUPLARI: dict[str, list[str]] = {
    "İşlemci": [
        "İşlemci (Bütün)", "İşlemci Markası", "İşlemci Modeli", "İşlemci Hızı (GHZ)",
    ],
    "Bellek": [
        "Ram (Bütün)", "Ram Markası", "Ram Kapasitesi (mB)", "Ram DDR", "Ram Hızı (Mhz)",
    ],
    "Depolama": [
        "Harddisk (Bütün)", "Harddisk Tipi", "Harddisk Markası", "Harddisk Modeli",
        "Harddisk Kapasitesi", "RPM", "Harddisk Serial",
    ],
    "Anakart / Ekran Kartı": [
        "Ana Kart", "Ekran Kartı (Bütün)", "Ekran Kartı Marka", "Ekran Kartı Kapasite",
    ],
    "Ekran": [
        "Dizüstü Ekran Boyut", "Dizüstü Ekran Çözünürlük",
        "1. Ekran Markası", "1. Ekran Serial", "1. Ekran Modeli", "1. Ekran Boyutu",
        "1. Ekran Çözünürlüğü", "1. Ekran Ek Özellik",
        "2. Ekran Kodu", "2. Ekran Serial", "2. Ekran Markası ve Modeli",
        "2. Ekran Boyutu", "2. Ekran Çözünürlüğü",
    ],
    "Yazılım": [
        "İşletim Sistemi", "Ms Office Versiyon", "Autocad Versiyon",
        "Primavera Versiyon", "MS Project Versiyon", "Netcad Versiyon",
        "SAP Versiyon", "Probina Versiyon", "Microsoft Visio Versiyon",
    ],
    "Satın Alma": [
        "SAS Ref", "Kur", "Fiyat (USD)", "Transfer Geldiği Birim", "Transfer Tarihi",
    ],
    "Diğer": [
        "Eski Makine Açıklama", "Unvan", "Kullanılan Birim",
    ],
}

# Tüm bilinen başlıklar (bilinmeyenler "Ek Bilgi" grubuna düşer)
BILINEN = (
    set(ALAN_ESLEME)
    | {MARKA, MODEL, CIHAZ_TIPI, KULLANICI, LOKASYON, BIRIM, UNVAN, SIRKET,
       TEDARIKCI, FATURA_TARIHI, FIYAT_TL, FIYAT_USD}
    | {b for grup in OZELLIK_GRUPLARI.values() for b in grup}
)

# --------------------------------------------------------------------------- #
# Başlıksız dosyalar için standart sütun sırası
# --------------------------------------------------------------------------- #
# Bazı Excel dosyalarında başlık satırı yoktur (veri 1. satırdan başlar) ama
# sütun düzeni aynıdır. O dosyalar bu sırayla yorumlanır.
STANDART_SUTUNLAR: list[str] = [
    'Eski Makine Açıklama',
    'Cihaz Tipi',
    'Cihaz NO',
    'Serial',
    'IFS KOD',
    'Transfer Geldiği Birim',
    'Transfer Tarihi',
    'Bulunduğu Yer',
    'Kullanılan Birim',
    'Unvan',
    'Kullanıcı Adı',
    'IP',
    'Marka',
    'Model',
    'Fatura Tarihi',
    'Fatura No',
    'SAS Ref',
    'Tedarikçi Firma Adı',
    'Alınan Şirket',
    'Fiyat (USD)',
    'Fiyat (TL)',
    'Kur',
    'İşletim Sistemi',
    'İşlemci (Bütün)',
    'İşlemci Markası',
    'İşlemci Modeli',
    'İşlemci Hızı (GHZ)',
    'Ram (Bütün)',
    'Ram Markası',
    'Ram Kapasitesi (mB)',
    'Ram DDR',
    'Ram Hızı (Mhz)',
    'Harddisk (Bütün)',
    'Harddisk Tipi',
    'Harddisk Markası',
    'Harddisk Modeli',
    'Harddisk Kapasitesi',
    'RPM',
    'Harddisk Serial',
    'Ana Kart',
    'Ekran Kartı (Bütün)',
    'Ekran Kartı Marka',
    'Ekran Kartı Kapasite',
    'Dizüstü Ekran Boyut',
    'Dizüstü Ekran Çözünürlük',
    '1. Ekran Markası',
    '1. Ekran Serial',
    '1. Ekran Modeli',
    '1. Ekran Boyutu',
    '1. Ekran Çözünürlüğü',
    '1. Ekran Ek Özellik',
    '2. Ekran Kodu',
    '2. Ekran Serial',
    '2. Ekran Markası ve Modeli',
    '2. Ekran Boyutu',
    '2. Ekran Çözünürlüğü',
    'Ms Office Versiyon',
    'Autocad Versiyon',
    'Primavera Versiyon',
    'MS Project Versiyon',
    'Netcad Versiyon',
    'SAP Versiyon',
    'Probina Versiyon',
    'Microsoft Visio Versiyon',
    'Açıklama',
]

# --------------------------------------------------------------------------- #
# Cihaz tipi normalizasyonu
# --------------------------------------------------------------------------- #
# Excel'de aynı tür farklı yazımlarla geçiyor: "Ip Kamera", "İp Kamera",
# "ip Kamera"… Türkçe I/İ sorunu nedeniyle basit lower() yetmez.
TIP_ESLEME: dict[str, str] = {
    "ip kamera": "IP Kamera",
    "kamera": "IP Kamera",
    "kamera speed dome": "IP Kamera (Speed Dome)",
    "konferans": "Konferans Kamerası",
    "konferans kamera": "Konferans Kamerası",
    "nvr kayit cihazi": "NVR Kayıt Cihazı",
    "nvr hard disk": "NVR Diski",
    "hardisk": "Harddisk",
    "harddisk": "Harddisk",
    "dizustu bilgisayar": "Dizüstü Bilgisayar",
    "masaustu bilgisayar": "Masaüstü Bilgisayar",
    "monitor": "Monitör",
    "switch": "Switch",
    "hub": "Hub",
    "access point": "Access Point",
    "firewall": "Güvenlik Duvarı",
    "guvenlik duvari": "Güvenlik Duvarı",
    "personel kart okuyucu": "Personel Kart Okuyucu",
    "usb kart okuyucu": "USB Kart Okuyucu",
    "yansitici": "Projeksiyon",
    "projeksiyon": "Projeksiyon",
    "regulator": "Regülatör",
    "ups": "UPS",
    "total station": "Total Station",
    "yazici": "Yazıcı",
    "netcad": "Netcad Lisansı",
    "bluetooth hoparlor/mikrofon": "Bluetooth Hoparlör/Mikrofon",
}


def _sadelestir(metin: str) -> str:
    """Türkçe karakterleri ASCII'ye indirger, küçük harfe çevirir."""
    esleme = str.maketrans("ıİışŞğĞüÜöÖçÇ", "iiisSgGuUoOcC")
    metin = metin.translate(esleme)
    metin = unicodedata.normalize("NFKD", metin).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", metin).strip().lower()


def cihaz_tipi_normalle(ham: str) -> str:
    """Farklı yazımları tek bir kategori adına indirger."""
    if not ham:
        return "Diğer"
    sade = _sadelestir(ham)

    # Parantez içi açıklamaları at: "İp Kamera (değiştirildi)" -> "ip kamera"
    cekirdek = re.sub(r"\(.*?\)", "", sade).strip()
    cekirdek = re.sub(r"[-–].*$", "", cekirdek).strip()

    if cekirdek in TIP_ESLEME:
        return TIP_ESLEME[cekirdek]
    if sade in TIP_ESLEME:
        return TIP_ESLEME[sade]
    # "kamera" geçen her şey IP Kamera sayılır (speed dome hariç yukarıda)
    if "kamera" in cekirdek and "konferans" not in cekirdek:
        return "IP Kamera"
    # Bilinmeyen: ilk harfleri büyüterek olduğu gibi kullan
    return " ".join(w.capitalize() for w in ham.split()) or "Diğer"


def ad_normalle(ham: str) -> str:
    """Kişi/yer adındaki fazla boşlukları temizler."""
    return re.sub(r"\s+", " ", (ham or "").strip())


# "Kullanıcı Adı" sütununda kişi yerine yer/not yazılmış olabiliyor.
# Bu kelimelerden biri geçiyorsa kişi sayılmaz. (Büyük harf tek başına
# sinyal DEĞİLDİR — Türkçe kayıtlarda isimler de büyük harfle yazılıyor.)
KISI_OLMAYAN_KELIMELER = {
    # yer
    "oda", "odasi", "depo", "ambar", "santiye", "ofis", "toplanti", "kamp",
    "kampi", "kogus", "kogusu", "saha", "sahasi", "turnike", "kismi",
    "sunucu", "server", "sistem", "kabin", "kabinet", "insaat", "blok",
    # durum / not
    "yedek", "stok", "arsiv", "kullanilmiyor", "bosta", "hurda", "iade",
    "ariza", "arizali", "degistirildi", "degisti", "yenisi", "eski",
    # cihaz
    "pc", "nvr", "dvr", "kamera", "bilgisayar", "yazici", "switch",
}


def kisi_mi(ad: str) -> bool:
    """Değerin bir kişi adı mı yoksa yer/not mu olduğunu belirler.

    Excel'in 'Kullanıcı Adı' sütununda bazen 'Sunucu Odası', 'İNŞAAT SAHASI'
    veya 'yenisi ile değiştirildi' gibi kayıtlar bulunuyor. Bunlar kişi
    olarak açılmamalı; lokasyon veya not olarak ele alınmalı.
    """
    if not ad:
        return False
    # "Eser Pehlivan (Site Plus)" -> "Eser Pehlivan"
    sade = _sadelestir(re.sub(r"\(.*?\)", "", ad))
    kelimeler = sade.split()
    if not kelimeler:
        return False
    if set(kelimeler) & KISI_OLMAYAN_KELIMELER:
        return False
    # Ad Soyad genelde 2-4 kelimedir; daha uzunu açıklama cümlesidir
    if not 2 <= len(kelimeler) <= 4:
        return False
    return all(k.isalpha() for k in kelimeler)
