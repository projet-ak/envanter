"""Kimlik doğrulama: parola hash'leme, JWT üretimi ve rol tabanlı erişim."""

from __future__ import annotations

import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)

# Rol hiyerarşisi (büyük sayı = daha yetkili)
_ROLE_LEVEL = {UserRole.viewer: 1, UserRole.editor: 2, UserRole.admin: 3}


# --------------------------------------------------------------------------- #
# Parola
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(user: User) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "username": user.username,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Kullanıcı adı + parola doğrular (kilit denetimi YAPMAZ).

    Kilit/sayaç yönetimi için `giris_dene` kullanılır; bu işlev geriye
    dönük uyumluluk ve testler için sade doğrulamayı sürdürür.
    """
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.password_hash or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# --------------------------------------------------------------------------- #
# Kaba kuvvet koruması
# --------------------------------------------------------------------------- #
def kilit_kalan_saniye(user: User) -> int:
    """Hesap kilitliyse kalan süre (saniye), değilse 0."""
    if not user.kilit_bitis:
        return 0
    bitis = user.kilit_bitis
    if bitis.tzinfo is None:                      # SQLite naive döndürür
        bitis = bitis.replace(tzinfo=dt.timezone.utc)
    kalan = (bitis - dt.datetime.now(dt.timezone.utc)).total_seconds()
    return int(kalan) if kalan > 0 else 0


def giris_sifirla(db: Session, user: User) -> None:
    """Başarılı giriş / parola değişimi: sayaç ve kilit temizlenir."""
    if user.basarisiz_giris or user.kilit_bitis:
        user.basarisiz_giris = 0
        user.kilit_bitis = None
        db.commit()


def _basarisiz_isle(db: Session, user: User) -> int:
    """Hatalı denemeyi sayar, sınıra gelindiyse kilitler. Kalan hakkı döner."""
    user.basarisiz_giris = (user.basarisiz_giris or 0) + 1
    kalan_hak = settings.max_login_attempts - user.basarisiz_giris
    if kalan_hak <= 0:
        user.kilit_bitis = (dt.datetime.now(dt.timezone.utc)
                            + dt.timedelta(minutes=settings.lockout_minutes))
        user.basarisiz_giris = 0        # kilit bitince sıfırdan başlasın
        kalan_hak = 0
    db.commit()
    return kalan_hak


class GirisKilitli(Exception):
    """Hesap geçici olarak kilitli — kalan süreyi taşır."""

    def __init__(self, kalan_saniye: int):
        self.kalan_saniye = kalan_saniye
        super().__init__("Hesap geçici olarak kilitli")


def giris_dene(db: Session, username: str, password: str) -> User | None:
    """Kilit denetimli giriş.

    - Hesap kilitliyse doğru parolayla bile `GirisKilitli` atar.
    - Hatalı parola sayacı artırır; sınıra gelen deneme hesabı kilitler
      ve aynı yanıtta `GirisKilitli` ile bildirilir.
    - Başarılı girişte sayaç ve kilit sıfırlanır.

    Kullanıcı adı hiç yoksa None döner (sayaç tutulacak kayıt da yok);
    saldırgana hesabın var olup olmadığı sızmasın diye mesaj hep aynıdır.
    """
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.password_hash or not user.active:
        return None

    kalan = kilit_kalan_saniye(user)
    if kalan:
        raise GirisKilitli(kalan)
    # Süresi dolmuş kilit varsa temizle
    if user.kilit_bitis:
        user.kilit_bitis = None
        user.basarisiz_giris = 0
        db.commit()

    if not verify_password(password, user.password_hash):
        if _basarisiz_isle(db, user) <= 0:
            # Sınıra bu denemeyle gelindi: kullanıcı bir sonraki denemeyi
            # beklemesin, kilidi hemen bildirelim.
            raise GirisKilitli(kilit_kalan_saniye(user))
        return None

    giris_sifirla(db, user)
    return user


# --------------------------------------------------------------------------- #
# Bağımlılıklar
# --------------------------------------------------------------------------- #
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz veya eksik oturum belirteci",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise exc
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise exc
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise exc
    return user


def require_role(minimum: UserRole):
    """Belirtilen minimum role sahip kullanıcıyı gerektiren bağımlılık üretir."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if _ROLE_LEVEL[user.role] < _ROLE_LEVEL[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için en az '{minimum.value}' yetkisi gerekir",
            )
        return user

    return checker


require_editor = require_role(UserRole.editor)
require_admin = require_role(UserRole.admin)
