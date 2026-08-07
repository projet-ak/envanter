"""Ağ / network ürünleri uçları.

Ağ ürünleri normal varlıklardır (bkz. app/ag.py); bu router yalnızca türe
özel bir görünüm ve toplu ekleme kolaylığı sunar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ag, models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/ag", tags=["Ağ Ürünleri"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]


@router.get("/sablon", dependencies=READ)
def sablon():
    """Ağ ürün türleri ve her türün teknik alanları (arayüz formu bundan üretilir)."""
    return ag.sablon()


@router.get("/urunler", dependencies=READ)
def urunler(
    tur: str | None = Query(None, description="switch, sfp, access_point, router…"),
    location_id: int | None = None,
    proje_kodu: str | None = None,
    durum_id: int | None = None,
    q: str | None = Query(None, description="Marka/model/seri/özellik içinde ara"),
    db: Session = Depends(get_db),
):
    if tur and tur not in ag.TURLER:
        raise HTTPException(400, f"Bilinmeyen tür: {tur}")
    return ag.urunler(db, tur=tur, location_id=location_id, proje_kodu=proje_kodu,
                      durum_id=durum_id, q=q)


@router.get("/ozet", dependencies=READ)
def ozet(db: Session = Depends(get_db)):
    return ag.ozet(db)


@router.get("/transferler", dependencies=READ)
def transferler(limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    """Lokasyonu değişen cihazlar — hangi şantiyeden hangisine gitti."""
    return ag.transferler(db, limit=limit)


# --------------------------------------------------------------------------- #
# Ekleme
# --------------------------------------------------------------------------- #
def _referans(db: Session, model, ad: str | None):
    """Ada göre kaydı bulur, yoksa oluşturur (Türkçe duyarlı karşılaştırma)."""
    from app.excel.sema import _sadelestir

    ad = (ad or "").strip()
    if not ad:
        return None
    aranan = _sadelestir(ad)
    for nesne in db.scalars(select(model)).all():
        if nesne.name and _sadelestir(nesne.name) == aranan:
            return nesne
    nesne = model(name=ad)
    db.add(nesne)
    db.flush()
    return nesne


def _model_bul(db: Session, tur: str, marka_adi: str | None, model_adi: str | None):
    """Ağ ürünü için model kaydını bulur/oluşturur ve doğru kategoriye bağlar."""
    kategori = _referans(db, models.Category, ag.kategori_adi(tur))
    marka = _referans(db, models.Manufacturer, marka_adi)
    ad = (model_adi or "").strip() or (marka_adi or "").strip() or ag.kategori_adi(tur)

    from app.excel.sema import _sadelestir
    aranan = _sadelestir(ad)
    for m in db.scalars(select(models.AssetModel)).all():
        if (m.name and _sadelestir(m.name) == aranan
                and m.category_id == kategori.id
                and m.manufacturer_id == (marka.id if marka else None)):
            return m
    m = models.AssetModel(name=ad, category_id=kategori.id,
                          manufacturer_id=marka.id if marka else None)
    db.add(m)
    db.flush()
    return m


@router.post("/urunler", status_code=201, dependencies=WRITE)
def urun_ekle(payload: schemas.AgUrunEkle, db: Session = Depends(get_db)):
    """Ağ ürünü ekler: kategori, marka ve model gerekirse kendiliğinden açılır."""
    if payload.tur not in ag.TURLER:
        raise HTTPException(400, f"Bilinmeyen tür: {payload.tur}")

    etiket = (payload.asset_tag or "").strip() or (payload.serial or "").strip()
    if not etiket:
        raise HTTPException(400, "Cihaz no ya da seri no zorunlu")
    if db.scalar(select(models.Asset).where(models.Asset.asset_tag == etiket)):
        raise HTTPException(409, f"'{etiket}' etiketi zaten kullanımda")

    mdl = _model_bul(db, payload.tur, payload.marka, payload.model)
    varlik = models.Asset(
        asset_tag=etiket,
        name=payload.ad or " ".join(filter(None, [payload.marka, payload.model])) or None,
        serial=payload.serial or None,
        demirbas_no=payload.demirbas_no or None,
        ip_address=payload.ip_address or None,
        model_id=mdl.id,
        location_id=payload.location_id,
        status_id=payload.status_id,
        notes=payload.notes or None,
        custom={ag.GRUP: {k: v for k, v in (payload.ozellikler or {}).items() if v}},
    )
    db.add(varlik)
    db.flush()
    db.add(models.ActivityLog(action=models.ActivityAction.create,
                              item_type="asset", item_id=varlik.id,
                              note=f"Ağ ürünü eklendi ({ag.TURLER[payload.tur]['ad']})"))
    db.commit()
    db.refresh(varlik)
    return {"id": varlik.id, "asset_tag": varlik.asset_tag}


@router.put("/urunler/{asset_id}/ozellikler", dependencies=WRITE)
def ozellikleri_yaz(asset_id: int, ozellikler: dict[str, str],
                    db: Session = Depends(get_db)):
    """Ağ özelliklerini topluca günceller (boş değerler silinir)."""
    varlik = db.get(models.Asset, asset_id)
    if varlik is None:
        raise HTTPException(404, "Varlık bulunamadı")

    # JSON sütunu yerinde değişikliği izlemez; yeni sözlük atanır
    ozel = {g: dict(v) for g, v in (varlik.custom or {}).items() if isinstance(v, dict)}
    temiz = {k: v for k, v in ozellikler.items() if v not in (None, "")}
    if temiz:
        ozel[ag.GRUP] = temiz
    else:
        ozel.pop(ag.GRUP, None)
    varlik.custom = ozel

    db.add(models.ActivityLog(action=models.ActivityAction.update,
                              item_type="asset", item_id=asset_id,
                              note="Ağ özellikleri güncellendi"))
    db.commit()
    return {"id": asset_id, "ozellikler": temiz}
