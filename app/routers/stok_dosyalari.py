"""Aksesuar / sarf / bileşen / lisans kayıtlarına dosya eki.

Depolama kuralları `app/depo.py`'de ortaktır; buradaki tek fark sahibin dört
tablodan biri olabilmesi. Yabancı anahtar yerine `kayit_turu + kayit_id`
ikilisi tutulur (bkz. models.StockFile) ve kayıt silinince ekleri aşağıdaki
`after_delete` dinleyicisi temizler. Diskteki içerik, cihaz eklerinde olduğu
gibi yerinde kalır — yedekten geri dönmek gerekebilir diye.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app import depo, models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/stok", tags=["Dosyalar"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]

# Kayıt türü -> tablo ve dosya adı ön eki
TABLOLAR = {
    models.StokTuru.accessory: (models.Accessory, "a"),
    models.StokTuru.consumable: (models.Consumable, "s"),
    models.StokTuru.component: (models.Component, "b"),
    models.StokTuru.license: (models.License, "l"),
}


def _kayit(db: Session, kayit_turu: models.StokTuru, kayit_id: int):
    tablo, _ = TABLOLAR[kayit_turu]
    nesne = db.get(tablo, kayit_id)
    if nesne is None:
        raise HTTPException(404, f"{kayit_turu.value} kaydı bulunamadı")
    return nesne


@router.get("/{kayit_turu}/{kayit_id}/dosyalar",
            response_model=list[schemas.StockFileRead], dependencies=READ)
def dosyalari_listele(kayit_turu: models.StokTuru, kayit_id: int,
                      db: Session = Depends(get_db)):
    _kayit(db, kayit_turu, kayit_id)
    return db.scalars(
        select(models.StockFile)
        .where(models.StockFile.kayit_turu == kayit_turu,
               models.StockFile.kayit_id == kayit_id)
        .order_by(models.StockFile.created_at.desc())
    ).all()


@router.post("/{kayit_turu}/{kayit_id}/dosyalar",
             response_model=schemas.StockFileRead, status_code=201,
             dependencies=WRITE)
async def dosya_yukle(
    kayit_turu: models.StokTuru,
    kayit_id: int,
    file: UploadFile = File(...),
    tur: models.DosyaTuru = Form(models.DosyaTuru.diger),
    aciklama: str | None = Form(None),
    db: Session = Depends(get_db),
    yukleyen: models.User = Depends(get_current_user),
):
    """Stok kaydına dosya ekler (ürün fotoğrafı, fatura, lisans belgesi…)."""
    _kayit(db, kayit_turu, kayit_id)

    alanlar = await depo.diske_yaz(file, tur, kayit_id,
                                   on_ek=TABLOLAR[kayit_turu][1])
    kayit = models.StockFile(
        kayit_turu=kayit_turu, kayit_id=kayit_id, aciklama=aciklama,
        yukleyen=yukleyen.username or yukleyen.full_name, **alanlar)
    db.add(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=kayit_turu.value,
        item_id=kayit_id, note=f"Dosya eklendi: {kayit.dosya_adi}",
        actor=kayit.yukleyen,
    ))
    db.commit()
    db.refresh(kayit)
    return kayit


@router.get("/dosyalari/{dosya_id}", dependencies=READ)
def dosya_indir(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.StockFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    return depo.indir(kayit)


@router.delete("/dosyalari/{dosya_id}", status_code=204, dependencies=WRITE)
def dosya_sil(dosya_id: int, db: Session = Depends(get_db)):
    kayit = db.get(models.StockFile, dosya_id)
    if kayit is None:
        raise HTTPException(404, "Dosya bulunamadı")
    depo.diskten_sil(kayit)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=kayit.kayit_turu.value,
        item_id=kayit.kayit_id, note=f"Dosya silindi: {kayit.dosya_adi}",
    ))
    db.delete(kayit)
    db.commit()


# --------------------------------------------------------------------------- #
# Kayıt silinince eklerini de sil
# --------------------------------------------------------------------------- #
def _ekleri_sil(mapper, baglanti, nesne) -> None:
    """Yabancı anahtar olmadığı için temizliği burada yapıyoruz.

    `after_delete` aynı işlemin içinde çalışır: silme geri alınırsa dosya
    kayıtları da geri gelir.
    """
    for tur, (tablo, _) in TABLOLAR.items():
        if isinstance(nesne, tablo):
            baglanti.execute(
                delete(models.StockFile).where(
                    models.StockFile.kayit_turu == tur,
                    models.StockFile.kayit_id == nesne.id,
                )
            )
            return


for _tablo, _ in TABLOLAR.values():
    event.listen(_tablo, "after_delete", _ekleri_sil)
