"""Doğal dil arama ucu."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.ai import search as ai_search
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/search", tags=["Arama"])


@router.post(
    "", response_model=schemas.SearchResponse, dependencies=[Depends(get_current_user)]
)
def natural_language_search(
    payload: schemas.SearchRequest, db: Session = Depends(get_db)
):
    """Örnek: {"q": "depodaki boştaki Dell laptoplar"}"""
    filt, used_ai = ai_search.build_filter(payload.q, db)
    filt.limit = payload.limit
    results = ai_search.apply_filter(db, filt)
    return schemas.SearchResponse(
        query=payload.q,
        interpreted_filter=filt,
        count=len(results),
        results=results,
        used_ai=used_ai,
    )
