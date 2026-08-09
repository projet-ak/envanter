"""Stok hareketleri: giriş (+), kişiye zimmet (−) ve tarihçe.

Klavye/fare gibi hep aynı kalemler tekrar tekrar alınıp dağıtılır; `qty`
alanı yalnızca kalan sayıyı söyler. Buradaki uçlar her hareketi kayıt altına
alır: alım yapılınca adet artar, kişiye verilince düşer ve kim/ne zaman/kaç
adet aldığı listelenebilir. Sahip, dosya eklerindeki gibi `kayit_turu +
kayit_id` ikilisiyle tutulur (bkz. models.StockMove).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db
from app.routers.stok_dosyalari import TABLOLAR, _kayit

router = APIRouter(prefix="/stok", tags=["Stok Hareketleri"])
READ = [Depends(get_current_user)]

# Lisansta adet (qty) yok, koltuk (seats) var — hareket adetli türlerle sınırlı
ADETLI = {models.StokTuru.accessory, models.StokTuru.consumable,
          models.StokTuru.component}


def _adetli(kayit_turu: models.StokTuru) -> None:
    if kayit_turu not in ADETLI:
        raise HTTPException(400, "Bu tür için stok hareketi tutulmaz")


def _kisi_adlari(db: Session, hareketler) -> dict[int, str]:
    kimlikler = {h.user_id for h in hareketler if h.user_id}
    if not kimlikler:
        return {}
    return {u.id: " ".join(filter(None, [u.first_name, u.last_name]))
            for u in db.scalars(select(models.User)
                                .where(models.User.id.in_(kimlikler))).all()}


def _hareket_ciktisi(h: models.StockMove, kisiler: dict[int, str]) -> dict:
    return {
        "id": h.id, "islem": h.islem.value, "adet": h.adet,
        "user_id": h.user_id, "kisi": kisiler.get(h.user_id),
        "aciklama": h.aciklama, "yapan": h.yapan, "created_at": h.created_at,
    }


@router.get("/{kayit_turu}/{kayit_id}/hareketler",
            response_model=list[schemas.StockMoveRead], dependencies=READ)
def hareketleri_listele(kayit_turu: models.StokTuru, kayit_id: int,
                        db: Session = Depends(get_db)):
    """Kaydın tüm hareketleri, yeniden eskiye: kim, ne zaman, kaç adet."""
    _kayit(db, kayit_turu, kayit_id)
    hareketler = db.scalars(
        select(models.StockMove)
        .where(models.StockMove.kayit_turu == kayit_turu,
               models.StockMove.kayit_id == kayit_id)
        .order_by(models.StockMove.created_at.desc(),
                  models.StockMove.id.desc())
    ).all()
    kisiler = _kisi_adlari(db, hareketler)
    return [_hareket_ciktisi(h, kisiler) for h in hareketler]


@router.post("/{kayit_turu}/{kayit_id}/giris",
             response_model=schemas.StockMoveRead, status_code=201)
def stok_girisi(kayit_turu: models.StokTuru, kayit_id: int,
                govde: schemas.StokGiris,
                db: Session = Depends(get_db),
                aktor: models.User = Depends(require_editor)):
    """Alım girişi: adet artar, hareket kaydı düşülür."""
    _adetli(kayit_turu)
    kayit = _kayit(db, kayit_turu, kayit_id)
    kayit.qty = (kayit.qty or 0) + govde.adet
    hareket = models.StockMove(
        kayit_turu=kayit_turu, kayit_id=kayit_id,
        islem=models.HareketTuru.giris, adet=govde.adet,
        aciklama=govde.aciklama, yapan=aktor.username or aktor.full_name)
    db.add(hareket)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=kayit_turu.value,
        item_id=kayit_id, actor=hareket.yapan,
        note=f"Stok girişi: +{govde.adet} ({kayit.name}) → kalan {kayit.qty}"))
    db.commit()
    db.refresh(hareket)
    return _hareket_ciktisi(hareket, {})


@router.post("/{kayit_turu}/{kayit_id}/zimmet",
             response_model=schemas.StockMoveRead, status_code=201)
def stok_zimmet(kayit_turu: models.StokTuru, kayit_id: int,
                govde: schemas.StokZimmet,
                db: Session = Depends(get_db),
                aktor: models.User = Depends(require_editor)):
    """Stoktan kişiye verme: adet düşer, kim/ne zaman kaydedilir."""
    _adetli(kayit_turu)
    kayit = _kayit(db, kayit_turu, kayit_id)
    kisi = db.get(models.User, govde.user_id)
    if kisi is None:
        raise HTTPException(404, "Personel bulunamadı")
    if (kayit.qty or 0) < govde.adet:
        raise HTTPException(
            400, f"Stok yetersiz: {kayit.qty or 0} adet var, "
                 f"{govde.adet} adet isteniyor")
    kayit.qty -= govde.adet
    kisi_adi = " ".join(filter(None, [kisi.first_name, kisi.last_name]))
    hareket = models.StockMove(
        kayit_turu=kayit_turu, kayit_id=kayit_id,
        islem=models.HareketTuru.zimmet, adet=govde.adet,
        user_id=kisi.id, aciklama=govde.aciklama,
        yapan=aktor.username or aktor.full_name)
    db.add(hareket)
    db.add(models.ActivityLog(
        action=models.ActivityAction.checkout, item_type=kayit_turu.value,
        item_id=kayit_id, actor=hareket.yapan,
        target_type="user", target_id=kisi.id,
        note=f"{kayit.name}: {govde.adet} adet {kisi_adi} kişisine verildi"
             f" → kalan {kayit.qty}"))
    db.commit()
    db.refresh(hareket)
    return _hareket_ciktisi(hareket, {kisi.id: kisi_adi})


@router.delete("/hareketleri/{hareket_id}", status_code=204)
def hareket_geri_al(hareket_id: int, db: Session = Depends(get_db),
                    aktor: models.User = Depends(require_editor)):
    """Yanlış girilen hareketi geri alır: adet, yönün tersine düzeltilir."""
    hareket = db.get(models.StockMove, hareket_id)
    if hareket is None:
        raise HTTPException(404, "Hareket bulunamadı")
    kayit = _kayit(db, hareket.kayit_turu, hareket.kayit_id)
    if hareket.islem == models.HareketTuru.giris:
        if (kayit.qty or 0) < hareket.adet:
            raise HTTPException(
                400, "Geri alınamaz: giriş sonrası ürünler dağıtılmış "
                     f"(stokta {kayit.qty or 0} adet kaldı)")
        kayit.qty -= hareket.adet
    else:
        kayit.qty = (kayit.qty or 0) + hareket.adet
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=hareket.kayit_turu.value,
        item_id=hareket.kayit_id, actor=aktor.username or aktor.full_name,
        note=f"Hareket geri alındı: {hareket.islem.value} {hareket.adet} adet"
             f" → kalan {kayit.qty}"))
    db.delete(hareket)
    db.commit()


# --------------------------------------------------------------------------- #
# Kayıt silinince hareketlerini de sil (dosya eklerindeki desenle aynı)
# --------------------------------------------------------------------------- #
def _hareketleri_sil(mapper, baglanti, nesne) -> None:
    for tur, (tablo, _) in TABLOLAR.items():
        if isinstance(nesne, tablo):
            baglanti.execute(
                delete(models.StockMove).where(
                    models.StockMove.kayit_turu == tur,
                    models.StockMove.kayit_id == nesne.id,
                )
            )
            return


for _tablo, _ in TABLOLAR.values():
    event.listen(_tablo, "after_delete", _hareketleri_sil)
