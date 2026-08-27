"""Kimlik doğrulama uçları: giriş ve mevcut kullanıcı bilgisi."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import (
    GirisKilitli,
    create_access_token,
    get_current_user,
    giris_dene,
    giris_sifirla,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["Kimlik Doğrulama"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Giriş. Art arda hatalı denemeler hesabı geçici olarak kilitler."""
    try:
        user = giris_dene(db, payload.username, payload.password)
    except GirisKilitli as kilit:
        dakika = max(1, round(kilit.kalan_saniye / 60))
        raise HTTPException(
            429,
            f"Çok fazla hatalı deneme — hesap güvenlik için geçici olarak "
            f"kilitlendi. {dakika} dakika sonra tekrar deneyin.",
            headers={"Retry-After": str(kilit.kalan_saniye)},
        ) from None
    if user is None:
        # Kalan hak sayısı bilerek yazılmaz: yalnız var olan hesaplar için
        # görünürdü ve kullanıcı adı avlamayı kolaylaştırırdı. Uyarı geneldir.
        raise HTTPException(
            401,
            f"Kullanıcı adı veya parola hatalı — {settings.max_login_attempts} "
            f"hatalı denemeden sonra hesap {settings.lockout_minutes} dakika "
            f"kilitlenir.",
        )
    return schemas.TokenResponse(
        access_token=create_access_token(user),
        user=schemas.AuthUser.model_validate(user),
    )


@router.get("/me", response_model=schemas.AuthUser)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=schemas.AuthUser)
def profil_guncelle(
    payload: schemas.ProfilGuncelle,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Kullanıcının kendi bilgilerini güncellemesi (rol ve yetki hariç)."""
    for alan, deger in payload.model_dump(exclude_unset=True).items():
        setattr(user, alan, deger)
    db.commit()
    db.refresh(user)
    return user


@router.post("/parola", status_code=204)
def parola_degistir(
    payload: schemas.ParolaDegistir,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Kendi parolasını değiştirir; mevcut parola doğrulanır."""
    if not user.password_hash or not verify_password(payload.mevcut_parola,
                                                     user.password_hash):
        raise HTTPException(400, "Mevcut parola hatalı")
    if payload.yeni_parola == payload.mevcut_parola:
        raise HTTPException(400, "Yeni parola eskisiyle aynı olamaz")
    user.password_hash = hash_password(payload.yeni_parola)
    db.commit()
    giris_sifirla(db, user)      # parolayı bilen kişi kilitli kalmasın
