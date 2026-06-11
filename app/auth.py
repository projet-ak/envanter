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
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.password_hash or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
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
