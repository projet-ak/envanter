"""Referans tabloları için tekrar eden CRUD uçlarını üreten yardımcı.

NOT: Bu modülde `from __future__ import annotations` KULLANILMAZ — FastAPI'nin
parametre tiplerini çalışma anında (closure değişkeninden) çözebilmesi gerekir.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_editor
from app.database import get_db


def make_crud_router(*, model, create_schema, update_schema, read_schema, prefix, tag):
    router = APIRouter(prefix=prefix, tags=[tag])
    read = [Depends(get_current_user)]   # okuma: giriş şart
    write = [Depends(require_editor)]    # yazma: en az 'editor'

    @router.get("", response_model=list[read_schema], dependencies=read)
    def list_items(
        skip: int = 0,
        limit: int = 100,
        q: str | None = None,
        db: Session = Depends(get_db),
    ):
        stmt = select(model)
        if q and hasattr(model, "name"):
            stmt = stmt.where(model.name.ilike(f"%{q}%"))
        stmt = stmt.offset(skip).limit(limit)
        return db.scalars(stmt).all()

    @router.post("", response_model=read_schema, status_code=201, dependencies=write)
    def create_item(payload: create_schema, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = model(**payload.model_dump(exclude_unset=True))
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @router.get("/{item_id}", response_model=read_schema, dependencies=read)
    def get_item(item_id: int, db: Session = Depends(get_db)):
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, f"{tag} bulunamadı")
        return obj

    @router.put("/{item_id}", response_model=read_schema, dependencies=write)
    def update_item(item_id: int, payload: update_schema, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, f"{tag} bulunamadı")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204, dependencies=write)
    def delete_item(item_id: int, db: Session = Depends(get_db)):
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, f"{tag} bulunamadı")
        db.delete(obj)
        db.commit()

    return router
