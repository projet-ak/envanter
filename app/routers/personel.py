"""Personel arama ucu — zimmet verirken kişi seçmek için.

DİKKAT — yol sırası: `/users/ara`, `crud_factory`'nin ürettiği
`/users/{item_id}` ile aynı ön eki paylaşır. FastAPI yolları kayıt sırasına
göre eşleştirdiği için bu router `app/main.py` içinde lookups router'larından
ÖNCE eklenmelidir; aksi hâlde "ara" bir kimlik sanılıp 422 döner.
(tests/test_personel_secimi.py bunu doğrular.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import arama, models, schemas
from app.auth import (get_current_user, hash_password,
                      kilit_kalan_saniye, require_admin)
from app.database import get_db

router = APIRouter(prefix="/users", tags=["Personel"])


@router.get("/ara", dependencies=[Depends(get_current_user)])
def personel_ara(
    q: str = Query("", description="Ad soyad, sicil no, departman veya şube"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Ada göre personel arar; her kişinin taşıdığı cihaz sayısını da verir.

    Terim boşken en çok cihaz taşıyanlar listelenir.
    """
    return arama.personel_ara(db, q, limit=limit)


# --------------------------------------------------------------------------- #
# Hesap yönetimi (yalnızca yönetici)
# --------------------------------------------------------------------------- #
def _hesap(k: models.User) -> dict:
    return {
        "id": k.id,
        "username": k.username,
        "first_name": k.first_name,
        "last_name": k.last_name,
        "email": k.email,
        "department": k.department,
        "role": k.role,
        "active": k.active,
        "girebilir": bool(k.username and k.password_hash),
        # Kaba kuvvet kilidi: hesap ekranında görünür, yönetici açabilir
        "kilitli": kilit_kalan_saniye(k) > 0,
        "kilit_kalan_dk": (kilit_kalan_saniye(k) + 59) // 60 or None,
    }


@router.get("/hesaplar", response_model=list[schemas.HesapRead],
            dependencies=[Depends(require_admin)])
def hesaplar(db: Session = Depends(get_db)):
    """Giriş yetkisi olan (ya da olabilecek) kullanıcılar.

    Personel listesi yüzlerce kişi olabilir; burada yalnızca kullanıcı adı
    tanımlanmış olanlar listelenir — hesap yönetimi ekranının konusu bunlar.
    """
    kisiler = db.scalars(
        select(models.User).where(models.User.username.is_not(None))
        .order_by(models.User.username)
    ).all()
    return [_hesap(k) for k in kisiler]


@router.put("/{user_id}/hesap", response_model=schemas.HesapRead)
def hesap_ayarla(
    user_id: int,
    payload: schemas.HesapAyarla,
    db: Session = Depends(get_db),
    yonetici: models.User = Depends(require_admin),
):
    """Kullanıcı adı / rol / parola / hesap durumu ayarlar.

    Personel kaydına kullanıcı adı + parola verilerek giriş yetkisi açılır.
    """
    kisi = db.get(models.User, user_id)
    if kisi is None:
        raise HTTPException(404, "Personel bulunamadı")

    veri = payload.model_dump(exclude_unset=True)

    # Yönetici kendi yetkisini düşürüp sistemi kilitlemesin
    if kisi.id == yonetici.id:
        if veri.get("role") and veri["role"] != models.UserRole.admin:
            raise HTTPException(400, "Kendi yönetici yetkinizi kaldıramazsınız")
        if veri.get("active") is False:
            raise HTTPException(400, "Kendi hesabınızı kapatamazsınız")

    if "username" in veri and veri["username"]:
        kullanilan = db.scalar(
            select(models.User).where(models.User.username == veri["username"],
                                      models.User.id != user_id)
        )
        if kullanilan is not None:
            raise HTTPException(409, f"'{veri['username']}' kullanıcı adı zaten alınmış")
        kisi.username = veri["username"]

    if veri.get("yeni_parola"):
        if not kisi.username:
            raise HTTPException(400, "Önce kullanıcı adı tanımlayın")
        kisi.password_hash = hash_password(veri["yeni_parola"])
        # Yeni parola verildiyse kilidin sürmesi anlamsız
        kisi.basarisiz_giris = 0
        kisi.kilit_bitis = None
    if veri.get("kilidi_ac"):
        kisi.basarisiz_giris = 0
        kisi.kilit_bitis = None
    if "role" in veri and veri["role"]:
        kisi.role = veri["role"]
    if "active" in veri and veri["active"] is not None:
        kisi.active = veri["active"]

    # Sistem yöneticisiz kalmasın: değişikliği oturuma yansıtıp say, sıfırsa geri al
    db.flush()
    if not db.scalar(
        select(func.count(models.User.id)).where(
            models.User.role == models.UserRole.admin,
            models.User.active.is_(True),
            models.User.password_hash.is_not(None),
        )
    ):
        db.rollback()
        raise HTTPException(400, "Sistemde giriş yapabilen en az bir yönetici kalmalı")

    db.commit()
    db.refresh(kisi)
    return _hesap(kisi)
