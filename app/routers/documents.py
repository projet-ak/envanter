"""Belge üretimi: zimmet / iade tutanakları (PDF)."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.pdf.etiket import labels_pdf, qr_png
from app.pdf.zimmet import build_zimmet_pdf

router = APIRouter(prefix="/documents", tags=["Belgeler"])

# Türkçe karakterlerin ASCII karşılıkları (HTTP başlıkları ASCII olmalı)
_TR_MAP = str.maketrans({
    "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
    "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
})


def _ascii_filename(name: str) -> str:
    """Dosya adını ASCII'ye indirger (başlık uyumluluğu için)."""
    folded = name.translate(_TR_MAP)
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in folded)
    return safe.strip("-") or "belge"


def _pdf_response(data: bytes, filename: str) -> Response:
    # Hem ASCII yedeği hem UTF-8 (RFC 5987) sürümü gönderilir; modern
    # tarayıcılar filename* olanı kullanıp Türkçe adı korur.
    ascii_name = _ascii_filename(filename)
    utf8_name = quote(filename, safe="")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
        },
    )


@router.get("/zimmet/asset/{asset_id}.pdf",
            dependencies=[Depends(get_current_user)])
def zimmet_fisi_asset(
    asset_id: int,
    doc_type: str = Query("zimmet", pattern="^(zimmet|iade)$"),
    note: str | None = None,
    db: Session = Depends(get_db),
):
    """Tek varlık için zimmet/iade tutanağı."""
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")

    user = None
    if asset.assigned_user_id:
        user = db.get(models.User, asset.assigned_user_id)

    pdf = build_zimmet_pdf(assets=[asset], user=user, doc_type=doc_type, note=note)
    return _pdf_response(pdf, f"{doc_type}-{asset.asset_tag}.pdf")


@router.get("/zimmet/user/{user_id}.pdf",
            dependencies=[Depends(get_current_user)])
def zimmet_fisi_user(
    user_id: int,
    doc_type: str = Query("zimmet", pattern="^(zimmet|iade)$"),
    note: str | None = None,
    db: Session = Depends(get_db),
):
    """Personele zimmetli tüm varlıklar için tek tutanak."""
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "Personel bulunamadı")

    assets = db.scalars(
        select(models.Asset)
        .where(models.Asset.assigned_user_id == user_id)
        .order_by(models.Asset.asset_tag)
    ).all()
    if not assets:
        raise HTTPException(404, "Bu personele zimmetli varlık yok")

    pdf = build_zimmet_pdf(assets=list(assets), user=user, doc_type=doc_type, note=note)
    ad = "-".join(filter(None, [user.first_name, user.last_name])) or str(user_id)
    return _pdf_response(pdf, f"{doc_type}-{ad}.pdf")


# --------------------------------------------------------------------------- #
# Barkod / QR etiketleri
# --------------------------------------------------------------------------- #
@router.get("/etiket/asset/{asset_id}.png",
            dependencies=[Depends(get_current_user)])
def qr_kod(asset_id: int, db: Session = Depends(get_db)):
    """Varlık için tek QR kod görseli (PNG)."""
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    data = asset.asset_tag or asset.demirbas_no or str(asset.id)
    return Response(content=qr_png(data), media_type="image/png")


@router.get("/etiket/asset/{asset_id}.pdf",
            dependencies=[Depends(get_current_user)])
def etiket_tek(asset_id: int, db: Session = Depends(get_db)):
    """Tek varlık için yazdırılabilir etiket."""
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")
    return _pdf_response(labels_pdf([asset]), f"etiket-{asset.asset_tag}.pdf")


@router.post("/etiketler.pdf", dependencies=[Depends(get_current_user)])
def etiket_toplu(payload: schemas.LabelRequest, db: Session = Depends(get_db)):
    """Seçilen varlıklar için toplu etiket sayfası (A4, sayfa başına 24 etiket)."""
    stmt = select(models.Asset)
    if payload.asset_ids:
        stmt = stmt.where(models.Asset.id.in_(payload.asset_ids))
    if payload.location_id is not None:
        stmt = stmt.where(models.Asset.location_id == payload.location_id)
    assets = db.scalars(stmt.order_by(models.Asset.asset_tag).limit(500)).all()
    if not assets:
        raise HTTPException(404, "Etiket üretilecek varlık bulunamadı")

    pdf = labels_pdf(list(assets), show_barcode=payload.show_barcode,
                     start_offset=payload.start_offset)
    return _pdf_response(pdf, "etiketler.pdf")


@router.get("/tara", response_model=schemas.AssetRead,
            dependencies=[Depends(get_current_user)])
def barkod_tara(
    kod: str = Query(..., min_length=1, description="Okutulan barkod/QR içeriği"),
    db: Session = Depends(get_db),
):
    """Okutulan barkodu varlıkla eşleştirir (etiket, demirbaş, barkod, seri, IMEI)."""
    kod = kod.strip()
    asset = db.scalar(
        select(models.Asset).where(
            (models.Asset.asset_tag == kod)
            | (models.Asset.demirbas_no == kod)
            | (models.Asset.barkod == kod)
            | (models.Asset.serial == kod)
            | (models.Asset.imei == kod)
        )
    )
    if asset is None:
        raise HTTPException(404, f"'{kod}' ile eşleşen varlık bulunamadı")
    return asset
