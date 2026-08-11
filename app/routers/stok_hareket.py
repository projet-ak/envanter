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

# Lisansta adet (qty) yerine koltuk (seats) var: koltuk sayısı TOPLAM
# kapasitedir, kişiye verilince azalmaz — kalan = seats - dağıtılan.
# Adetli türlerde ise qty kalan stoğu tutar, zimmetle birebir düşer.
LISANS = models.StokTuru.license


def _dagitilan(db: Session, kayit_turu: models.StokTuru, kayit_id: int) -> int:
    from sqlalchemy import func

    return int(db.scalar(
        select(func.coalesce(func.sum(models.StockMove.adet), 0))
        .where(models.StockMove.kayit_turu == kayit_turu,
               models.StockMove.kayit_id == kayit_id,
               models.StockMove.islem == models.HareketTuru.zimmet)) or 0)


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


@router.get("/{kayit_turu}/dagilim-ozet", dependencies=READ)
def dagilim_ozeti(kayit_turu: models.StokTuru, db: Session = Depends(get_db)):
    """Tür içindeki her kayıt için dağıtılan adet ve kişi sayısı.

    Liste ekranı "Zimmet" sütununu tek istekle doldurur: kayıt başına
    toplam verilen adet + kaç farklı kişide olduğu.
    """
    from sqlalchemy import func

    satirlar = db.execute(
        select(models.StockMove.kayit_id,
               func.sum(models.StockMove.adet),
               func.count(func.distinct(models.StockMove.user_id)))
        .where(models.StockMove.kayit_turu == kayit_turu,
               models.StockMove.islem == models.HareketTuru.zimmet)
        .group_by(models.StockMove.kayit_id)).all()
    return [{"kayit_id": k, "dagitilan": int(a or 0), "kisi": int(n or 0)}
            for k, a, n in satirlar]


@router.get("/{kayit_turu}/{kayit_id}/dagilim", dependencies=READ)
def dagilim(kayit_turu: models.StokTuru, kayit_id: int,
            db: Session = Depends(get_db)):
    """Kaydın kimlerde olduğu: kişi başına adet + kişinin lokasyonu/projesi.

    "Hangi projede kaç kişide zimmet var" sorusunun cevabı: kişiler
    lokasyonlarıyla listelenir, altta lokasyon bazlı toplam verilir.
    """
    from sqlalchemy import func

    _kayit(db, kayit_turu, kayit_id)
    satirlar = db.execute(
        select(models.StockMove.user_id, func.sum(models.StockMove.adet))
        .where(models.StockMove.kayit_turu == kayit_turu,
               models.StockMove.kayit_id == kayit_id,
               models.StockMove.islem == models.HareketTuru.zimmet,
               models.StockMove.user_id.is_not(None))
        .group_by(models.StockMove.user_id)).all()

    lokasyonlar = {l.id: l for l in db.scalars(select(models.Location)).all()}
    kisiler = []
    lokasyon_toplami: dict[str, dict] = {}
    for uid, adet in satirlar:
        k = db.get(models.User, uid)
        if k is None:
            continue
        lok = lokasyonlar.get(k.location_id)
        kisiler.append({
            "user_id": uid,
            "ad": " ".join(filter(None, [k.first_name, k.last_name])),
            "adet": int(adet or 0),
            "lokasyon": lok.name if lok else None,
            "proje_kodu": lok.proje_kodu if lok else None,
        })
        anahtar = lok.name if lok else "(lokasyonsuz)"
        t = lokasyon_toplami.setdefault(anahtar, {
            "lokasyon": anahtar,
            "proje_kodu": lok.proje_kodu if lok else None,
            "adet": 0, "kisi": 0})
        t["adet"] += int(adet or 0)
        t["kisi"] += 1

    kisiler.sort(key=lambda x: -x["adet"])
    return {
        "kisiler": kisiler,
        "lokasyonlar": sorted(lokasyon_toplami.values(),
                              key=lambda x: -x["adet"]),
    }


@router.post("/{kayit_turu}/{kayit_id}/giris",
             response_model=schemas.StockMoveRead, status_code=201)
