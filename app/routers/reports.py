"""Raporlar ve dashboard özetleri."""

from __future__ import annotations

import datetime as dt
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, rapor
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/reports", tags=["Raporlar"],
                   dependencies=[Depends(get_current_user)])


def _group_count(db: Session, join_model, label_col, fk_col) -> list[dict]:
    """Varlıkları bir referans tablosuna göre gruplayıp sayar."""
    rows = db.execute(
        select(label_col, func.count(models.Asset.id))
        .select_from(models.Asset)
        .join(join_model, fk_col == join_model.id, isouter=True)
        .group_by(label_col)
        .order_by(func.count(models.Asset.id).desc())
    ).all()
    return [{"ad": name or "(belirtilmemiş)", "adet": count} for name, count in rows]


@router.get("/ozet")
def ozet(db: Session = Depends(get_db)):
    """Dashboard için genel özet."""
    toplam = db.scalar(select(func.count()).select_from(models.Asset)) or 0
    zimmetli = db.scalar(
        select(func.count()).select_from(models.Asset)
        .where(models.Asset.assigned_type.is_not(None))
    ) or 0

    toplam_deger = db.scalar(
        select(func.coalesce(func.sum(models.Asset.purchase_cost), 0))
    ) or 0

    sayilar = {}
    for key, model in [("aksesuar", models.Accessory), ("sarf", models.Consumable),
                       ("bilesen", models.Component), ("lisans", models.License),
                       ("personel", models.User), ("lokasyon", models.Location)]:
        sayilar[key] = db.scalar(select(func.count()).select_from(model)) or 0

    # Veri kalitesi: markası boş model kaç cihazı etkiliyor?
    markasiz_model_idler = db.scalars(
        select(models.AssetModel.id)
        .where(models.AssetModel.manufacturer_id.is_(None))).all()
    markasiz_cihaz = db.scalar(
        select(func.count()).select_from(models.Asset)
        .where(models.Asset.model_id.in_(markasiz_model_idler))
    ) or 0 if markasiz_model_idler else 0

    return {
        "varlik_toplam": toplam,
        "zimmetli": zimmetli,
        "bosta": toplam - zimmetli,
        "toplam_deger": float(toplam_deger),
        "markasiz_cihaz": markasiz_cihaz,
        **sayilar,
    }


@router.get("/dagilim")
def dagilim(db: Session = Depends(get_db)):
    """Kategori, lokasyon, üretici ve duruma göre dağılım."""
    return {
        "kategori": _kategori_dagilim(db),
        "lokasyon": _group_count(
            db, models.Location, models.Location.name, models.Asset.location_id
        ),
        "durum": _group_count(
            db, models.StatusLabel, models.StatusLabel.name, models.Asset.status_id
        ),
        "uretici": _uretici_dagilim(db),
    }


def _kategori_dagilim(db: Session) -> list[dict]:
    """Kategori dağılımı — asset → model → category zinciri üzerinden."""
    rows = db.execute(
        select(models.Category.name, func.count(models.Asset.id))
        .select_from(models.Asset)
        .join(models.AssetModel, models.Asset.model_id == models.AssetModel.id,
              isouter=True)
        .join(models.Category, models.AssetModel.category_id == models.Category.id,
              isouter=True)
        .group_by(models.Category.name)
        .order_by(func.count(models.Asset.id).desc())
    ).all()
    return [{"ad": name or "(belirtilmemiş)", "adet": count} for name, count in rows]


def _uretici_dagilim(db: Session) -> list[dict]:
    rows = db.execute(
        select(models.Manufacturer.name, func.count(models.Asset.id))
        .select_from(models.Asset)
        .join(models.AssetModel, models.Asset.model_id == models.AssetModel.id,
              isouter=True)
        .join(models.Manufacturer,
              models.AssetModel.manufacturer_id == models.Manufacturer.id, isouter=True)
        .group_by(models.Manufacturer.name)
        .order_by(func.count(models.Asset.id).desc())
    ).all()
    return [{"ad": name or "(belirtilmemiş)", "adet": count} for name, count in rows]


@router.get("/dusuk-stok")
def dusuk_stok(db: Session = Depends(get_db)):
    """Adedi minimum seviyenin altına düşen aksesuar/sarf/bileşenler."""
    sonuc = []
    for tur, model in [("aksesuar", models.Accessory), ("sarf", models.Consumable),
                       ("bilesen", models.Component)]:
        rows = db.scalars(
            select(model).where(model.qty <= model.min_qty, model.min_qty > 0)
            .order_by(model.qty)
        ).all()
        for item in rows:
            sonuc.append({"tur": tur, "id": item.id, "ad": item.name,
                          "adet": item.qty, "min": item.min_qty})
    return sonuc


