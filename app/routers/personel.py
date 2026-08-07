"""Personel arama ucu — zimmet verirken kişi seçmek için.

DİKKAT — yol sırası: `/users/ara`, `crud_factory`'nin ürettiği
`/users/{item_id}` ile aynı ön eki paylaşır. FastAPI yolları kayıt sırasına
göre eşleştirdiği için bu router `app/main.py` içinde lookups router'larından
ÖNCE eklenmelidir; aksi hâlde "ara" bir kimlik sanılıp 422 döner.
(tests/test_personel_secimi.py bunu doğrular.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import arama
from app.auth import get_current_user
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