def stok_girisi(kayit_turu: models.StokTuru, kayit_id: int,
                govde: schemas.StokGiris,
                db: Session = Depends(get_db),
                aktor: models.User = Depends(require_editor)):
    """Alım girişi: adet (lisansta koltuk) artar, hareket kaydı düşülür."""
    kayit = _kayit(db, kayit_turu, kayit_id)
    if kayit_turu == LISANS:
        kayit.seats = (kayit.seats or 0) + govde.adet
        kalan_metni = f"toplam {kayit.seats} koltuk"
    else:
        kayit.qty = (kayit.qty or 0) + govde.adet
        kalan_metni = f"kalan {kayit.qty}"
    hareket = models.StockMove(
        kayit_turu=kayit_turu, kayit_id=kayit_id,
        islem=models.HareketTuru.giris, adet=govde.adet,
        aciklama=govde.aciklama, yapan=aktor.username or aktor.full_name)
    db.add(hareket)
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=kayit_turu.value,
        item_id=kayit_id, actor=hareket.yapan,
        note=f"Stok girişi: +{govde.adet} ({kayit.name}) → {kalan_metni}"))
    db.commit()
    db.refresh(hareket)
    return _hareket_ciktisi(hareket, {})


@router.post("/{kayit_turu}/{kayit_id}/zimmet",
             response_model=schemas.StockMoveRead, status_code=201)
def stok_zimmet(kayit_turu: models.StokTuru, kayit_id: int,
                govde: schemas.StokZimmet,
                db: Session = Depends(get_db),
                aktor: models.User = Depends(require_editor)):
    """Stoktan kişiye verme: adet düşer (lisansta koltuk dolar), kaydedilir."""
    kayit = _kayit(db, kayit_turu, kayit_id)
    kisi = db.get(models.User, govde.user_id)
    if kisi is None:
        raise HTTPException(404, "Personel bulunamadı")
    if kayit_turu == LISANS:
        bos = (kayit.seats or 0) - _dagitilan(db, kayit_turu, kayit_id)
        if bos < govde.adet:
            raise HTTPException(
                400, f"Koltuk yetersiz: {bos} koltuk boşta, "
                     f"{govde.adet} isteniyor")
    else:
        if (kayit.qty or 0) < govde.adet:
            raise HTTPException(
                400, f"Stok yetersiz: {kayit.qty or 0} adet var, "
                     f"{govde.adet} adet isteniyor")
        kayit.qty -= govde.adet
    kisi_adi = " ".join(filter(None, [kisi.first_name, kisi.last_name]))
    kalan_metni = (f"boşta {(kayit.seats or 0) - _dagitilan(db, kayit_turu, kayit_id) - govde.adet} koltuk"
                   if kayit_turu == LISANS else f"kalan {kayit.qty}")
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
             f" → {kalan_metni}"))
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
    if hareket.kayit_turu == LISANS:
        # Koltuk zimmet kaydı silinince "dağıtılan" kendiliğinden düşer;
        # yalnızca giriş geri alınırken toplam koltuk azaltılır.
        if hareket.islem == models.HareketTuru.giris:
            dagitilan = _dagitilan(db, hareket.kayit_turu, hareket.kayit_id)
            if (kayit.seats or 0) - hareket.adet < dagitilan:
                raise HTTPException(
                    400, "Geri alınamaz: eklenen koltuklar dağıtılmış "
                         f"({dagitilan} koltuk kullanımda)")
            kayit.seats -= hareket.adet
        kalan_metni = f"toplam {kayit.seats} koltuk"
    elif hareket.islem == models.HareketTuru.giris:
        if (kayit.qty or 0) < hareket.adet:
            raise HTTPException(
                400, "Geri alınamaz: giriş sonrası ürünler dağıtılmış "
                     f"(stokta {kayit.qty or 0} adet kaldı)")
        kayit.qty -= hareket.adet
        kalan_metni = f"kalan {kayit.qty}"
    else:
        kayit.qty = (kayit.qty or 0) + hareket.adet
        kalan_metni = f"kalan {kayit.qty}"
    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type=hareket.kayit_turu.value,
        item_id=hareket.kayit_id, actor=aktor.username or aktor.full_name,
        note=f"Hareket geri alındı: {hareket.islem.value} {hareket.adet} adet"
             f" → {kalan_metni}"))
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
