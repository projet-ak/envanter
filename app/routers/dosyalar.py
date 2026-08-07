"""Cihaz dosya ekleri: fotoğraf, imzalı zimmet formu, fatura…

İçerik veritabanında değil diskte durur; veritabanında yalnızca **göreli yol**
saklanır (`AssetFile.yol`). Klasörler türe ve tarihe göre ayrılır:

    yuklemeler/
      gorseller/2026/08/12-a1b2c3d4e5f6a7b8.png
      belgeler/2026/08/12-9f8e7d6c5b4a3210.pdf
      faturalar/2026/08/...

Neden tarih klasörü: tek klasörde on binlerce dosya biriktiğinde listeleme ve
yedekleme yavaşlar; ay bazlı bölme bunu önler ve arşivlemeyi kolaylaştırır.

Dosya adları kullanıcıdan gelmez — sunucu üretir — böylece yol geçişi (``../``)
ve ad çakışması mümkün olmaz. Okuma sırasında da yolun kök klasörün altında
kaldığı ayrıca doğrulanır.
"""

from __future__ import annotations

import datetime as dt
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


# Tür -> klasör adı
KLASORLER = {
    models.DosyaTuru.gorsel: "gorseller",
    models.DosyaTuru.zimmet_formu: "belgeler",
    models.DosyaTuru.fatura: "faturalar",
    models.DosyaTuru.diger: "belgeler",
}


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


def yeni_yol(asset_id: int, tur: models.DosyaTuru, uzanti: str) -> str:
    """Yeni dosya için göreli yol üretir: <klasör>/<yıl>/<ay>/<id>-<rastgele><uz>."""
    bugun = dt.date.today()
    return (f"{KLASORLER.get(tur, 'belgeler')}/{bugun:%Y/%m}/"
            f"{asset_id}-{secrets.token_hex(8)}{uzanti}")


def tam_yol(goreli: str) -> Path:
    """Göreli yolu diskteki tam yola çevirir ve kök klasörün altında tutar.

    Veritabanındaki değer bozulsa ya da elle değiştirilse bile yükleme
    klasörünün dışına çıkılamaz.
    """
    kok = yukleme_dizini().resolve()
    hedef = (kok / goreli).resolve()
    if not hedef.is_relative_to(kok):
        raise HTTPException(400, "Geçersiz dosya yolu")
    return hedef


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

    # Diskteki yol sunucu tarafından üretilir: çakışma ve yol geçişi olmaz.
    goreli = yeni_yol(asset_id, tur, uzanti)
    hedef = tam_yol(goreli)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(icerik)

    kayit = models.AssetFile(
        asset_id=asset_id,
        tur=tur,
        dosya_adi=ad,
        yol=goreli,
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
    yol = tam_yol(kayit.yol)
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
    tam_yol(kayit.yol).unlink(missing_ok=True)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset",
        item_id=kayit.asset_id, note=f"Dosya silindi: {kayit.dosya_adi}",
    ))
    db.delete(kayit)
    db.commit()
