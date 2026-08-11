"""Referans tabloları için tekrar eden CRUD uçlarını üreten yardımcı.

NOT: Bu modülde `from __future__ import annotations` KULLANILMAZ — FastAPI'nin
parametre tiplerini çalışma anında (closure değişkeninden) çözebilmesi gerekir.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_editor
from app.database import get_db
from app.excel.sema import _sadelestir


def make_crud_router(*, model, create_schema, update_schema, read_schema,
                     prefix, tag, essiz_ad: bool = False, dogrula=None):
    """`essiz_ad=True` verilen tablolarda aynı ada ikinci kayıt açılamaz.

    Karşılaştırma _sadelestir ile yapılır: "ŞANTİYE U026", "Şantiye U026" ve
    "santiye u026" aynı sayılır. Mükerrer lokasyon/kategori kayıtlarının ana
    kaynağı buydu — içe aktarım Python tarafında eşleştirse de elle eklenen
    ikinci yazım listeyi bölüyordu.

    `dogrula(db, veri, mevcut)` tabloya özgü ek kurallar için: yazımdan önce
    çağrılır, kural bozuluyorsa HTTPException atar (mevcut=None → yeni kayıt).
    """
    router = APIRouter(prefix=prefix, tags=[tag])
    read = [Depends(get_current_user)]   # okuma: giriş şart
    write = [Depends(require_editor)]    # yazma: en az 'editor'

    def _ayni_adli(db: Session, ad, haric_id=None):
        if not (essiz_ad and ad and hasattr(model, "name")):
            return None
        anahtar = _sadelestir(ad)
        for kimlik, mevcut_ad in db.execute(select(model.id, model.name)).all():
            if kimlik != haric_id and mevcut_ad \
                    and _sadelestir(mevcut_ad) == anahtar:
                return mevcut_ad
        return None

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
        veri = payload.model_dump(exclude_unset=True)
        ayni = _ayni_adli(db, veri.get("name"))
        if ayni:
            raise HTTPException(
                409, f"Aynı adla kayıt zaten var: {ayni}. "
                     "Mükerrer kayıt açmak yerine mevcut kaydı kullanın.")
        if dogrula:
            dogrula(db, veri, None)
        obj = model(**veri)
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
        veri = payload.model_dump(exclude_unset=True)
        ayni = _ayni_adli(db, veri.get("name"), haric_id=item_id)
        if ayni:
            raise HTTPException(
                409, f"Aynı adla başka kayıt var: {ayni}.")
        if dogrula:
            dogrula(db, veri, obj)
        for key, value in veri.items():
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
