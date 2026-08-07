"""Detay uçları: cihazın tüm özellikleri, kişinin zimmetli cihazları."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/detay", tags=["Detay"],
                   dependencies=[Depends(get_current_user)])


def _ad(nesne) -> str | None:
    return nesne.name if nesne is not None else None


def _kisi_adi(k: models.User | None) -> str | None:
    if k is None:
        return None
    return " ".join(filter(None, [k.first_name, k.last_name]))


def _varlik_ozeti(db: Session, a: models.Asset) -> dict:
    mdl = db.get(models.AssetModel, a.model_id) if a.model_id else None
    return {
        "id": a.id,
        "asset_tag": a.asset_tag,
        "name": a.name,
        "serial": a.serial,
        "demirbas_no": a.demirbas_no,
        "kategori": _ad(db.get(models.Category, mdl.category_id))
                    if mdl and mdl.category_id else None,
        "marka": _ad(db.get(models.Manufacturer, mdl.manufacturer_id))
                 if mdl and mdl.manufacturer_id else None,
        "model": _ad(mdl),
        "durum": _ad(db.get(models.StatusLabel, a.status_id)) if a.status_id else None,
        "lokasyon": _ad(db.get(models.Location, a.location_id))
                    if a.location_id else None,
        "ip_address": a.ip_address,
        "purchase_cost": float(a.purchase_cost) if a.purchase_cost else None,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "warranty_end": a.warranty_end.isoformat() if a.warranty_end else None,
    }


@router.get("/asset/{asset_id}")
def varlik_detay(asset_id: int, db: Session = Depends(get_db)):
    """Cihazın tüm bilgileri: künye, teknik özellikler, zimmet, geçmiş."""
    a = db.get(models.Asset, asset_id)
    if a is None:
        raise HTTPException(404, "Cihaz bulunamadı")

    mdl = db.get(models.AssetModel, a.model_id) if a.model_id else None
    zimmetli = db.get(models.User, a.assigned_user_id) if a.assigned_user_id else None

    gecmis = db.scalars(
        select(models.ActivityLog)
        .where(models.ActivityLog.item_type == "asset",
               models.ActivityLog.item_id == asset_id)
        .order_by(models.ActivityLog.created_at.desc())
        .limit(30)
    ).all()

    return {
        "kunye": {
            **_varlik_ozeti(db, a),
            "muhasebe_kodu": a.muhasebe_kodu,
            "fatura_no": a.fatura_no,
            "barkod": a.barkod,
            "imei": a.imei,
            "mac_address": a.mac_address,
            "hostname": a.hostname,
            "telefon_no": a.telefon_no,
            "sim_no": a.sim_no,
            "operator": a.operator,
            "tedarikci": _ad(db.get(models.Supplier, a.supplier_id))
                         if a.supplier_id else None,
            "sirket": _ad(db.get(models.Company, a.company_id))
                      if a.company_id else None,
            "notes": a.notes,
        },
        "zimmet": {
            "tur": a.assigned_type.value if a.assigned_type else None,
            "kisi_id": zimmetli.id if zimmetli else None,
            "kisi": _kisi_adi(zimmetli),
            "departman": zimmetli.department if zimmetli else None,
            "unvan": zimmetli.job_title if zimmetli else None,
            "lokasyon": _ad(db.get(models.Location, a.assigned_location_id))
                        if a.assigned_location_id else None,
            "tarih": a.last_checkout.isoformat() if a.last_checkout else None,
        },
        # Teknik özellikler zaten gruplu JSON olarak saklanıyor
        "ozellikler": a.custom or {},
        "dosyalar": [
            {
                "id": d.id,
                "tur": d.tur.value,
                "dosya_adi": d.dosya_adi,
                "content_type": d.content_type,
                "boyut": d.boyut,
                "aciklama": d.aciklama,
                "yukleyen": d.yukleyen,
                "tarih": d.created_at.isoformat() if d.created_at else None,
            }
            for d in a.dosyalar
        ],
        "gecmis": [
            {
                "islem": g.action.value,
                "not": g.note,
                "degisiklikler": g.changes,
                "tarih": g.created_at.isoformat() if g.created_at else None,
            }
            for g in gecmis
        ],
    }


@router.get("/user/{user_id}")
def kisi_detay(user_id: int, db: Session = Depends(get_db)):
    """Kişinin bilgileri ve zimmetindeki tüm cihazlar (özellikleriyle)."""
    k = db.get(models.User, user_id)
    if k is None:
        raise HTTPException(404, "Personel bulunamadı")

    varliklar = db.scalars(
        select(models.Asset)
        .where(models.Asset.assigned_user_id == user_id)
        .order_by(models.Asset.asset_tag)
    ).all()

    cihazlar = []
    tur_sayilari: dict[str, int] = {}
    toplam_deger = 0.0
    for a in varliklar:
        ozet = _varlik_ozeti(db, a)
        ozet["ozellikler"] = a.custom or {}
        cihazlar.append(ozet)
        tur = ozet["kategori"] or "Diğer"
        tur_sayilari[tur] = tur_sayilari.get(tur, 0) + 1
        toplam_deger += ozet["purchase_cost"] or 0.0

    return {
        "kisi": {
            "id": k.id,
            "ad": _kisi_adi(k),
            "employee_num": k.employee_num,
            "department": k.department,
            "job_title": k.job_title,
            "sube": k.sube,
            "email": k.email,
            "telefon": k.telefon,
            "lokasyon": _ad(db.get(models.Location, k.location_id))
                        if k.location_id else None,
        },
        "cihaz_sayisi": len(cihazlar),
        "tur_dagilimi": dict(sorted(tur_sayilari.items(), key=lambda x: -x[1])),
        "toplam_deger": toplam_deger,
        "cihazlar": cihazlar,
    }
