"""Kimlik doğrulama uçları: giriş ve mevcut kullanıcı bilgisi."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import authenticate, create_access_token, get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["Kimlik Doğrulama"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(401, "Kullanıcı adı veya parola hatalı")
    return schemas.TokenResponse(
        access_token=create_access_token(user),
        user=schemas.AuthUser.model_validate(user),
    )


@router.get("/me", response_model=schemas.AuthUser)
def me(user: User = Depends(get_current_user)):
    return user
