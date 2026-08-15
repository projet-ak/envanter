"""Sistem ürünü şablonları: aileler, türler, teknik alanlar, kategori eşleme.

Bu modül yalnızca VERİ ve saf işlevler içerir — veritabanına dokunmaz.
Sorgular `app/ag.py`'dedir; dışarıya karşı API değişmedi, her ad oradan da
erişilebilir (`ag.TURLER`, `ag.tur_bul`…).

Yeni tür/aile eklerken üç yere bakmak yeterli:
  1. `AILELER`  — menüde görünen bölüm
  2. `TURLER`   — türün alan listesi (`aile` anahtarıyla ailesine bağlanır)
  3. `_KATEGORI_IPUCU` — kategori adından türü bulan kurallar (SIRA ÖNEMLİ)
Değişmez testi `tests/test_ag_urunleri.py` içindedir: her türün kendi
kategori adı yine kendi türüne dönmek zorundadır.
"""

from __future__ import annotations

from app.excel.sema import _sadelestir

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
    "kamera": {
        "aile": "ag",
        "ad": "IP Kamera",
        "ikon": "📹",
        "aciklama": "Güvenlik kameraları (IP/analog) — dome, bullet, PTZ",
        "alanlar": [
            Alan("Kamera Tipi", "Kamera Tipi", "secim",
                 ["Dome", "Bullet", "PTZ (hareketli)", "Fisheye (balıkgözü)",
                  "Kutu (box)", "Termal", "Kapı Zili / İnterkom"]),
            Alan("Çözünürlük", "Çözünürlük", "secim",
                 ["2 MP (1080p)", "4 MP", "5 MP", "6 MP", "8 MP (4K)", "12 MP"]),
            Alan("Lens", "Lens", ipucu="örn. 2.8 mm sabit / 2.8-12 mm motorize"),
            Alan("Görüş Açısı", "Görüş Açısı (°)", "number", ipucu="örn. 108"),
            Alan("IR Mesafesi", "Gece Görüşü (IR) Mesafesi (m)", "number",
                 ipucu="örn. 30"),
            Alan("Bağlantı", "Bağlantı", "secim",
                 ["IP (Ethernet)", "Wi-Fi", "Analog (BNC)"]),
            Alan("Besleme", "Besleme", "secim",
                 ["PoE", "12V DC", "24V AC", "Adaptör"]),
            Alan("Bağlı NVR", "Bağlı Olduğu NVR / Kayıt Cihazı"),
            Alan("Kanal No", "NVR Kanal No", "number", ipucu="örn. 7"),
            Alan("SD Kart", "SD Kart Kapasitesi", ipucu="örn. 128 GB"),
            Alan("Ses", "Ses", "secim", ["Yok", "Mikrofon", "Mikrofon + Hoparlör"]),
            Alan("Akıllı Özellik", "Akıllı Özellik", "secim",
                 ["Yok", "Hareket Algılama", "İnsan/Araç Ayrımı",
                  "Yüz Tanıma", "Çizgi Geçme / Alan İhlali"]),
            Alan("IP Sınıfı", "IP Koruma Sınıfı", "secim", IP_SINIFI),
            Alan("Montaj", "Montaj", "secim",
                 ["Duvar", "Tavan", "Direk", "Köşe", "Gömme"]),
            Alan("Görüş Alanı", "İzlediği Alan", ipucu="örn. ana giriş kapısı"),
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
      "radyo link", "airfiber", "airmax", "nanostation",
      "ligowave", "ligodlb"), "ptp"),
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
    # Kamera kuralı NVR'DAN SONRA: "Kamera Kayıt Cihazı" kayıt cihazıdır.
    # Plaka tanıma kameraları yukarıda (geçiş ailesi) çoktan eşleşti.
    (("ip kamera", "guvenlik kamera", "dome kamera", "bullet kamera",
      "ptz kamera", "termal kamera", "kamera", "cctv", "dome", "bullet",
      " ptz "), "kamera"),
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


