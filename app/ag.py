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

# Şablonlar ve kategori eşleme app/sistem_sablonlari.py'ye taşındı; buradan
# yeniden dışa verilir ki `ag.TURLER` gibi mevcut kullanımlar değişmesin.
from app.sistem_sablonlari import (  # noqa: F401
    ADRESLI_SECENEKLERI, AILELER, Alan, BAGLANTI_SECENEKLERI,
    FREKANS_SECENEKLERI, GRUP, IP_SINIFI, KART_TEKNOLOJISI,
    KATMAN_SECENEKLERI, ORTAK, PIL_SECENEKLERI, POE_SECENEKLERI, TURLER,
    _KATEGORI_IPUCU, _PARCA_KELIMELERI, _PARCA_MUAF, _parca_mi, tur_bul,
)

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
    # Tür/aile filtresi kategori kümesini baştan daraltır: eleme Python'da
    # satır satır değil, SQL'deki IN(...) içinde yapılır.
    if tur:
        kategoriler = {k: t for k, t in kategoriler.items() if t == tur}
    if aile:
        kategoriler = {k: t for k, t in kategoriler.items()
                       if TURLER.get(t, {}).get("aile") == aile}
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
