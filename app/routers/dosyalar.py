"""Cihaz dosya ekleri: fotoğraf, imzalı zimmet formu, fatura…

Dosyalar veritabanına değil diske yazılır (`settings.upload_dir`). Yükleme
adları kullanıcıdan gelmez — sunucu üretir — böylece yol geçişi (``../``) ve
ad çakışması mümkün olmaz.
"""

from __future__ import annotations

import mimetypes
import secrets
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, require_editor
from app.config import settings
from app.database import get_db

router = APIRouter(tags=["Dosyalar"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]

# Kabul edilen türler. Yürütülebilir/betik içerik alınmaz.
IZINLI_UZANTILAR = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic",   # görseller
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",    # belgeler
}
GORSEL_UZANTILAR = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic"}


def yukleme_dizini() -> Path:
    d = Path(settings.upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _uzanti(ad: str) -> str:
    return Path(ad).suffix.lower()


def _guvenli_ad(ad: str) -> str:
    """Görüntülenecek dosya adını zararsız hâle getirir (yol bileşeni değil)."""
    ad = Path(ad).name                       # dizin kısmını at
    ad = unicodedata.normalize("NFC", ad)
    return ad[:200] or "dosya"


def _dosya_yolu(kayit: models.AssetFile) -> Path:
    return yukleme_dizini() / kayit.saklama_adi


@router.get("/assets/{asset_id}/dosyalar",
            response_model=list[schemas.AssetFileRead], dependencies=READ)
def dosyalari_listele(asset_id: int, db: Session = Depends(get_db)):
    if db.get(models.Asset, asset_id) is None:
        raise HTTPException(404, "Varlık bulunamadı")
    return db.scalars(
        select(models.AssetFile)
        .where(models.AssetFile.asset_id == asset_id)
        .order_by(models.AssetFile.created_at.desc())
    ).all()


@router.post("/assets/{asset_id}/dosyalar", response_model=schemas.AssetFileRead,
             status_code=201, dependencies=WRITE)
async def dosya_yukle(
    asset_id: int,
    file: UploadFile = File(...),
    tur: models.DosyaTuru = Form(models.DosyaTuru.diger),
    aciklama: str | None = Form(None),
    db: Session = Depends(get_db),
    yukleyen: models.User = Depends(get_current_user),
):
    """Cihaza dosya ekler (fotoğraf, imzalı zimmet formu, fatura…)."""
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Varlık bulunamadı")

    ad = _guvenli_ad(file.filename or "dosya")
    uzanti = _uzanti(ad)
    if uzanti not in IZINLI_UZANTILAR:
        raise HTTPException(
            415, f"'{uzanti or 'uzantısız'}' dosya türü kabul edilmiyor. "
                 f"İzinliler: {', '.join(sorted(IZINLI_UZANTILAR))}")
    if tur == models.DosyaTuru.gorsel and uzanti not in GORSEL_UZANTILAR:
        raise HTTPException(415, "Cihaz görseli için bir resim dosyası seçin")

    icerik = await file.read()
    sinir = settings.max_upload_mb * 1024 * 1024
    if len(icerik) > sinir:
        raise HTTPException(
            413, f"Dosya çok büyük ({len(icerik) // 1024 // 1024} MB). "
                 f"Sınır: {settings.max_upload_mb} MB")
    if not icerik:
        raise HTTPException(400, "Dosya boş")

    # Diskteki ad sunucu tarafından üretilir: çakışma ve yol geçişi olmaz.
    saklama_adi = f"{asset_id}-{secrets.token_hex(8)}{uzanti}"
    (yukleme_dizini() / saklama_adi).write_bytes(icerik)

    kayit = models.AssetFile(
        asset_id=asset_id,
        tur=tur,
        dosya_adi=ad,
        saklama_adi=saklama_adi,
        content_type=file.content_type or mimetypes.guess_type(ad)[0],
        boyut=len(icerik),
        aciklama=aciklama,
        yukleyen=yukleyen.username or yukleyen.full_name,
    )
    db.add(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset", item_id=asset_id,
        note=f"Dosya eklendi: {ad}", actor=kayit.yukleyen,
    ))
    db.commit()
    db.refresh(kayit)
    return kayit


@router.get("/dosyalar/{dosya_id}", dependencies=READ)
def dosya_indir(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.AssetFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    yol = _dosya_yolu(kayit)
    if not yol.exists():
        raise HTTPException(404, "Dosya diskte bulunamadı")

    # Görseller tarayıcıda gösterilsin, diğerleri indirilsin.
    icerde = _uzanti(kayit.dosya_adi) in GORSEL_UZANTILAR
    yerlesim = "inline" if icerde else "attachment"
    return FileResponse(
        yol,
        media_type=kayit.content_type or "application/octet-stream",
        headers={"Content-Disposition":
                 f"{yerlesim}; filename*=UTF-8''{quote(kayit.dosya_adi)}"},
    )


@router.delete("/dosyalar/{dosya_id}", status_code=204, dependencies=WRITE)
def dosya_sil(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.AssetFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    _dosya_yolu(kayit).unlink(missing_ok=True)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset",
        item_id=kayit.asset_id, note=f"Dosya silindi: {kayit.dosya_adi}",
    ))
    db.delete(kayit)
    db.commit()