@router.get("/garanti")
def garanti_bitenler(
    gun: int = Query(90, ge=1, le=3650, description="Kaç gün içinde bitenler"),
    db: Session = Depends(get_db),
):
    """Garantisi yaklaşan veya bitmiş varlıklar."""
    bugun = dt.date.today()
    sinir = bugun + dt.timedelta(days=gun)
    rows = db.scalars(
        select(models.Asset)
        .where(models.Asset.warranty_end.is_not(None),
               models.Asset.warranty_end <= sinir)
        .order_by(models.Asset.warranty_end)
        .limit(500)
    ).all()
    return [{
        "id": a.id, "asset_tag": a.asset_tag, "ad": a.name,
        "demirbas_no": a.demirbas_no,
        "garanti_bitis": a.warranty_end.isoformat() if a.warranty_end else None,
        "kalan_gun": (a.warranty_end - bugun).days if a.warranty_end else None,
        "bitti": bool(a.warranty_end and a.warranty_end < bugun),
    } for a in rows]


@router.get("/personel-zimmet")
def personel_zimmet(db: Session = Depends(get_db)):
    """Personel başına zimmetli cihaz sayısı."""
    rows = db.execute(
        select(models.User.id, models.User.first_name, models.User.last_name,
               models.User.department, func.count(models.Asset.id))
        .select_from(models.User)
        .join(models.Asset, models.Asset.assigned_user_id == models.User.id)
        .group_by(models.User.id, models.User.first_name, models.User.last_name,
                  models.User.department)
        .order_by(func.count(models.Asset.id).desc())
    ).all()
    return [{
        "user_id": uid,
        "ad": " ".join(filter(None, [first, last])),
        "departman": dept,
        "cihaz_sayisi": count,
    } for uid, first, last, dept, count in rows]


@router.get("/lisans-kullanim")
def lisans_kullanim(db: Session = Depends(get_db)):
    """Lisansların koltuk sayısı ve bitiş tarihleri."""
    bugun = dt.date.today()
    rows = db.scalars(select(models.License).order_by(models.License.name)).all()
    return [{
        "id": lic.id, "ad": lic.name, "koltuk": lic.seats,
        "bitis": lic.expiration_date.isoformat() if lic.expiration_date else None,
        "suresi_doldu": bool(lic.expiration_date and lic.expiration_date < bugun),
    } for lic in rows]


@router.get("/son-islemler")
def son_islemler(limit: int = Query(12, le=50), db: Session = Depends(get_db)):
    """Son etkinlikler: kim, neye, ne yaptı — dashboard'un canlı akışı."""
    etiketler = dict(db.execute(
        select(models.Asset.id, models.Asset.asset_tag)).all())
    kisiler = {k.id: k.full_name for k in db.scalars(select(models.User)).all()}
    EYLEM = {"create": "eklendi", "update": "güncellendi", "delete": "silindi",
             "checkout": "zimmetlendi", "checkin": "iade alındı",
             "audit": "sayıldı"}

    sonuc = []
    for g in db.scalars(select(models.ActivityLog)
                        .order_by(models.ActivityLog.created_at.desc(),
                                  models.ActivityLog.id.desc())
                        .limit(limit)).all():
        if g.item_type == "asset":
            hedef = etiketler.get(g.item_id) or f"cihaz #{g.item_id}"
        elif g.item_type == "user":
            hedef = kisiler.get(g.item_id) or f"kişi #{g.item_id}"
        else:
            hedef = f"{g.item_type} #{g.item_id}"
        sonuc.append({
            "hedef": hedef,
            "hedef_tur": g.item_type,
            "hedef_id": g.item_id,
            "eylem": EYLEM.get(g.action.value, g.action.value),
            "not": g.note,
            "yapan": g.actor,
            "tarih": g.created_at.isoformat() if g.created_at else None,
        })
    return sonuc


@router.get("/excel")
def excel_raporu(tip: str = Query("genel", description="|".join(rapor.RAPOR_ADLARI)),
                 db: Session = Depends(get_db)):
    """Biçimli Excel raporu üretir (başlık, süzgeç, zebra, TR biçimleri)."""
    if tip not in rapor.RAPOR_ADLARI:
        raise HTTPException(400, f"Bilinmeyen rapor tipi: {tip}. "
                                 f"Geçerli: {', '.join(rapor.RAPOR_ADLARI)}")
    icerik = rapor.olustur(db, tip)
    ad = f"{rapor.RAPOR_ADLARI[tip]} {dt.date.today():%d.%m.%Y}.xlsx"
    return Response(
        icerik,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{quote(ad)}"},
    )
