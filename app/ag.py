"""Teknik sistem ürünleri — tür şablonları ve sorgular.

Başlangıçta yalnızca ağ ürünleri içindi (modül adı ve /ag uçları bu yüzden),
sonradan yangın algılama, alarm ve kart sistemleri de eklendi. Türler
**ailelere** ayrılır:

    AILELER = {"ag": Ağ Ürünleri, "yangin": Yangın Sistemleri,
               "alarm": Alarm Sistemleri, "gecis": Geçiş Sistemleri,
               "kantar": Kantar Sistemi}

Bu ürünler ayrı bir tablo değildir: normal varlıklardır, ama kategorileri
sistem türlerinden biridir ve teknik özellikleri `Asset.custom["Ağ"]` altında
tutulur. Böylece zimmet, dosya eki, etiket basma ve arama aynen çalışır;
ekran yalnızca türe özel bir görünüm sunar.

Her türün kendi alan listesi vardır (switch'te port sayısı ve PoE, dedektörde
algılama tipi ve kapsama alanı gibi) — bkz. `TURLER`.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.excel.sema import _sadelestir

# `custom` içinde ağ özelliklerinin tutulduğu grup adı
GRUP = "Ağ"


class Alan:
    """Bir teknik alanın tanımı (arayüz formunu bundan üretir)."""

    def __init__(self, ad: str, etiket: str, tip: str = "text",
                 secenekler: list[str] | None = None, ipucu: str = ""):
        self.ad = ad
        self.etiket = etiket
        self.tip = tip                      # text | number | secim
        self.secenekler = secenekler or []
        self.ipucu = ipucu

    def sozluk(self) -> dict:
        return {"ad": self.ad, "etiket": self.etiket, "tip": self.tip,
                "secenekler": self.secenekler, "ipucu": self.ipucu}


# Tüm ağ ürünlerinde ortak alanlar
ORTAK = [
    Alan("Parça No", "Parça No", ipucu="örn. HK-SFP-1.25G-1310-DF-MM"),
    Alan("Yönetim IP", "Yönetim IP", ipucu="örn. 10.0.0.2"),
    Alan("Firmware", "Firmware / Yazılım Sürümü"),
]

# Ürün aileleri — menüde ayrı bölüm olarak görünür
AILELER = {
    "ag": {"ad": "Ağ Ürünleri", "ikon": "🌐",
           "aciklama": "Switch, SFP modül, access point ve diğer ağ donanımı"},
    "yangin": {"ad": "Yangın Sistemleri", "ikon": "🔥",
               "aciklama": "Yangın alarm paneli, dedektörler, butonlar ve sirenler"},
    "alarm": {"ad": "Alarm Sistemleri", "ikon": "🔐",
              "aciklama": "Hırsız alarm panelleri, kablolu/kablosuz dedektörler, "
                          "tuş takımları, sirenler ve modüller"},
    "gecis": {"ad": "Geçiş Sistemleri", "ikon": "🚧",
              "aciklama": "Kart okuyucu ve yazıcıları, bariyerler ve parçaları, "
                          "plaka tanıma sistemi ve kameraları"},
    "kantar": {"ad": "Kantar Sistemi", "ikon": "⚖️",
               "aciklama": "Araç kantarları, yük hücreleri, terminaller ve "
                           "yardımcı ekipman"},
}

POE_SECENEKLERI = ["Yok", "PoE", "PoE+ (802.3at)", "PoE++ (802.3bt)", "Pasif PoE"]
ADRESLI_SECENEKLERI = ["Adresli", "Konvansiyonel"]
IP_SINIFI = ["IP20", "IP42", "IP54", "IP65", "IP66", "IP67"]
KATMAN_SECENEKLERI = ["Erişim (Access)", "Dağıtım (Distribution)", "Omurga (Core)"]

# Alarm tarafında kablolu/kablosuz ayrımı her türde sorulur
BAGLANTI_SECENEKLERI = ["Kablolu", "Kablosuz", "Hibrit (kablolu + kablosuz)"]
FREKANS_SECENEKLERI = ["433 MHz", "868 MHz", "915 MHz", "2.4 GHz"]
PIL_SECENEKLERI = ["Yok (kablolu besleme)", "CR123A", "CR2032", "AA (kalem)",
                   "AAA (ince kalem)", "9V", "Lityum (dahili)"]

# Kart teknolojisi hem okuyucuyu hem yazıcıyı ilgilendirir (aynı kartı
# okuyan ve kodlayan cihazlar eşleşmeli)
KART_TEKNOLOJISI = ["Proximity 125 kHz (EM)", "Mifare 13.56 MHz",
                    "Mifare DESFire", "HID iCLASS", "NFC",
                    "UHF (860-960 MHz)", "Manyetik Şerit", "Temaslı Çip",
                    "Barkod / QR"]

# Ağ ürün türleri: anahtar -> (görünen ad, ikon, alanlar)
TURLER: dict[str, dict] = {
    "switch": {
        "aile": "ag",
        "ad": "Switch",
        "ikon": "🔀",
        "aciklama": "Yönetilebilir/yönetilemez anahtarlar, omurga ve kenar cihazlar",
        "alanlar": [
            Alan("Port Sayısı", "Port Sayısı", "number", ipucu="örn. 24"),
            Alan("Port Hızı", "Port Hızı", "secim",
                 ["100 Mbps", "1 Gbps", "2.5 Gbps", "10 Gbps", "25 Gbps", "40 Gbps"]),
            Alan("PoE", "PoE Desteği", "secim", POE_SECENEKLERI),
            Alan("PoE Bütçesi (W)", "PoE Bütçesi (W)", "number", ipucu="örn. 370"),
            Alan("Katman", "Ağdaki Yeri", "secim", KATMAN_SECENEKLERI),
            Alan("Yönetilebilir", "Yönetilebilir mi", "secim",
                 ["Yönetilebilir", "Yönetilemez (unmanaged)"]),
            Alan("Uplink", "Uplink Portları", ipucu="örn. 4x SFP+ 10G"),
            Alan("Yığınlanabilir", "Yığınlanabilir (stack)", "secim", ["Evet", "Hayır"]),
            Alan("VLAN", "VLAN Desteği", "secim", ["Var", "Yok"]),
            Alan("Rack U", "Rack Yüksekliği (U)", "number"),
        ],
    },
    "sfp": {
        "aile": "ag",
        "ad": "SFP / Modül",
        "ikon": "🔌",
        "aciklama": "SFP, SFP+, QSFP transceiver ve medya dönüştürücüler",
        "alanlar": [
            Alan("Hız", "Hız", "secim",
                 ["1.25G", "10G", "25G", "40G", "100G", "8G FC", "4G FC"]),
            Alan("Dalga Boyu", "Dalga Boyu", "secim",
                 ["850nm", "1310nm", "1550nm", "BiDi"]),
            Alan("Mesafe", "Mesafe", "secim",
                 ["550m", "300m", "2km", "10km", "20km", "40km", "80km"]),
            Alan("Mod", "Fiber Modu", "secim",
                 ["Multi-Mode", "Single-Mode", "Bakır (RJ45)"]),
            Alan("Konnektör", "Konnektör", "secim", ["LC", "SC", "RJ45", "MPO"]),
        ],
    },
    "access_point": {
        "aile": "ag",
        "ad": "Access Point",
        "ikon": "📶",
        "aciklama": "Kablosuz erişim noktaları",
        "alanlar": [
            Alan("Standart", "Wi-Fi Standardı", "secim",
                 ["Wi-Fi 4 (n)", "Wi-Fi 5 (ac)", "Wi-Fi 6 (ax)", "Wi-Fi 6E", "Wi-Fi 7"]),
            Alan("Bant", "Bantlar", "secim",
                 ["2.4 GHz", "5 GHz", "2.4 + 5 GHz", "2.4 + 5 + 6 GHz"]),
            Alan("PoE", "PoE ile Beslenir mi", "secim", POE_SECENEKLERI),
            Alan("Anten", "Anten", "secim", ["Dahili", "Harici"]),
            Alan("Montaj", "Montaj", "secim", ["Tavan", "Duvar", "Direk"]),
        ],
    },
    "router": {
        "aile": "ag",
        "ad": "Router / Modem",
        "ikon": "📡",
        "aciklama": "Yönlendiriciler ve modemler",
        "alanlar": [
            Alan("Port Sayısı", "Port Sayısı", "number"),
            Alan("WAN Portu", "WAN Portu", "number"),
            Alan("Throughput", "Throughput", ipucu="örn. 1 Gbps"),
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim",
                 ["Fiber", "VDSL/ADSL", "Metro Ethernet", "4G/LTE", "5G", "Uydu"]),
            Alan("Katman", "Ağdaki Yeri", "secim", KATMAN_SECENEKLERI),
        ],
    },
    "mobil_internet": {
        "aile": "ag",
        "ad": "Mobil İnternet / Superbox",
        "ikon": "📱",
        "aciklama": "Superbox, Vinn, MiFi, USB modem ve SIM'li 4G/5G cihazlar",
        # Hat bilgisi teknik özellik değil künye bilgisidir: operatör, hat no,
        # SIM ve IMEI varlığın kendi sütunlarında tutulur (arama onları da tarar)
        "hat": True,
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["Sabit Kablosuz (Superbox)", "Taşınabilir Wi-Fi (Vinn/MiFi)",
                  "USB Modem (dongle)", "SIM'li Router", "Endüstriyel 4G Router"]),
            Alan("Nesil", "Şebeke Nesli", "secim",
                 ["4G / LTE", "4.5G", "5G", "3G"]),
            Alan("Wi-Fi", "Wi-Fi Standardı", "secim",
                 ["Yok", "Wi-Fi 4 (n)", "Wi-Fi 5 (ac)", "Wi-Fi 6 (ax)"]),
            Alan("Ethernet Portu", "Ethernet Portu", "number"),
            Alan("Bağlanabilen Cihaz", "Bağlanabilen Cihaz Sayısı", "number",
                 ipucu="örn. 64"),
            Alan("Paket", "Tarife / Kota", ipucu="örn. 250 GB/ay"),
            Alan("Taahhüt Bitiş", "Taahhüt Bitişi", ipucu="örn. 31.12.2026"),
            Alan("Batarya", "Batarya", "secim",
                 ["Yok (prizden)", "Var"]),
            Alan("Batarya Süresi", "Batarya Süresi", ipucu="örn. 8 saat"),
            Alan("Anten", "Harici Anten", "secim", ["Var", "Yok"]),
        ],
    },
    "firewall": {
        "aile": "ag",
        "ad": "Güvenlik Duvarı",
        "ikon": "🛡️",
        "aciklama": "Firewall / UTM cihazları ve güvenlik geçitleri",
        "alanlar": [
            Alan("Port Sayısı", "Port Sayısı", "number"),
            Alan("WAN Portu", "WAN Portu", "number"),
            Alan("Throughput", "Firewall Throughput", ipucu="örn. 1 Gbps"),
            Alan("VPN Throughput", "VPN Throughput", ipucu="örn. 300 Mbps"),
            Alan("Eşzamanlı Oturum", "Eşzamanlı Oturum", "number"),
            Alan("VPN", "VPN Desteği", "secim",
                 ["Yok", "IPSec", "SSL-VPN", "IPSec + SSL-VPN"]),
            Alan("Lisans Bitiş", "Lisans/Abonelik Bitişi", ipucu="örn. 31.12.2027"),
            Alan("HA", "Yüksek Erişilebilirlik (HA)", "secim",
                 ["Yok", "Aktif-Pasif", "Aktif-Aktif"]),
            Alan("Rack U", "Rack Yüksekliği (U)", "number"),
        ],
    },
    "ptp": {
        "aile": "ag",
        "ad": "Noktadan Noktaya Link",
        "ikon": "🔭",
        "aciklama": "Şantiyeler arası kablosuz köprüler (PtP/PtMP anten setleri)",
        "alanlar": [
            Alan("Frekans", "Frekans", "secim",
                 ["2.4 GHz", "5 GHz", "5.8 GHz", "24 GHz", "60 GHz", "80 GHz"]),
            Alan("Hız", "Bağlantı Hızı", ipucu="örn. 300 Mbps"),
            Alan("Menzil", "Menzil", ipucu="örn. 5 km"),
            Alan("Anten Kazancı", "Anten Kazancı (dBi)", "number", ipucu="örn. 25"),
            Alan("Mod", "Çalışma Modu", "secim",
                 ["Noktadan Noktaya (PtP)", "Noktadan Çok Noktaya (PtMP)"]),
            Alan("Rol", "Roldeki Yeri", "secim", ["Master (AP)", "Slave (Station)"]),
            Alan("Karşı Uç", "Karşı Uç", ipucu="bağlandığı şantiye / cihaz"),
            Alan("PoE", "PoE ile Beslenir mi", "secim", POE_SECENEKLERI),
        ],
    },
    "nvr": {
        "aile": "ag",
        "ad": "NVR / Kayıt Cihazı",
        "ikon": "🎥",
        "aciklama": "Ağ üzerinden kamera kaydı yapan cihazlar (NVR / DVR)",
        "alanlar": [
            Alan("Kanal Sayısı", "Kanal Sayısı", "number", ipucu="örn. 16"),
            Alan("PoE Portu", "PoE Portu", "number",
                 ipucu="kameraları besleyen port sayısı"),
            Alan("PoE Bütçesi (W)", "PoE Bütçesi (W)", "number"),
            Alan("Disk Yuvası", "Disk Yuvası", "number", ipucu="örn. 4"),
            Alan("Disk Kapasitesi", "Takılı Disk Kapasitesi", ipucu="örn. 4x4 TB"),
            Alan("RAID", "RAID", "secim",
                 ["Yok", "RAID 0", "RAID 1", "RAID 5", "RAID 6", "RAID 10"]),
            Alan("Çözünürlük", "Azami Çözünürlük", "secim",
                 ["2 MP (1080p)", "4 MP", "5 MP", "8 MP (4K)", "12 MP"]),
            Alan("Kayıt Süresi", "Kayıt Süresi", ipucu="örn. 30 gün"),
            Alan("Rack U", "Rack Yüksekliği (U)", "number"),
        ],
    },
    "kabinet": {
        "aile": "ag",
        "ad": "Kabinet / Patch Panel",
        "ikon": "🗄️",
        "aciklama": "Rack kabinetler, patch panel ve kablolama malzemesi",
        "alanlar": [
            Alan("Boyut (U)", "Boyut (U)", "number", ipucu="örn. 42"),
            Alan("Port Sayısı", "Port Sayısı", "number"),
            Alan("Kategori", "Kablo Kategorisi", "secim",
                 ["Cat5e", "Cat6", "Cat6a", "Cat7", "Fiber"]),
            Alan("Derinlik (cm)", "Derinlik (cm)", "number"),
        ],
    },
    "diger": {
        "aile": "ag",
        "ad": "Diğer Ağ Ürünü",
        "ikon": "🌐",
        "aciklama": "Media converter, KVM, konsol sunucu ve diğerleri",
        "alanlar": [Alan("Açıklama", "Teknik Açıklama")],
    },

    # ----------------------------------------------------------------- #
    # Yangın algılama sistemleri
    # ----------------------------------------------------------------- #
    "yangin_panel": {
        "aile": "yangin",
        "ad": "Yangın Alarm Paneli",
        "ikon": "🚨",
        "aciklama": "Adresli/konvansiyonel yangın alarm santralleri ve tekrarlayıcılar",
        "alanlar": [
            Alan("Sistem Tipi", "Sistem Tipi", "secim", ADRESLI_SECENEKLERI),
            Alan("Çevrim Sayısı", "Çevrim (Loop) Sayısı", "number", ipucu="örn. 2"),
            Alan("Adres Kapasitesi", "Çevrim Başına Adres", "number", ipucu="örn. 127"),
            Alan("Zon Sayısı", "Zon Sayısı", "number"),
            Alan("Siren Çıkışı", "Siren Çıkışı", "number"),
            Alan("Batarya", "Batarya", ipucu="örn. 2x12V 7Ah"),
            Alan("Yedek Süre", "Yedekleme Süresi", ipucu="örn. 24 saat + 30 dk alarm"),
            Alan("Ağ Bağlantısı", "Ağ Bağlantısı", "secim",
                 ["Yok", "TCP/IP", "RS485", "TCP/IP + RS485"]),
            Alan("Sertifika", "Sertifika", "secim",
                 ["EN 54", "UL", "CE", "TSE", "Belirtilmemiş"]),
        ],
    },
    "dedektor": {
        "aile": "yangin",
        "ad": "Dedektör / Sensör",
        "ikon": "🔎",
        "aciklama": "Duman, ısı, alev ve gaz dedektörleri",
        "alanlar": [
            Alan("Algılama Tipi", "Algılama Tipi", "secim",
                 ["Optik Duman", "İyonize Duman", "Isı (Sabit)", "Isı (Artış Hızı)",
                  "Duman + Isı (Kombine)", "Alev", "Gaz (CO)", "Gaz (LPG/Doğalgaz)",
                  "Aspirasyon"]),
            Alan("Sistem Tipi", "Sistem Tipi", "secim", ADRESLI_SECENEKLERI),
            Alan("Adres", "Adres / Zon", ipucu="örn. Loop 1 / Adres 24"),
            Alan("Kapsama Alanı", "Kapsama Alanı (m²)", "number", ipucu="örn. 60"),
            Alan("Montaj", "Montaj", "secim", ["Tavan", "Duvar", "Kanal içi"]),
            Alan("Soket", "Soket / Taban", ipucu="örn. standart taban"),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "yangin_buton": {
        "aile": "yangin",
        "ad": "Buton / Siren",
        "ikon": "🔔",
        "aciklama": "Yangın ihbar butonları, sirenler ve flaşörler",
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["Yangın İhbar Butonu", "Siren", "Flaşör", "Siren + Flaşör",
                  "Konvansiyonel Buton"]),
            Alan("Sistem Tipi", "Sistem Tipi", "secim", ADRESLI_SECENEKLERI),
            Alan("Adres", "Adres / Zon", ipucu="örn. Loop 1 / Adres 8"),
            Alan("Ses Seviyesi", "Ses Seviyesi (dB)", "number", ipucu="örn. 100"),
            Alan("Montaj", "Montaj", "secim", ["İç Mekan", "Dış Mekan"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
            Alan("Besleme", "Besleme Gerilimi", "secim", ["24V DC", "12V DC", "Çevrimden"]),
        ],
    },
    "beam": {
        "aile": "yangin",
        "ad": "Beam Dedektör / Yansıtıcı",
        "ikon": "📡",
        "aciklama": "Noktadan noktaya (ışınlı) duman dedektörleri ve yansıtıcıları",
        "alanlar": [
            Alan("Parça Tipi", "Parça Tipi", "secim",
                 ["Verici-Alıcı (tek gövde)", "Verici", "Alıcı", "Yansıtıcı (prizma)"]),
            Alan("Menzil", "Menzil", ipucu="örn. 10-100 m"),
            Alan("Yansıtıcı Sayısı", "Yansıtıcı Sayısı", "number",
                 ipucu="uzun mesafede birden fazla prizma kullanılır"),
            Alan("Hizalama", "Hizalama", "secim", ["Elle", "Motorlu/Otomatik"]),
            Alan("Sistem Tipi", "Sistem Tipi", "secim", ADRESLI_SECENEKLERI),
            Alan("Adres", "Adres / Zon"),
            Alan("Montaj Yüksekliği", "Montaj Yüksekliği (m)", "number"),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "yangin_diger": {
        "aile": "yangin",
        "ad": "Diğer Yangın Ekipmanı",
        "ikon": "🧯",
        "aciklama": "Modül, izolatör, yangın dolabı, tüp ve diğer ekipman",
        "alanlar": [
            Alan("Ekipman Tipi", "Ekipman Tipi", "secim",
                 ["Giriş/Çıkış Modülü", "İzolatör", "Tekrarlayıcı Panel",
                  "Yangın Dolabı", "Yangın Tüpü", "Duman Damperi", "Diğer"]),
            Alan("Sistem Tipi", "Sistem Tipi", "secim", ADRESLI_SECENEKLERI),
            Alan("Adres", "Adres / Zon"),
            Alan("Açıklama", "Teknik Açıklama"),
        ],
    },

    # ----------------------------------------------------------------- #
    # Alarm (hırsız ihbar) sistemleri — kablolu ve kablosuz
    # ----------------------------------------------------------------- #
    "alarm_panel": {
        "aile": "alarm",
        "ad": "Alarm Paneli",
        "ikon": "🔐",
        "aciklama": "Hırsız ihbar kontrol panelleri (kablolu, kablosuz, hibrit)",
        "alanlar": [
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim", BAGLANTI_SECENEKLERI),
            Alan("Zon Sayısı", "Kablolu Zon Sayısı", "number", ipucu="örn. 8"),
            Alan("Kablosuz Zon", "Kablosuz Zon Sayısı", "number", ipucu="örn. 32"),
            Alan("Genişletilebilir Zon", "Genişletme ile Azami Zon", "number"),
            Alan("Bölme", "Bölme (Partition) Sayısı", "number", ipucu="örn. 2"),
            Alan("Kullanıcı Sayısı", "Kullanıcı Kodu Sayısı", "number"),
            Alan("Frekans", "Kablosuz Frekans", "secim", FREKANS_SECENEKLERI),
            Alan("Haberleşme", "Haberleşme", "secim",
                 ["Yok", "PSTN (telefon hattı)", "GSM/GPRS", "IP (Ethernet)",
                  "GSM + IP", "Wi-Fi"]),
            Alan("Uygulama", "Mobil Uygulama Desteği", "secim", ["Var", "Yok"]),
            Alan("Çıkış Sayısı", "Programlanabilir Çıkış (PGM)", "number"),
            Alan("Batarya", "Yedek Batarya", ipucu="örn. 12V 7Ah"),
            Alan("Yedek Süre", "Yedekleme Süresi", ipucu="örn. 24 saat"),
            Alan("Sertifika", "Sertifika", "secim",
                 ["EN 50131", "CE", "TSE", "Belirtilmemiş"]),
        ],
    },
    "alarm_dedektor": {
        "aile": "alarm",
        "ad": "Alarm Dedektörü",
        "ikon": "🚶",
        "aciklama": "Hareket (PIR), manyetik kontak, cam kırılma ve titreşim "
                    "dedektörleri",
        "alanlar": [
            Alan("Algılama Tipi", "Algılama Tipi", "secim",
                 ["PIR (Hareket)", "Dual (PIR + Mikrodalga)", "Manyetik Kontak",
                  "Cam Kırılma", "Titreşim / Şok", "Perde Tipi",
                  "Dış Mekan (Bariyer)", "Su Baskını", "Panik / Sabotaj"]),
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim", BAGLANTI_SECENEKLERI),
            Alan("Frekans", "Kablosuz Frekans", "secim", FREKANS_SECENEKLERI),
            Alan("Menzil", "Algılama Menzili (m)", "number", ipucu="örn. 12"),
            Alan("Algılama Açısı", "Algılama Açısı (°)", "number", ipucu="örn. 110"),
            Alan("Evcil Hayvan", "Evcil Hayvan Bağışıklığı", "secim",
                 ["Yok", "Var (25 kg'a kadar)", "Var (45 kg'a kadar)"]),
            Alan("Pil Tipi", "Pil Tipi", "secim", PIL_SECENEKLERI),
            Alan("Pil Ömrü", "Pil Ömrü", ipucu="örn. 2 yıl"),
            Alan("Zon", "Bağlı Olduğu Zon", ipucu="örn. Zon 3"),
            Alan("Montaj", "Montaj", "secim",
                 ["İç Mekan (duvar)", "İç Mekan (köşe)", "Tavan", "Dış Mekan"]),
            Alan("Tamper", "Sabotaj (tamper) Koruması", "secim", ["Var", "Yok"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "alarm_keypad": {
        "aile": "alarm",
        "ad": "Tuş Takımı / Kumanda",
        "ikon": "🔢",
        "aciklama": "Keypad, uzaktan kumanda, etiket okuyucu ve panik butonları",
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["Tuş Takımı (LED)", "Tuş Takımı (LCD)", "Dokunmatik Tuş Takımı",
                  "Uzaktan Kumanda", "Etiket / Proximity Okuyucu", "Panik Butonu"]),
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim", BAGLANTI_SECENEKLERI),
            Alan("Frekans", "Kablosuz Frekans", "secim", FREKANS_SECENEKLERI),
            Alan("Buton Sayısı", "Buton Sayısı", "number", ipucu="kumandalar için"),
            Alan("Bölme Desteği", "Bölme (Partition) Desteği", "secim",
                 ["Var", "Yok"]),
            Alan("Pil Tipi", "Pil Tipi", "secim", PIL_SECENEKLERI),
            Alan("Tamper", "Sabotaj (tamper) Koruması", "secim", ["Var", "Yok"]),
            Alan("Montaj", "Montaj", "secim", ["Duvar", "Taşınabilir"]),
        ],
    },
    "alarm_siren": {
        "aile": "alarm",
        "ad": "Alarm Sireni",
        "ikon": "📢",
        "aciklama": "İç/dış mekan alarm sirenleri ve flaşörler",
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["İç Mekan Siren", "Dış Mekan Siren", "Siren + Flaşör", "Flaşör"]),
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim", BAGLANTI_SECENEKLERI),
            Alan("Frekans", "Kablosuz Frekans", "secim", FREKANS_SECENEKLERI),
            Alan("Ses Seviyesi", "Ses Seviyesi (dB)", "number", ipucu="örn. 110"),
            Alan("Besleme", "Besleme", "secim",
                 ["Panelden (12V DC)", "24V DC", "Pil", "Panelden + Pil"]),
            Alan("Batarya", "Yedek Batarya", ipucu="örn. 12V 1.2Ah"),
            Alan("Tamper", "Sabotaj (tamper) Koruması", "secim", ["Var", "Yok"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "alarm_modul": {
        "aile": "alarm",
        "ad": "Alarm Modülü",
        "ikon": "🧩",
        "aciklama": "Zon genişletici, kablosuz alıcı, GSM/IP haberleşme, röle ve "
                    "tekrarlayıcı modülleri",
        "alanlar": [
            Alan("Modül Tipi", "Modül Tipi", "secim",
                 ["Zon Genişletme Modülü", "Kablosuz Alıcı (receiver)",
                  "GSM / GPRS Haberleşme", "IP Haberleşme", "Wi-Fi Modülü",
                  "Röle / Çıkış Modülü", "Güç Kaynağı Modülü",
                  "Tekrarlayıcı (repeater)", "Ses / Konuşma Modülü", "Diğer"]),
            Alan("Bağlantı Tipi", "Bağlantı Tipi", "secim", BAGLANTI_SECENEKLERI),
            Alan("Frekans", "Kablosuz Frekans", "secim", FREKANS_SECENEKLERI),
            Alan("Kanal Sayısı", "Zon / Kanal Sayısı", "number", ipucu="örn. 8"),
            Alan("Menzil", "Menzil", ipucu="örn. 100 m (açık alan)"),
            Alan("Besleme", "Besleme", "secim",
                 ["Panelden (12V DC)", "24V DC", "220V AC", "Pil"]),
            Alan("Uyumlu Panel", "Uyumlu Panel", ipucu="örn. Paradox SP serisi"),
            Alan("Açıklama", "Teknik Açıklama"),
        ],
    },

    # ----------------------------------------------------------------- #
    # Geçiş sistemleri — kart, bariyer ve plaka tanıma
    # ----------------------------------------------------------------- #
    "kart_okuyucu": {
        "aile": "gecis",
        "ad": "Kart Okuyucu",
        "ikon": "🪪",
        "aciklama": "Kartlı geçiş okuyucuları, parmak izi ve yüz tanıma "
                    "terminalleri, PDKS cihazları",
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["Kart Okuyucu", "Kart + Şifre (tuş takımlı)", "Parmak İzi",
                  "Yüz Tanıma", "Kart + Parmak İzi", "Uzun Mesafe (UHF)",
                  "Turnike Okuyucusu", "Plaka Tanıma"]),
            Alan("Kart Teknolojisi", "Kart Teknolojisi", "secim", KART_TEKNOLOJISI),
            Alan("Haberleşme", "Haberleşme", "secim",
                 ["Wiegand 26", "Wiegand 34", "RS485", "OSDP", "TCP/IP", "USB"]),
            Alan("Kullanım", "Kullanım Amacı", "secim",
                 ["Geçiş Kontrol (kapı)", "PDKS (personel devam)",
                  "Turnike", "Otopark / Bariyer", "Yemekhane"]),
            Alan("Okuma Mesafesi", "Okuma Mesafesi (cm)", "number", ipucu="örn. 8"),
            Alan("Kullanıcı Kapasitesi", "Kart / Kullanıcı Kapasitesi", "number",
                 ipucu="örn. 10000"),
            Alan("Tuş Takımı", "Tuş Takımı", "secim", ["Var", "Yok"]),
            Alan("Bağlı Panel", "Bağlı Olduğu Panel / Kontrolör",
                 ipucu="örn. 2 kapılı kontrolör"),
            Alan("Besleme", "Besleme", "secim",
                 ["12V DC", "24V DC", "PoE", "USB"]),
            Alan("Montaj", "Montaj", "secim",
                 ["İç Mekan", "Dış Mekan", "Gömme", "Turnike üstü"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "kart_yazici": {
        "aile": "gecis",
        "ad": "Kart Yazıcı / Kodlayıcı",
        "ikon": "🖨️",
        "aciklama": "Personel/geçiş kartı basan ve kodlayan yazıcılar",
        "alanlar": [
            Alan("Baskı Tipi", "Baskı Tipi", "secim", ["Tek Yüz", "Çift Yüz"]),
            Alan("Baskı Rengi", "Baskı Rengi", "secim",
                 ["Renkli (YMCKO)", "Monokrom (siyah)", "Renkli + Monokrom"]),
            Alan("Baskı Yöntemi", "Baskı Yöntemi", "secim",
                 ["Doğrudan (DTC)", "Retransfer (yüksek kalite)"]),
            Alan("Çözünürlük", "Çözünürlük (dpi)", "secim", ["300 dpi", "600 dpi"]),
            Alan("Kodlama", "Kart Kodlama", "secim",
                 ["Yok (sadece baskı)", "Manyetik Şerit", "Mifare / RFID",
                  "Temaslı Çip", "UHF", "Manyetik Şerit + Çip"]),
            Alan("Kart Teknolojisi", "Kodladığı Kart Teknolojisi", "secim",
                 KART_TEKNOLOJISI),
            Alan("Bağlantı", "Bağlantı", "secim",
                 ["USB", "USB + Ethernet", "Ethernet", "Wi-Fi"]),
            Alan("Hız", "Baskı Hızı", ipucu="örn. 180 kart/saat (renkli)"),
            Alan("Laminasyon", "Laminasyon Ünitesi", "secim", ["Var", "Yok"]),
            Alan("Hazne", "Kart Haznesi (adet)", "number", ipucu="örn. 100"),
            Alan("Ribbon", "Kullandığı Ribbon", ipucu="örn. YMCKO 250 baskı"),
            Alan("Baskı Sayacı", "Basılan Kart Sayısı", "number"),
        ],
    },
    "bariyer": {
        "aile": "gecis",
        "ad": "Bariyer",
        "ikon": "🚧",
        "aciklama": "Kollu araç bariyerleri (otopark, şantiye girişi, kantar)",
        "alanlar": [
            Alan("Kol Tipi", "Kol Tipi", "secim",
                 ["Düz Kol", "Eklemli (katlanır) Kol", "Çitli (fence) Kol",
                  "Yuvarlak Kol", "Oval Kol"]),
            Alan("Kol Uzunluğu", "Kol Uzunluğu (m)", "number", ipucu="örn. 4"),
            Alan("Açılma Süresi", "Açılma Süresi (sn)", "number", ipucu="örn. 3"),
            Alan("Motor Tipi", "Motor Tipi", "secim",
                 ["Elektromekanik", "Hidrolik", "BLDC (fırçasız)"]),
            Alan("Besleme", "Çalışma Gerilimi", "secim",
                 ["220V AC", "24V DC", "12V DC"]),
            Alan("Kontrol", "Nasıl Açılıyor", "secim",
                 ["Uzaktan Kumanda", "Kartlı Geçiş", "Plaka Tanıma", "Buton",
                  "Kantar / Yazılım", "Kumanda + Kart", "Kumanda + Plaka"]),
            Alan("Güvenlik", "Güvenlik Donanımı", "secim",
                 ["Yok", "Fotosel", "Loop Dedektör", "Fotosel + Loop Dedektör"]),
            Alan("Yön", "Giriş / Çıkış", "secim",
                 ["Giriş", "Çıkış", "Giriş + Çıkış (tek yol)"]),
            Alan("Manuel Açma", "Manuel Açma (elektrik kesintisinde)", "secim",
                 ["Var", "Yok"]),
            Alan("LED Kol", "LED Kol Aydınlatması", "secim", ["Var", "Yok"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "bariyer_parca": {
        "aile": "gecis",
        "ad": "Bariyer Parçası",
        "ikon": "🔧",
        "aciklama": "Bariyer kolu, motor, kontrol kartı, fotosel, loop dedektör "
                    "ve diğer yedek parçalar",
        "alanlar": [
            Alan("Parça Tipi", "Parça Tipi", "secim",
                 ["Bariyer Kolu", "Motor", "Redüktör", "Denge Yayı",
                  "Kontrol Kartı", "Loop Dedektör", "Fotosel",
                  "Uzaktan Kumanda", "Kumanda Alıcısı", "LED Şerit",
                  "Kol Flanşı / Tutucu", "Kol Ayağı (destek)", "Diğer"]),
            Alan("Uyumlu Model", "Uyumlu Bariyer Modeli",
                 ipucu="örn. CAME Gard 4040"),
            Alan("Ölçü", "Ölçü / Uzunluk", ipucu="örn. 4 m alüminyum kol"),
            Alan("Adet", "Adet", "number"),
            Alan("Açıklama", "Teknik Açıklama"),
        ],
    },
    "plaka_kamera": {
        "aile": "gecis",
        "ad": "Plaka Tanıma Kamerası",
        "ikon": "📷",
        "aciklama": "ANPR/LPR plaka okuma kameraları",
        "alanlar": [
            Alan("Çözünürlük", "Çözünürlük", "secim",
                 ["2 MP (1080p)", "4 MP", "5 MP", "8 MP (4K)"]),
            Alan("Lens", "Lens", ipucu="örn. 2.8-12 mm motorize"),
            Alan("Okuma Mesafesi", "Okuma Mesafesi (m)", "number", ipucu="örn. 15"),
            Alan("Azami Hız", "Okuyabildiği Azami Hız (km/s)", "number",
                 ipucu="örn. 60"),
            Alan("Aydınlatma", "Aydınlatma", "secim",
                 ["IR (kızılötesi)", "Beyaz Işık", "IR + Beyaz Işık", "Yok"]),
            Alan("IR Mesafesi", "IR Mesafesi (m)", "number"),
            Alan("Besleme", "Besleme", "secim", ["PoE", "12V DC", "24V AC"]),
            Alan("Bağlı Ünite", "Bağlı Olduğu Ünite / NVR"),
            Alan("Yön", "Giriş / Çıkış", "secim", ["Giriş", "Çıkış", "Şerit"]),
            Alan("Montaj", "Montaj", "secim", ["Direk", "Duvar", "Portal"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "plaka_tanima": {
        "aile": "gecis",
        "ad": "Plaka Tanıma Ünitesi",
        "ikon": "🚗",
        "aciklama": "Plaka okuma sisteminin kontrol ünitesi, sunucusu ve yazılımı",
        "alanlar": [
            Alan("Bileşen Tipi", "Bileşen Tipi", "secim",
                 ["Gömülü Ünite (edge)", "Sunucu / Yazılım", "Kontrol Ünitesi",
                  "Röle / Çıkış Modülü"]),
            Alan("Kanal Sayısı", "Kamera / Kanal Sayısı", "number", ipucu="örn. 4"),
            Alan("Plaka Formatı", "Plaka Formatı", "secim",
                 ["TR (Türkiye)", "TR + Yabancı Plaka", "Çoklu Ülke"]),
            Alan("Beyaz Liste", "Beyaz Liste Kapasitesi", "number",
                 ipucu="örn. 10000 plaka"),
            Alan("Entegrasyon", "Entegre Olduğu Sistem", "secim",
                 ["Bariyer", "Kantar", "Kartlı Geçiş", "Otopark Yazılımı",
                  "Bariyer + Kantar"]),
            Alan("Bağlantı", "Bağlantı", "secim",
                 ["TCP/IP", "RS485", "Röle Çıkışı", "TCP/IP + Röle"]),
            Alan("Lisans Bitiş", "Lisans/Abonelik Bitişi", ipucu="örn. 31.12.2027"),
            Alan("Sunucu", "Çalıştığı Sunucu / Bilgisayar"),
        ],
    },

    # ----------------------------------------------------------------- #
    # Kantar sistemi
    # ----------------------------------------------------------------- #
    "kantar_platform": {
        "aile": "kantar",
        "ad": "Kantar / Tartım Platformu",
        "ikon": "⚖️",
        "aciklama": "Araç (köprü) kantarları ve tartım platformları",
        "alanlar": [
            Alan("Kantar Tipi", "Kantar Tipi", "secim",
                 ["Araç Kantarı (köprü)", "Yük Kantarı (platform)",
                  "Bant Kantarı", "Vinç Kantarı", "Mobil Kantar"]),
            Alan("Kapasite", "Kapasite (ton)", "number", ipucu="örn. 60"),
            Alan("Platform Ölçüsü", "Platform Ölçüsü", ipucu="örn. 18 x 3 m"),
            Alan("Yük Hücresi Sayısı", "Yük Hücresi Sayısı", "number",
                 ipucu="örn. 8"),
            Alan("Bölüntü", "Bölüntü (d) kg", "number", ipucu="örn. 20"),
            Alan("Yapı", "Platform Yapısı", "secim",
                 ["Çelik", "Beton", "Çelik + Beton"]),
            Alan("Kurulum", "Kurulum Şekli", "secim",
                 ["Yüzey (rampalı)", "Çukurlu (gömme)"]),
            Alan("Kalibrasyon", "Son Kalibrasyon Tarihi", ipucu="örn. 12.03.2026"),
            Alan("Damga Bitiş", "Damga / Muayene Bitişi", ipucu="örn. 31.12.2027"),
        ],
    },
    "loadcell": {
        "aile": "kantar",
        "ad": "Yük Hücresi (Loadcell)",
        "ikon": "🏋️",
        "aciklama": "Kantar yük hücreleri ve bağlantı elemanları",
        "alanlar": [
            Alan("Kapasite", "Kapasite (ton)", "number", ipucu="örn. 30"),
            Alan("Hücre Tipi", "Hücre Tipi", "secim",
                 ["Kolon (column)", "Kesme Kirişi (shear beam)",
                  "Tek Nokta (single point)", "S Tipi", "Halka (ring torsion)"]),
            Alan("Malzeme", "Malzeme", "secim",
                 ["Paslanmaz Çelik", "Alaşımlı Çelik", "Nikel Kaplama"]),
            Alan("Çıkış", "Çıkış (mV/V)", ipucu="örn. 2.0 mV/V"),
            Alan("Doğruluk Sınıfı", "Doğruluk Sınıfı", "secim",
                 ["C3", "C4", "C5", "C6", "Belirtilmemiş"]),
            Alan("Kablo Uzunluğu", "Kablo Uzunluğu (m)", "number"),
            Alan("Bağlı Kantar", "Bağlı Olduğu Kantar", ipucu="örn. Giriş kantarı"),
            Alan("Konum", "Platformdaki Konumu", ipucu="örn. 3 no'lu hücre"),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
        ],
    },
    "kantar_terminal": {
        "aile": "kantar",
        "ad": "Kantar Terminali / İndikatör",
        "ikon": "🖥️",
        "aciklama": "Tartım göstergeleri, indikatörler ve tartım bilgisayarları",
        "alanlar": [
            Alan("Cihaz Tipi", "Cihaz Tipi", "secim",
                 ["İndikatör (gösterge)", "Tartım Terminali",
                  "Tartım Bilgisayarı", "Uzak Gösterge (büyük ekran)"]),
            Alan("Ekran", "Ekran", "secim", ["LED", "LCD", "Dokunmatik"]),
            Alan("Kanal Sayısı", "Bağlanabilen Yük Hücresi", "number",
                 ipucu="örn. 8"),
            Alan("Haberleşme", "Haberleşme", "secim",
                 ["RS232", "RS485", "TCP/IP", "USB", "RS232 + TCP/IP"]),
            Alan("Yazıcı", "Fiş Yazıcısı", "secim",
                 ["Yok", "Dahili", "Harici (RS232)", "Harici (USB)"]),
            Alan("Yazılım", "Tartım Yazılımı", ipucu="örn. kantar takip programı"),
            Alan("Onay", "Onay / Sertifika", "secim",
                 ["OIML R76", "TSE", "CE", "Belirtilmemiş"]),
            Alan("Besleme", "Besleme", "secim", ["220V AC", "24V DC", "12V DC"]),
        ],
    },
    "kantar_diger": {
        "aile": "kantar",
        "ad": "Diğer Kantar Ekipmanı",
        "ikon": "🧰",
        "aciklama": "Bağlantı kutusu, trafik lambası, uzak gösterge, kablo ve "
                    "yardımcı ekipman",
        "alanlar": [
            Alan("Ekipman Tipi", "Ekipman Tipi", "secim",
                 ["Bağlantı Kutusu (junction box)", "Trafik Lambası",
                  "Uzak Gösterge Ekranı", "Yük Hücresi Kablosu",
                  "Paratoner / Parafudr", "Kalibrasyon Ağırlığı",
                  "Kamera / Görüntüleme", "Yazılım", "Diğer"]),
            Alan("Kapasite", "Kapasite / Ölçü", ipucu="örn. 8 kanal, 500 kg"),
            Alan("Bağlı Kantar", "Bağlı Olduğu Kantar"),
            Alan("Açıklama", "Teknik Açıklama"),
        ],
    },
}

# Kategori adından tür anahtarına: içe aktarılmış kayıtları da yakalamak için.
#
# SIRA ÖNEMLİDİR — ilk eşleşen kural kazanır. Üç aile aynı kelimeleri
# paylaşıyor ("alarm", "panel", "dedektör", "siren", "kablosuz"), bu yüzden
# daha dar kural daha geniş olanın ÜSTÜNDE durmak zorunda:
#   • "Yangın Alarm Paneli" → yangın (alarm kuralından önce gelir)
#   • "Kablosuz Alarm Paneli" → alarm (access_point'in "kablosuz"undan önce)
#   • "Kablosuz Link" → ptp (yine "kablosuz"tan önce)
#   • yalın "Siren" → yangın butonu (eski davranış korunur); "Alarm Sireni"
#     ise alarm ailesine düşer.
# Bir anahtar boşlukla çevrelenirse (" pir ") tam kelime olarak aranır.
_KATEGORI_IPUCU: list[tuple[tuple[str, ...], str]] = [
    # Yaygın yazım hataları da dahil ("swich", "swtich" gerçek veride görüldü)
    (("switch", "swich", "swtich", "anahtar"), "switch"),
    (("sfp", "transceiver", "gbic", "qsfp", "fiber modul", "optik modul"), "sfp"),
    # Dongle ve bridge'ler erişim noktası DEĞİL: biri USB adaptör, diğeri
    # noktadan noktaya bağlantı. access_point'ten ÖNCE eşleşmeliler.
    (("wifi dongle", "wi-fi dongle", "wireless dongle", "wireless adapter",
      "wireless bridge", "wifi bridge", "kablosuz kopru"), "diger"),

    # --- Yangın paneli: "alarm" kelimesini alarm ailesine kaptırmamalı ---
    (("yangin alarm panel", "yangin panel", "yangin santral", "yangin alarm santral",
      "yangin ihbar panel", "yangin kontrol panel"), "yangin_panel"),

    # --- Alarm (hırsız ihbar) sistemleri ---
    (("hirsiz alarm", "hirsiz ihbar", "soygun alarm", "guvenlik alarm",
      "alarm panel", "alarm santral", "alarm kontrol panel"), "alarm_panel"),
    ((" pir ", "pir dedektor", "pir sensor", "alarm dedektor", "alarm sensor",
      "hareket dedektor", "hareket sensor",
      "manyetik kontak", "kapi kontak", "cam kirilma", "titresim dedektor",
      "titresim sensor", "perde dedektor", "perde tipi",
      "bariyer dedektor"), "alarm_dedektor"),
    (("tus takimi", "keypad", "uzaktan kumanda", "alarm kumanda",
      "etiket okuyucu", "panik butonu"), "alarm_keypad"),
    (("alarm siren", "harici siren", "ic mekan siren", "dis mekan siren",
      "kablosuz siren"), "alarm_siren"),
    (("zon genisletici", "zon genisletme", "kablosuz alici", "alarm modul",
      "gsm modul", "gprs modul", "ip haberlesme", "haberlesme modul",
      "role modul", "tekrarlayici modul"), "alarm_modul"),

    # --- Geçiş sistemleri ---
    # Düz "Yazıcı" kategorisi (normal ofis yazıcısı) buraya girmemeli:
    # her anahtar "kart" kelimesini içerir.
    (("kart yazici", "kart printer", "kart basim", "kart kodlayici",
      "kimlik karti yazici", "kartli gecis yazici"), "kart_yazici"),
    (("kart okuyucu", "kart okutucu", "kartli gecis", "gecis okuyucu",
      "gecis kontrol okuyucu", "proximity okuyucu", "prox okuyucu",
      "rfid okuyucu", "mifare okuyucu", "parmak izi okuyucu",
      "parmak izi terminal", "yuz tanima terminal", "pdks terminal",
      "pdks cihaz", "turnike okuyucu"), "kart_okuyucu"),
    # Kamera kuralı üniteden ÖNCE: "Plaka Tanıma Kamerası" ikisine de uyar
    (("plaka tanima kamera", "plaka kamera", "anpr kamera", "lpr kamera",
      "plaka okuma kamera"), "plaka_kamera"),
    (("plaka tanima", "plaka okuma", "plaka sistem", " anpr ", " lpr ",
      "anpr unite", "plaka unite"), "plaka_tanima"),
    # Parça kuralı bariyerden ÖNCE: "Bariyer Kolu" bariyerin kendisi değil
    (("bariyer kol", "bariyer motor", "bariyer kart", "bariyer kontrol",
      "bariyer yedek",
      "bariyer kumanda", "bariyer fotosel", "loop dedektor", "lup dedektor",
      "fotosel", "bariyer parca"), "bariyer_parca"),
    (("bariyer", "kollu bariyer", "otopark bariyer", "kol bariyer"), "bariyer"),

    # --- Kantar sistemi ---
    (("yuk hucresi", "loadcell", "load cell", "yuk sensor"), "loadcell"),
    (("kantar terminal", "kantar indikator", "indikator", "tarti terminal",
      "tartim terminal", "tartim bilgisayari", "kantar gosterge"),
     "kantar_terminal"),
    (("kantar baglanti kutusu", "junction box", "kantar yazilim",
      "kantar kablo", "kalibrasyon agirlik", "trafik lamba",
      "diger kantar"), "kantar_diger"),
    (("arac kantar", "kopru kantar", "tartim platform", "kantar platform",
      "kantar", "bascul", "tarti platform"), "kantar_platform"),

    # "Kablosuz Link" access_point değildir: ptp önce gelir
    (("noktadan noktaya", "point to point", "ptp", "ptmp", "kablosuz link",
      "radyo link", "airfiber", "airmax", "nanostation"), "ptp"),
    (("access point", "accesspoint", "erisim noktasi", "wifi", "wi-fi",
      "kablosuz"), "access_point"),
    (("firewall", "guvenlik duvari", "utm", "guvenlik geciti"), "firewall"),
    # SIM'li cihazlar router'dan ÖNCE: "4G Modem" bir mobil internet cihazıdır.
    # " vin " boşlukla aranır — "vinç" içindeki "vin"e takılmasın.
    (("superbox", "super box", "vinn", " vin ", "mifi", "mi-fi",
      "mobil internet", "usb modem", "4g modem", "5g modem", "4.5g modem",
      "sim modem", "cep interneti", "tasinabilir wifi",
      "tasinabilir wi-fi"), "mobil_internet"),
    (("router", "modem", "yonlendirici"), "router"),

    # --- Yangın algılama (kalan türler) ---
    (("beam dedektor", "isinli dedektor", "yansitici", "prizma",
      "lineer duman"), "beam"),
    (("dedektor", "detektor", "duman sensor", "isi sensor", "alev sensor",
      "gaz sensor", "duman alarm"), "dedektor"),
    (("yangin butonu", "ihbar butonu", "siren", "flasor",
      "yangin buton"), "yangin_buton"),
    (("yangin dolab", "yangin tup", "yangin sondur", "duman damper",
      "izolator", "yangin"), "yangin_diger"),
    (("nvr", "dvr", "kayit cihazi", "kamera kayit"), "nvr"),
    (("kabinet", "kabin", "patch panel", "patchpanel", "rack"), "kabinet"),
    # Ağ altyapısı ama yukarıdakilere girmeyenler
    (("media converter", "medya donusturucu", "kvm", "konsol sunucu",
      "diger ag urunu"), "diger"),
]


# Ağ cihazının YEDEK PARÇASI olan kategoriler ağ ürünü sayılmaz:
# "NVR Diski" bir disktir, "Switch Fanı" bir fandır.
#
# Kendisi zaten parça/sarf olan türler bu denetimden muaftır: "SFP / Modül"
# bir moduldur, "Bariyer Kolu" ve "Kantar Kablosu" da bilerek takip edilir.
_PARCA_MUAF = frozenset({"sfp", "bariyer_parca", "kantar_diger"})
_PARCA_KELIMELERI = ("disk", "harddisk", "hdd", "ssd", "fan", "adaptor",
                     "kablo", "raf", "vida", "guc", "batarya", "pil",
                     "ribbon", "toner", "kartus")


def _parca_mi(sade: str) -> bool:
    """Ad bir yedek parçayı mı anlatıyor?

    Türkçede tamlamanın başı SONDA olur: "Switch Kablosu"nun konusu kablodur,
    "Kablosuz Erişim Noktası"nınki noktadır. Bu yüzden yalnızca SON kelimeye
    bakılır — metnin herhangi bir yerinde aramak "kablosuz" içindeki "kablo"ya
    takılıp erişim noktalarını eliyordu.
    """
    kelimeler = sade.replace("/", " ").split()
    if not kelimeler:
        return False
    son = kelimeler[-1]
    return any(son.startswith(p) for p in _PARCA_KELIMELERI)


def tur_bul(kategori_adi: str | None) -> str | None:
    """Kategori adından ağ türünü çıkarır; ağ ürünü değilse None."""
    if not kategori_adi:
        return None
    sade = _sadelestir(kategori_adi)
    # Baş/son boşluk: " pir " gibi anahtarlar tam kelime arayabilsin
    # ("spiral" içindeki "pir"e takılmasın); diğer anahtarlar etkilenmez.
    bosluklu = f" {sade} "
    # "Yangın Alarm Sireni" bir alarm ürünü değil, yangın ekipmanıdır:
    # adında "yangın" geçen hiçbir kayıt alarm ailesine düşmez.
    yangin_metni = "yangin" in sade
    for anahtarlar, tur in _KATEGORI_IPUCU:
        if yangin_metni and tur.startswith("alarm_"):
            continue
        if any(a in bosluklu for a in anahtarlar):
            if tur not in _PARCA_MUAF and _parca_mi(sade):
                return None
            return tur
    return None


def kategori_adi(tur: str) -> str:
    """Tür için kullanılacak kategori adı (Tanımlar'da bu adla görünür)."""
    return TURLER[tur]["ad"]


def sablon(aile: str | None = None) -> list[dict]:
    """Arayüzün form üretmek için kullandığı tür/alan tanımları.

    `aile` verilirse yalnızca o ailenin türleri döner ("ag" / "yangin").
    """
    return [
        {
            "tur": anahtar,
            "aile": bilgi["aile"],
            "ad": bilgi["ad"],
            "ikon": bilgi["ikon"],
            "aciklama": bilgi["aciklama"],
            # Arayüz künye bölümüne hat alanlarını bu bayrağa bakarak ekler
            "hat": bool(bilgi.get("hat")),
            "alanlar": [a.sozluk() for a in bilgi["alanlar"]],
            "ortak": [a.sozluk() for a in ORTAK],
        }
        for anahtar, bilgi in TURLER.items()
        if aile is None or bilgi["aile"] == aile
    ]


# --------------------------------------------------------------------------- #
# Sorgular
# --------------------------------------------------------------------------- #
def _ag_kategori_idleri(db: Session) -> dict[int, str]:
    """Ağ ürünü sayılan kategori kimlikleri -> tür."""
    esleme = {}
    for kid, ad in db.execute(select(models.Category.id, models.Category.name)).all():
        tur = tur_bul(ad)
        if tur:
            esleme[kid] = tur
    return esleme


def _ozellikler(a: models.Asset) -> dict:
    ozel = a.custom or {}
    return dict(ozel.get(GRUP) or {})


def urunler(db: Session, *, aile: str | None = None, tur: str | None = None,
            location_id: int | None = None, proje_kodu: str | None = None,
            durum_id: int | None = None, q: str | None = None) -> list[dict]:
    """Sistem ürünlerini aileye/türe/lokasyona/duruma göre listeler."""
    kategoriler = _ag_kategori_idleri(db)
    if not kategoriler:
        return []

    stmt = (select(models.Asset)
            .join(models.AssetModel, models.Asset.model_id == models.AssetModel.id)
            .where(models.AssetModel.category_id.in_(kategoriler)))
    if location_id is not None:
        stmt = stmt.where(models.Asset.location_id == location_id)
    if durum_id is not None:
        stmt = stmt.where(models.Asset.status_id == durum_id)
    if proje_kodu:
        stmt = stmt.join(models.Location,
                         models.Asset.location_id == models.Location.id
                         ).where(models.Location.proje_kodu == proje_kodu)

    varliklar = db.scalars(stmt.order_by(models.Asset.asset_tag)).all()

    # Ad çözümlemeleri için tek seferlik haritalar (N+1 sorgu olmasın)
    modeller = {m.id: m for m in db.scalars(select(models.AssetModel)).all()}
    markalar = {m.id: m.name for m in db.scalars(select(models.Manufacturer)).all()}
    lokasyonlar = {loc.id: loc for loc in db.scalars(select(models.Location)).all()}
    durumlar = {s.id: s.name for s in db.scalars(select(models.StatusLabel)).all()}
    kisiler = {k.id: " ".join(filter(None, [k.first_name, k.last_name]))
               for k in db.scalars(select(models.User)).all()}
    gorseller = {}
    for d in db.scalars(select(models.AssetFile)
                        .where(models.AssetFile.tur == models.DosyaTuru.gorsel)
                        .order_by(models.AssetFile.created_at)).all():
        gorseller[d.asset_id] = d.id       # her cihazın en yeni görseli

    terim = _sadelestir(q) if q else ""
    sonuc = []
    for a in varliklar:
        mdl = modeller.get(a.model_id)
        urun_turu = kategoriler.get(mdl.category_id) if mdl else None
        if tur and urun_turu != tur:
            continue
        if aile and TURLER.get(urun_turu, {}).get("aile") != aile:
            continue
        lok = lokasyonlar.get(a.location_id)
        kayit = {
            "id": a.id,
            "tur": urun_turu,
            "asset_tag": a.asset_tag,
            "marka": markalar.get(mdl.manufacturer_id) if mdl else None,
            "model": mdl.name if mdl else None,
            "serial": a.serial,
            "demirbas_no": a.demirbas_no,
            "ip_address": a.ip_address,
            # SIM'li cihazlar (Superbox, Vinn, USB modem) için hat künyesi
            "operator": a.operator,
            "telefon_no": a.telefon_no,
            "sim_no": a.sim_no,
            "imei": a.imei,
            "lokasyon": lok.name if lok else None,
            "lokasyon_id": a.location_id,
            "proje_kodu": lok.proje_kodu if lok else None,
            "durum": durumlar.get(a.status_id),
            "zimmetli": kisiler.get(a.assigned_user_id),
            "gorsel_id": gorseller.get(a.id),
            "ozellikler": _ozellikler(a),
        }
        if terim:
            havuz = " ".join(str(v) for v in [
                kayit["asset_tag"], kayit["marka"], kayit["model"], kayit["serial"],
                kayit["demirbas_no"], kayit["lokasyon"], kayit["ip_address"],
                kayit["operator"], kayit["telefon_no"], kayit["sim_no"],
                kayit["imei"], *kayit["ozellikler"].values()] if v)
            if terim not in _sadelestir(havuz):
                continue
        sonuc.append(kayit)
    return sonuc


def ozet(db: Session, *, aile: str | None = None) -> dict:
    """Tür bazlı sayılar, lokasyon dağılımı ve toplam port/PoE kapasitesi."""
    liste = urunler(db, aile=aile)
    tur_sayilari: dict[str, int] = {}
    lokasyon_sayilari: dict[str, int] = {}
    toplam_port = 0
    poe_cihaz = 0

    for u in liste:
        tur_sayilari[u["tur"]] = tur_sayilari.get(u["tur"], 0) + 1
        yer = u["lokasyon"] or "(belirtilmemiş)"
        lokasyon_sayilari[yer] = lokasyon_sayilari.get(yer, 0) + 1
        try:
            toplam_port += int(str(u["ozellikler"].get("Port Sayısı", "")).strip() or 0)
        except ValueError:
            pass
        poe = str(u["ozellikler"].get("PoE", "")).strip()
        if poe and poe.lower() not in ("yok", "hayır", "hayir"):
            poe_cihaz += 1

    return {
        "toplam": len(liste),
        "tur_dagilimi": [
            {"tur": t, "ad": TURLER[t]["ad"], "ikon": TURLER[t]["ikon"], "adet": n}
            for t, n in sorted(tur_sayilari.items(), key=lambda x: -x[1])
        ],
        "lokasyon_dagilimi": [
            {"lokasyon": k, "adet": n}
            for k, n in sorted(lokasyon_sayilari.items(), key=lambda x: -x[1])
        ],
        "toplam_port": toplam_port,
        "poe_cihaz": poe_cihaz,
    }


def transferler(db: Session, *, limit: int = 200) -> list[dict]:
    """Lokasyonu değişen cihazlar: nereden nereye, ne zaman.

    Lokasyon değişikliği `ActivityLog.changes["location_id"]` içinde
    {"eski": ..., "yeni": ...} olarak duruyor (bkz. assets.update_asset).
    """
    lokasyonlar = {loc.id: loc for loc in db.scalars(select(models.Location)).all()}
    etiketler = dict(db.execute(select(models.Asset.id, models.Asset.asset_tag)).all())

    def _ad(ham) -> str | None:
        if ham in (None, "", "None"):
            return None
        try:
            lok = lokasyonlar.get(int(ham))
        except (TypeError, ValueError):
            return str(ham)
        if lok is None:
            return None
        return f"{lok.name} ({lok.proje_kodu})" if lok.proje_kodu else lok.name

    # İşlem türüne bakılmaz: lokasyon değişimi kaydeden her giriş bir transferdir
    # (elle güncelleme "update", toplu içe aktarım "create" olarak yazar).
    kayitlar = db.scalars(
        select(models.ActivityLog)
        .where(models.ActivityLog.item_type == "asset",
               models.ActivityLog.changes.is_not(None))
        .order_by(models.ActivityLog.created_at.desc())
        .limit(2000)
    ).all()

    sonuc = []
    for g in kayitlar:
        degisim = (g.changes or {}).get("location_id")
        if not isinstance(degisim, dict):
            continue
        nereden, nereye = _ad(degisim.get("eski")), _ad(degisim.get("yeni"))
        if nereden == nereye:
            continue
        sonuc.append({
            "asset_id": g.item_id,
            "asset_tag": etiketler.get(g.item_id),
            "nereden": nereden,
            "nereye": nereye,
            "tarih": g.created_at.isoformat() if g.created_at else None,
            "not": g.note,
        })
        if len(sonuc) >= limit:
            break
    return sonuc
