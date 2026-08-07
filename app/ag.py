"""Ağ / network ürünleri — tür şablonları ve sorgular.

Ağ ürünleri ayrı bir tablo değildir: normal varlıklardır, ama kategorileri
ağ türlerinden biridir ve teknik özellikleri `Asset.custom["Ağ"]` altında
tutulur. Böylece zimmet, dosya eki, etiket basma, arama gibi her şey aynen
çalışır; ağ ekranı yalnızca bu varlıklara türe özel bir görünüm sunar.

Her türün kendi alan listesi vardır (switch'te port sayısı ve PoE, SFP'de
hız/mesafe/mod gibi) — bkz. `TURLER`.
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

POE_SECENEKLERI = ["Yok", "PoE", "PoE+ (802.3at)", "PoE++ (802.3bt)", "Pasif PoE"]
KATMAN_SECENEKLERI = ["Erişim (Access)", "Dağıtım (Distribution)", "Omurga (Core)"]

# Ağ ürün türleri: anahtar -> (görünen ad, ikon, alanlar)
TURLER: dict[str, dict] = {
    "switch": {
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
        "ad": "Router / Firewall",
        "ikon": "🛡️",
        "aciklama": "Yönlendirici, güvenlik duvarı ve modemler",
        "alanlar": [
            Alan("Port Sayısı", "Port Sayısı", "number"),
            Alan("WAN Portu", "WAN Portu", "number"),
            Alan("Throughput", "Throughput", ipucu="örn. 1 Gbps"),
            Alan("VPN", "VPN Desteği", "secim", ["Var", "Yok"]),
            Alan("Katman", "Ağdaki Yeri", "secim", KATMAN_SECENEKLERI),
        ],
    },
    "kabinet": {
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
        "ad": "Diğer Ağ Ürünü",
        "ikon": "🌐",
        "aciklama": "Media converter, KVM, konsol sunucu ve diğerleri",
        "alanlar": [Alan("Açıklama", "Teknik Açıklama")],
    },
}

# Kategori adından tür anahtarına: içe aktarılmış kayıtları da yakalamak için
_KATEGORI_IPUCU: list[tuple[tuple[str, ...], str]] = [
    # Yaygın yazım hataları da dahil ("swich", "swtich" gerçek veride görüldü)
    (("switch", "swich", "swtich", "anahtar"), "switch"),
    (("sfp", "transceiver", "gbic", "qsfp", "fiber modul", "optik modul"), "sfp"),
    # Dongle ve bridge'ler erişim noktası DEĞİL: biri USB adaptör, diğeri
    # noktadan noktaya bağlantı. access_point'ten ÖNCE eşleşmeliler.
    (("wifi dongle", "wi-fi dongle", "wireless dongle", "wireless adapter",
      "wireless bridge", "wifi bridge", "kablosuz kopru"), "diger"),
    (("access point", "accesspoint", "erisim noktasi", "wifi", "wi-fi",
      "kablosuz"), "access_point"),
    (("router", "firewall", "guvenlik duvari", "modem", "yonlendirici"), "router"),
    (("kabinet", "kabin", "patch panel", "patchpanel", "rack"), "kabinet"),
    # Ağ altyapısı ama yukarıdakilere girmeyenler
    (("media converter", "medya donusturucu", "kvm", "konsol sunucu"), "diger"),
]


def tur_bul(kategori_adi: str | None) -> str | None:
    """Kategori adından ağ türünü çıkarır; ağ ürünü değilse None."""
    if not kategori_adi:
        return None
    sade = _sadelestir(kategori_adi)
    for anahtarlar, tur in _KATEGORI_IPUCU:
        if any(a in sade for a in anahtarlar):
            return tur
    return None


def kategori_adi(tur: str) -> str:
    """Tür için kullanılacak kategori adı (Tanımlar'da bu adla görünür)."""
    return TURLER[tur]["ad"]


def sablon() -> list[dict]:
    """Arayüzün form üretmek için kullandığı tür/alan tanımları."""
    return [
        {
            "tur": anahtar,
            "ad": bilgi["ad"],
            "ikon": bilgi["ikon"],
            "aciklama": bilgi["aciklama"],
            "alanlar": [a.sozluk() for a in bilgi["alanlar"]],
            "ortak": [a.sozluk() for a in ORTAK],
        }
        for anahtar, bilgi in TURLER.items()
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


def urunler(db: Session, *, tur: str | None = None, location_id: int | None = None,
            proje_kodu: str | None = None, durum_id: int | None = None,
            q: str | None = None) -> list[dict]:
    """Ağ ürünlerini türe/lokasyona/duruma göre listeler."""
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
                *kayit["ozellikler"].values()] if v)
            if terim not in _sadelestir(havuz):
                continue
        sonuc.append(kayit)
    return sonuc


def ozet(db: Session) -> dict:
    """Tür bazlı sayılar, lokasyon dağılımı ve toplam port/PoE kapasitesi."""
    liste = urunler(db)
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
