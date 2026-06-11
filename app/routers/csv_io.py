"""Varlıklar için CSV içe/dışa aktarım."""

from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/io", tags=["CSV İçe/Dışa Aktarım"])

# Dışa/içe aktarımda kullanılan sütunlar (asset_tag zorunlu)
COLUMNS = [
    "asset_tag", "name", "serial", "model_id", "status_id", "location_id",
    "supplier_id", "company_id", "purchase_date", "purchase_cost",
    "order_number", "warranty_months", "notes",
]
_INT_FIELDS = {"model_id", "status_id", "location_id", "supplier_id",
               "company_id", "warranty_months"}


@router.get(
    "/assets.csv",
    dependencies=[Depends(get_current_user)],
    response_class=StreamingResponse,
)
def export_assets_csv(db: Session = Depends(get_db)):
    """Tüm varlıkları CSV olarak indirir."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for asset in db.scalars(select(models.Asset)):
        writer.writerow({c: getattr(asset, c) for c in COLUMNS})
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=varliklar.csv"},
    )


def _to_int(value):
    value = (value or "").strip()
    return int(value) if value else None


def _to_float(value):
    value = (value or "").strip().replace(",", "")
    return float(value) if value else None


def _to_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


@router.post("/assets/import", dependencies=[Depends(require_editor)])
async def import_assets_csv(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """CSV'den varlık içe aktarır. `asset_tag`'e göre ekler veya günceller."""
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames or "asset_tag" not in reader.fieldnames:
        raise HTTPException(400, "CSV 'asset_tag' sütunu içermeli")

    created = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # 1 = başlık satırı
        tag = (row.get("asset_tag") or "").strip()
        if not tag:
            skipped += 1
            errors.append(f"Satır {i}: asset_tag boş")
            continue

        values = {
            "name": (row.get("name") or "").strip() or None,
            "serial": (row.get("serial") or "").strip() or None,
            "order_number": (row.get("order_number") or "").strip() or None,
            "notes": (row.get("notes") or "").strip() or None,
            "purchase_date": _to_date(row.get("purchase_date")),
            "purchase_cost": _to_float(row.get("purchase_cost")),
        }
        for field in _INT_FIELDS:
            if field in row:
                values[field] = _to_int(row.get(field))

        asset = db.scalar(select(models.Asset).where(models.Asset.asset_tag == tag))
        if asset is None:
            asset = models.Asset(asset_tag=tag, **values)
            db.add(asset)
            db.flush()
            db.add(models.ActivityLog(action=models.ActivityAction.create,
                                      item_type="asset", item_id=asset.id,
                                      note="CSV içe aktarım"))
            created += 1
        else:
            for key, value in values.items():
                setattr(asset, key, value)
            updated += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped,
            "errors": errors[:50]}
