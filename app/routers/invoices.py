"""Fatura / irsaliye okuma ve okunan kalemleri envantere aktarma."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.fatura import (
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_PDF_TYPE,
    AIUnavailable,
    extract_invoice,
)
from app.auth import require_editor
from app.database import get_db

router = APIRouter(prefix="/invoices", tags=["Fatura Okuma"],
                   dependencies=[Depends(require_editor)])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/oku", response_model=schemas.InvoiceExtraction)
async def fatura_oku(file: UploadFile = File(...)):
    """Fatura görselinden/PDF'inden kalemleri çıkarır (kaydetmez, önizleme)."""
    media_type = (file.content_type or "").lower()
    if media_type not in SUPPORTED_IMAGE_TYPES | {SUPPORTED_PDF_TYPE}:
        raise HTTPException(
            400,
            "Desteklenen biçimler: JPEG, PNG, GIF, WebP görseller veya PDF."
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "Dosya boş")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Dosya 10 MB'tan büyük olamaz")

    try:
        return extract_invoice(data, media_type)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc))


def _next_tag(db: Session, prefix: str) -> str:
    """Ön eke göre kullanılmayan bir varlık etiketi üretir (PREFIX-0001)."""
    count = db.scalar(
        select(func.count()).select_from(models.Asset)
        .where(models.Asset.asset_tag.like(f"{prefix}-%"))
    ) or 0
    n = count + 1
    while True:
        candidate = f"{prefix}-{n:04d}"
        exists = db.scalar(
            select(models.Asset).where(models.Asset.asset_tag == candidate)
        )
        if exists is None:
            return candidate
        n += 1


@router.post("/aktar")
def fatura_aktar(payload: schemas.InvoiceImportRequest, db: Session = Depends(get_db)):
    """Onaylanan fatura kalemlerini envantere ekler.

    Her kalem için `adet` kadar ayrı varlık kaydı oluşturulur (her cihaz
    kendi etiketini alır). Seri no yalnızca adet 1 ise atanır.
    """
    if not payload.kalemler:
        raise HTTPException(400, "Aktarılacak kalem yok")

    olusan: list[dict] = []
    for kalem in payload.kalemler:
        prefix = (kalem.asset_tag_prefix or "BT").strip().upper() or "BT"
        for _ in range(kalem.adet):
            tag = _next_tag(db, prefix)
            asset = models.Asset(
                asset_tag=tag,
                name=kalem.ad,
                serial=kalem.seri_no if kalem.adet == 1 else None,
                purchase_cost=kalem.birim_fiyat,
                purchase_date=payload.purchase_date or dt.date.today(),
                fatura_no=payload.fatura_no,
                supplier_id=payload.supplier_id,
                location_id=payload.location_id,
                status_id=payload.status_id,
            )
            db.add(asset)
            db.flush()
            db.add(models.ActivityLog(
                action=models.ActivityAction.create,
                item_type="asset", item_id=asset.id,
                note=f"Faturadan aktarıldı ({payload.fatura_no or 'fatura no yok'})",
            ))
            olusan.append({"id": asset.id, "asset_tag": tag, "ad": kalem.ad})

    db.commit()
    return {"eklenen": len(olusan), "varliklar": olusan}
