"""Varlık (asset) uçları: CRUD, zimmet (checkout/checkin) ve geçmiş."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/assets", tags=["Varlıklar"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]


def _log(
    db: Session,
    *,
    action: models.ActivityAction,
    asset_id: int,
    target_type: str | None = None,
    target_id: int | None = None,
    note: str | None = None,
    changes: dict | None = None,
    actor: str | None = None,
) -> None:
    db.add(
        models.ActivityLog(
            action=action,
            item_type="asset",
            item_id=asset_id,
            target_type=target_type,
            target_id=target_id,
            note=note,
            changes=changes,
            actor=actor,
        )
    )


@router.get("", response_model=list[schemas.AssetRead], dependencies=READ)
def list_assets(
    skip: int = 0,
    limit: int = Query(100, le=1000),
    status_id: int | None = None,
    location_id: int | None = None,
    model_id: int | None = None,
    category_id: int | None = Query(None, description="Cihaz türü (model üzerinden)"),
    manufacturer_id: int | None = Query(None, description="Marka (model üzerinden)"),
    user_id: int | None = Query(None, description="Zimmetli olduğu personel"),
    assigned: bool | None = Query(None, description="true=zimmetli, false=boşta"),
    q: str | None = Query(None, description="Etiket/seri/ad/demirbaş içinde ara"),
    db: Session = Depends(get_db),
):
    stmt = select(models.Asset)
    if status_id is not None:
        stmt = stmt.where(models.Asset.status_id == status_id)
    if location_id is not None:
        stmt = stmt.where(models.Asset.location_id == location_id)
    if model_id is not None:
        stmt = stmt.where(models.Asset.model_id == model_id)
    if user_id is not None:
        stmt = stmt.where(models.Asset.assigned_user_id == user_id)
    # Kategori ve marka bilgisi modelde tutulur; model üzerinden filtrele
    if category_id is not None or manufacturer_id is not None:
        stmt = stmt.join(
            models.AssetModel, models.Asset.model_id == models.AssetModel.id
        )
        if category_id is not None:
            stmt = stmt.where(models.AssetModel.category_id == category_id)
        if manufacturer_id is not None:
            stmt = stmt.where(models.AssetModel.manufacturer_id == manufacturer_id)
    if assigned is True:
        stmt = stmt.where(models.Asset.assigned_type.is_not(None))
    elif assigned is False:
        stmt = stmt.where(models.Asset.assigned_type.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            models.Asset.asset_tag.ilike(like)
            | models.Asset.serial.ilike(like)
            | models.Asset.name.ilike(like)
            | models.Asset.demirbas_no.ilike(like)
            | models.Asset.ip_address.ilike(like)
        )
    stmt = stmt.order_by(models.Asset.asset_tag).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.get("/sayi", dependencies=READ)
def asset_sayisi(
    status_id: int | None = None,
    location_id: int | None = None,
    category_id: int | None = None,
    manufacturer_id: int | None = None,
    user_id: int | None = None,
    assigned: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """Filtrelere uyan toplam kayıt sayısı (sayfalamadan bağımsız)."""
    from sqlalchemy import func

    stmt = select(func.count(models.Asset.id))
    if status_id is not None:
        stmt = stmt.where(models.Asset.status_id == status_id)
    if location_id is not None:
        stmt = stmt.where(models.Asset.location_id == location_id)
    if user_id is not None:
        stmt = stmt.where(models.Asset.assigned_user_id == user_id)
    if category_id is not None or manufacturer_id is not None:
        stmt = stmt.join(
            models.AssetModel, models.Asset.model_id == models.AssetModel.id
        )
        if category_id is not None:
            stmt = stmt.where(models.AssetModel.category_id == category_id)
        if manufacturer_id is not None:
            stmt = stmt.where(models.AssetModel.manufacturer_id == manufacturer_id)
    if assigned is True:
        stmt = stmt.where(models.Asset.assigned_type.is_not(None))
    elif assigned is False:
        stmt = stmt.where(models.Asset.assigned_type.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            models.Asset.asset_tag.ilike(like)
            | models.Asset.serial.ilike(like)
            | models.Asset.name.ilike(like)
            | models.Asset.demirbas_no.ilike(like)
            | models.Asset.ip_address.ilike(like)
        )
    return {"toplam": db.scalar(stmt) or 0}


@router.post("", response_model=schemas.AssetRead, status_code=201, dependencies=WRITE)
def create_asset(payload: schemas.AssetCreate, db: Session = Depends(get_db)):
    if db.scalar(select(models.Asset).where(models.Asset.asset_tag == payload.asset_tag)):
        raise HTTPException(409, f"'{payload.asset_tag}' etiketi zaten kullanımda")
    asset = models.Asset(**payload.model_dump())
    db.add(asset)
    db.flush()
    _log(db, action=models.ActivityAction.create, asset_id=asset.id)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=schemas.AssetRead, dependencies=READ)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    return asset


@router.put("/{asset_id}", response_model=schemas.AssetRead, dependencies=WRITE)
def update_asset(
    asset_id: int, payload: schemas.AssetUpdate, db: Session = Depends(get_db)
):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    changes: dict = {}
    for key, value in payload.model_dump(exclude_unset=True).items():
        old = getattr(asset, key)
        if old != value:
            changes[key] = {"eski": str(old), "yeni": str(value)}
        setattr(asset, key, value)
    if changes:
        _log(db, action=models.ActivityAction.update, asset_id=asset.id, changes=changes)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=204, dependencies=WRITE)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    _log(db, action=models.ActivityAction.delete, asset_id=asset.id)
    db.delete(asset)
    db.commit()


@router.post("/{asset_id}/checkout", response_model=schemas.AssetRead, dependencies=WRITE)
def checkout_asset(
    asset_id: int, payload: schemas.CheckoutRequest, db: Session = Depends(get_db)
):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    if asset.assigned_type is not None:
        raise HTTPException(409, "Varlık zaten zimmetli, önce iade alın")

    target_model = {
        models.AssignedType.user: models.User,
        models.AssignedType.location: models.Location,
        models.AssignedType.asset: models.Asset,
    }[payload.assigned_type]
    if db.get(target_model, payload.assigned_id) is None:
        raise HTTPException(404, "Zimmet hedefi bulunamadı")

    asset.assigned_type = payload.assigned_type
    asset.assigned_user_id = None
    asset.assigned_location_id = None
    asset.assigned_asset_id = None
    if payload.assigned_type == models.AssignedType.user:
        asset.assigned_user_id = payload.assigned_id
    elif payload.assigned_type == models.AssignedType.location:
        asset.assigned_location_id = payload.assigned_id
    else:
        asset.assigned_asset_id = payload.assigned_id
    asset.last_checkout = dt.datetime.now(dt.timezone.utc)
    asset.expected_checkin = payload.expected_checkin

    _log(
        db,
        action=models.ActivityAction.checkout,
        asset_id=asset.id,
        target_type=payload.assigned_type.value,
        target_id=payload.assigned_id,
        note=payload.note,
        actor=payload.actor,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/checkin", response_model=schemas.AssetRead, dependencies=WRITE)
def checkin_asset(
    asset_id: int, payload: schemas.CheckinRequest, db: Session = Depends(get_db)
):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    if asset.assigned_type is None:
        raise HTTPException(409, "Varlık zaten boşta")

    prev_type = asset.assigned_type.value
    prev_id = asset.assigned_user_id or asset.assigned_location_id or asset.assigned_asset_id

    asset.assigned_type = None
    asset.assigned_user_id = None
    asset.assigned_location_id = None
    asset.assigned_asset_id = None
    asset.last_checkout = None
    asset.expected_checkin = None
    if payload.location_id is not None:
        asset.location_id = payload.location_id

    _log(
        db,
        action=models.ActivityAction.checkin,
        asset_id=asset.id,
        target_type=prev_type,
        target_id=prev_id,
        note=payload.note,
        actor=payload.actor,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{asset_id}/history", response_model=list[schemas.ActivityLogRead], dependencies=READ)
def asset_history(asset_id: int, db: Session = Depends(get_db)):
    if db.get(models.Asset, asset_id) is None:
        raise HTTPException(404, "Varlık bulunamadı")
    stmt = (
        select(models.ActivityLog)
        .where(
            models.ActivityLog.item_type == "asset",
            models.ActivityLog.item_id == asset_id,
        )
        .order_by(models.ActivityLog.created_at.desc())
    )
    return db.scalars(stmt).all()
