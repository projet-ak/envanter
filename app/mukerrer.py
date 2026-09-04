"""Mükerrer varlık tespiti ve birleştirme.

Aynı cihaz envantere birden çok kez girebiliyor: eski aktarımlar etiketi
"-2 / -3" ekiyle çoğaltmış, aynı cihaz bir kez seri numarasıyla bir kez
demirbaş numarasıyla açılmış olabiliyor. Bu modül şüphelileri gruplar ve
birleştirmeyi tek yerden yürütür — hiçbir bilgi kaybolmadan.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models
from app.excel.sema import _sadelestir

# Birleştirmede hedefe kopyalanabilecek künye alanları (etiket hariç:
# etiket kaydın kimliğidir, birleştirme sonrası hedefinki kalır).
TASINACAK_ALANLAR = (
    "name", "serial", "demirbas_no", "muhasebe_kodu", "fatura_no", "barkod",
    "imei", "mac_address", "ip_address", "hostname", "telefon_no", "sim_no",
    "operator", "model_id", "status_id", "supplier_id", "location_id",
    "company_id", "purchase_date", "purchase_cost", "order_number",
    "warranty_months", "warranty_end", "notes", "image_url",
)


def seri_anahtar(deger: str | None) -> str:
    """Seri/demirbaş karşılaştırma anahtarı: yalnız harf-rakam, büyük harf."""
    return re.sub(r"[^0-9A-Z]", "", (deger or "").upper())


def etiket_koku(etiket: str | None) -> str:
    """'B002-2', 'B002_3', 'B002 (2)' → 'B002'. Sonek yoksa etiketin kendisi."""
    ham = (etiket or "").strip()
    if not ham:
        return ""
    ham = re.sub(r"\s*\((\d{1,2})\)$", "", ham)
    ham = re.sub(r"[-_](\d{1,2})$", "", ham)
    return _sadelestir(ham)


def _dolu_alan_sayisi(a: models.Asset) -> int:
    """Kaydın ne kadar dolu olduğu — birleştirmede hedef önerisi için."""
    sayi = sum(1 for alan in TASINACAK_ALANLAR if getattr(a, alan, None) not in (None, ""))
    sayi += len(a.custom or {})
    return sayi


def _anahtarlar(a: models.Asset) -> list[tuple[str, str]]:
    """Bu kaydı mükerrer yapabilecek anahtarlar (tür, değer)."""
    anahtar = []
    if a.serial and seri_anahtar(a.serial):
        anahtar.append(("seri", seri_anahtar(a.serial)))
    if a.demirbas_no and seri_anahtar(a.demirbas_no):
        anahtar.append(("demirbas", seri_anahtar(a.demirbas_no)))
    if a.muhasebe_kodu and seri_anahtar(a.muhasebe_kodu):
        anahtar.append(("ifs", seri_anahtar(a.muhasebe_kodu)))
    kok = etiket_koku(a.asset_tag)
    if kok:
        anahtar.append(("etiket", kok))
    return anahtar


def _ozet(a: models.Asset, adlar: dict) -> dict:
    kategori = marka = model = None
    mdl = adlar["modeller"].get(a.model_id)
    if mdl is not None:
        model = mdl.name
        kategori = adlar["kategoriler"].get(mdl.category_id)
        marka = adlar["markalar"].get(mdl.manufacturer_id)
    kisi = adlar["kisiler"].get(a.assigned_user_id)
    yer = adlar["lokasyonlar"].get(a.assigned_location_id)
    return {
        "id": a.id,
        "asset_tag": a.asset_tag,
        "name": a.name,
        "serial": a.serial,
        "demirbas_no": a.demirbas_no,
        "muhasebe_kodu": a.muhasebe_kodu,
        "kategori": kategori,
        "marka": marka,
        "model": model,
        "lokasyon": adlar["lokasyonlar"].get(a.location_id),
        "durum": adlar["durumlar"].get(a.status_id),
        "zimmetli": kisi or yer,
        "zimmet_turu": a.assigned_type.value if a.assigned_type else None,
        "ozellik_grubu": len(a.custom or {}),
        "dosya": adlar["dosyalar"].get(a.id, 0),
        "gecmis": adlar["gecmis"].get(a.id, 0),
        "dolu_alan": _dolu_alan_sayisi(a),
        "eklendi": a.created_at.isoformat() if a.created_at else None,
    }


def gruplar(db: Session) -> list[dict]:
    """Mükerrer olabilecek varlık grupları — en güçlü kanıt önce.

    Aynı cihaza ait kayıtlar tek grupta toplanır: seri no ile eşleşen iki
    kayıt ayrıca etiket kökünden de eşleşiyorsa grup ikiye bölünmez.
    """
    varliklar = db.scalars(select(models.Asset)).all()
    if not varliklar:
        return []

    # --- Birleşen kümeler (union-find): her kayıt bir kümeye girer ---
    ata: dict[int, int] = {a.id: a.id for a in varliklar}

    def kok(x: int) -> int:
        while ata[x] != x:
            ata[x] = ata[ata[x]]
            x = ata[x]
        return x

    def birlestir_kume(x: int, y: int) -> None:
        kx, ky = kok(x), kok(y)
        if kx != ky:
            ata[ky] = kx

    anahtar_sahipleri: dict[tuple[str, str], list[models.Asset]] = {}
    for a in varliklar:
        for anahtar in _anahtarlar(a):
            anahtar_sahipleri.setdefault(anahtar, []).append(a)

    kanit: dict[int, set[str]] = {}
    for (tur, _deger), sahipler in anahtar_sahipleri.items():
        if len(sahipler) < 2:
            continue
        ilk = sahipler[0]
        for digeri in sahipler[1:]:
            birlestir_kume(ilk.id, digeri.id)
        for s in sahipler:
            kanit.setdefault(kok(s.id), set()).add(tur)

    kumeler: dict[int, list[models.Asset]] = {}
    for a in varliklar:
        k = kok(a.id)
        if k in kanit:
            kumeler.setdefault(k, []).append(a)

    # --- Ad çözümlemeleri (tek seferde) ---
    from sqlalchemy import func

    adlar = {
        "modeller": {m.id: m for m in db.scalars(select(models.AssetModel)).all()},
        "kategoriler": {k.id: k.name for k in db.scalars(select(models.Category)).all()},
        "markalar": {m.id: m.name for m in db.scalars(select(models.Manufacturer)).all()},
        "lokasyonlar": {l.id: l.name for l in db.scalars(select(models.Location)).all()},
        "durumlar": {s.id: s.name for s in db.scalars(select(models.StatusLabel)).all()},
        "kisiler": {k.id: " ".join(filter(None, [k.first_name, k.last_name]))
                    for k in db.scalars(select(models.User)).all()},
        "dosyalar": dict(db.execute(
            select(models.AssetFile.asset_id, func.count(models.AssetFile.id))
            .group_by(models.AssetFile.asset_id)).all()),
        "gecmis": dict(db.execute(
            select(models.ActivityLog.item_id, func.count(models.ActivityLog.id))
            .where(models.ActivityLog.item_type == "asset")
            .group_by(models.ActivityLog.item_id)).all()),
    }

    # Kanıt gücü: seri/IFS numarası aynıysa neredeyse kesin; yalnız etiket
    # kökü eşleşiyorsa "olabilir" — sıralama buna göre.
    guc = {"seri": 3, "ifs": 3, "demirbas": 2, "etiket": 1}
    sonuc = []
    for k, kayitlar in kumeler.items():
        turler = sorted(kanit[k], key=lambda t: -guc.get(t, 0))
        # Hedef önerisi: önce ZİMMETLİ kayıt (kullanımdaki cihazın etiketi
        # zimmet fişlerinde geçiyor, o etiket kalsın), sonra en dolu kayıt,
        # eşitlikte en eskisi. Birleştirmede alanlar zaten diğerlerinden
        # tamamlanıyor, hangisi hedef olursa olsun veri kaybolmuyor.
        ozetler = sorted((_ozet(a, adlar) for a in kayitlar),
                         key=lambda o: (0 if o["zimmet_turu"] else 1,
                                        -o["dolu_alan"], o["id"]))
        sonuc.append({
            "anahtar": ozetler[0]["asset_tag"],
            "kanit": turler,
            "guc": max(guc.get(t, 0) for t in turler),
            "onerilen_hedef": ozetler[0]["id"],
            "kayitlar": ozetler,
        })
    sonuc.sort(key=lambda g: (-g["guc"], g["anahtar"]))
    return sonuc


def birlestir(db: Session, hedef_id: int, kaynak_idler: list[int],
              *, aktor: str | None = None) -> dict:
    """Mükerrer varlıkları hedefte toplar; kaynaklar silinir.

    Hedefte BOŞ olan alanlar kaynaklardan doldurulur (dolu veriye
    dokunulmaz), teknik özellikler birleşir, dosya ve geçmiş kayıtları
    hedefe taşınır. Silinen kayıtların künyesi geçmişe not düşülür.
    """
    hedef = db.get(models.Asset, hedef_id)
    if hedef is None:
        raise ValueError("Hedef varlık bulunamadı")
    kaynaklar = []
    for kid in kaynak_idler:
        if kid == hedef_id:
            continue
        kaynak = db.get(models.Asset, kid)
        if kaynak is None:
            raise ValueError(f"Varlık bulunamadı: {kid}")
        kaynaklar.append(kaynak)
    if not kaynaklar:
        raise ValueError("Birleştirilecek kayıt seçilmedi")

    doldurulan: dict[str, str] = {}
    silinen_kunye: list[dict] = []
    dosya = gecmis = 0

    for kaynak in kaynaklar:
        # 1) Boş alanlar kaynaktan dolar
        for alan in TASINACAK_ALANLAR:
            deger = getattr(kaynak, alan, None)
            if deger in (None, ""):
                continue
            if getattr(hedef, alan, None) in (None, ""):
                setattr(hedef, alan, deger)
                doldurulan[alan] = f"{kaynak.asset_tag} → {deger}"

        # 2) Teknik özellikler birleşir (hedeftekiler korunur)
        if kaynak.custom:
            ozel = {g: dict(v) for g, v in (hedef.custom or {}).items()
                    if isinstance(v, dict)}
            for grup, alanlar in (kaynak.custom or {}).items():
                if not isinstance(alanlar, dict):
                    continue
                hedef_grup = dict(ozel.get(grup) or {})
                for alan, deger in alanlar.items():
                    if deger and not hedef_grup.get(alan):
                        hedef_grup[alan] = deger
                        doldurulan[f"{grup} / {alan}"] = f"{kaynak.asset_tag} → {deger}"
                if hedef_grup:
                    ozel[grup] = hedef_grup
            hedef.custom = ozel

        # 3) Zimmet: hedef boştaysa kaynağınki devralınır
        if hedef.assigned_type is None and kaynak.assigned_type is not None:
            hedef.assigned_type = kaynak.assigned_type
            hedef.assigned_user_id = kaynak.assigned_user_id
            hedef.assigned_location_id = kaynak.assigned_location_id
            hedef.assigned_asset_id = kaynak.assigned_asset_id
            hedef.last_checkout = kaynak.last_checkout or dt.datetime.now(dt.timezone.utc)
            doldurulan["zimmet"] = f"{kaynak.asset_tag} → devralındı"

        # 4) Dosyalar ve geçmiş hedefe taşınır
        dosya += db.execute(
            update(models.AssetFile).where(models.AssetFile.asset_id == kaynak.id)
            .values(asset_id=hedef.id)).rowcount
        gecmis += db.execute(
            update(models.ActivityLog)
            .where(models.ActivityLog.item_type == "asset",
                   models.ActivityLog.item_id == kaynak.id)
            .values(item_id=hedef.id)).rowcount
        # Başka bir cihaza takılı görünen kayıtlar da hedefe bağlanır
        db.execute(update(models.Asset)
                   .where(models.Asset.assigned_asset_id == kaynak.id)
                   .values(assigned_asset_id=hedef.id))

        silinen_kunye.append({
            "asset_tag": kaynak.asset_tag,
            "serial": kaynak.serial,
            "demirbas_no": kaynak.demirbas_no,
            "muhasebe_kodu": kaynak.muhasebe_kodu,
            "name": kaynak.name,
        })

    # 5) Kayıt: neyin nereden geldiği geçmişte kalsın
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset", item_id=hedef.id,
        actor=aktor,
        note=("Mükerrer kayıt birleştirildi: "
              + ", ".join(k["asset_tag"] for k in silinen_kunye)
              + f" → {hedef.asset_tag}"
              + (f" ({dosya} dosya, {gecmis} geçmiş kaydı taşındı)"
                 if dosya or gecmis else "")),
        changes={"silinen": {"eski": str(silinen_kunye), "yeni": hedef.asset_tag},
                 **{alan: {"eski": "(boş)", "yeni": deger}
                    for alan, deger in doldurulan.items()}} or None))

    for kaynak in kaynaklar:
        db.delete(kaynak)
    db.commit()
    return {"hedef_id": hedef.id, "hedef_etiket": hedef.asset_tag,
            "silinen": [k["asset_tag"] for k in silinen_kunye],
            "doldurulan": doldurulan, "dosya": dosya, "gecmis": gecmis}
