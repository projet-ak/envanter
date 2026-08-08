"""Cihaz ve kişi dosya ekleri: fotoğraf, imzalı zimmet formu, fatura…

Depolama kuralları (klasörler, doğrulama, yol güvenliği) `app/depo.py`'de
tektir; burada yalnızca sahibi bulup doğru tabloya yazan uçlar var. Zimmet
formu tek bir cihaza değil KİŞİYE aittir — bir form o kişinin birden çok
cihazını listeler — bu yüzden kişi ekleri ayrı tabloda durur.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import depo, models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(tags=["Dosyalar"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]


# --------------------------------------------------------------------------- #
# Cihaz ekleri
# --------------------------------------------------------------------------- #
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
    if db.get(models.Asset, asset_id) is None:
        raise HTTPException(404, "Varlık bulunamadı")

    alanlar = await depo.diske_yaz(file, tur, asset_id)
    kayit = models.AssetFile(
        asset_id=asset_id, aciklama=aciklama,
        yukleyen=yukleyen.username or yukleyen.full_name, **alanlar)
    db.add(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset", item_id=asset_id,
        note=f"Dosya eklendi: {kayit.dosya_adi}", actor=kayit.yukleyen,
    ))
    db.commit()
    db.refresh(kayit)
    return kayit


@router.get("/dosyalar/{dosya_id}", dependencies=READ)
def dosya_indir(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.AssetFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    return depo.indir(kayit)


@router.delete("/dosyalar/{dosya_id}", status_code=204, dependencies=WRITE)
def dosya_sil(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.AssetFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    depo.diskten_sil(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="asset",
        item_id=kayit.asset_id, note=f"Dosya silindi: {kayit.dosya_adi}",
    ))
    db.delete(kayit)
    db.commit()


# --------------------------------------------------------------------------- #
# Kişi ekleri — imzalı zimmet formu kişiye aittir, tek cihaza değil
# --------------------------------------------------------------------------- #
@router.get("/users/{user_id}/dosyalar",
            response_model=list[schemas.UserFileRead], dependencies=READ)
def kisi_dosyalari(user_id: int, db: Session = Depends(get_db)):
    if db.get(models.User, user_id) is None:
        raise HTTPException(404, "Kişi bulunamadı")
    return db.scalars(
        select(models.UserFile)
        .where(models.UserFile.user_id == user_id)
        .order_by(models.UserFile.created_at.desc())
    ).all()


@router.post("/users/{user_id}/dosyalar", response_model=schemas.UserFileRead,
             status_code=201, dependencies=WRITE)
async def kisi_dosya_yukle(
    user_id: int,
    file: UploadFile = File(...),
    tur: models.DosyaTuru = Form(models.DosyaTuru.zimmet_formu),
    aciklama: str | None = Form(None),
    db: Session = Depends(get_db),
    yukleyen: models.User = Depends(get_current_user),
):
    """Kişiye dosya ekler (imzalı zimmet formu, tutanak…)."""
    if db.get(models.User, user_id) is None:
        raise HTTPException(404, "Kişi bulunamadı")

    alanlar = await depo.diske_yaz(file, tur, user_id, on_ek="k")
    kayit = models.UserFile(
        user_id=user_id, aciklama=aciklama,
        yukleyen=yukleyen.username or yukleyen.full_name, **alanlar)
    db.add(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="user", item_id=user_id,
        note=f"Dosya eklendi: {kayit.dosya_adi}", actor=kayit.yukleyen,
    ))
    db.commit()
    db.refresh(kayit)
    return kayit


@router.get("/kisi-dosyalari/{dosya_id}", dependencies=READ)
def kisi_dosya_indir(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.UserFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    return depo.indir(kayit)


@router.delete("/kisi-dosyalari/{dosya_id}", status_code=204, dependencies=WRITE)
def kisi_dosya_sil(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.UserFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    depo.diskten_sil(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="user",
        item_id=kayit.user_id, note=f"Dosya silindi: {kayit.dosya_adi}",
    ))
    db.delete(kayit)
    db.commit()
