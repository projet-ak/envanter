"""Yedekleme uçları — yalnızca yönetici.

Yedek dosyaları veritabanının tamamını içerir; bu yüzden hem listeleme hem
indirme yönetici yetkisi ister.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app import yedek
from app.auth import require_admin
from app.config import settings

router = APIRouter(prefix="/yedek", tags=["Yedekleme"],
                   dependencies=[Depends(require_admin)])


@router.get("")
def durum():
    """Yedek listesi ve ayarlar."""
    return {
        "klasor": str(yedek.yedek_dizini()),
        "saklama_gun": settings.backup_keep_days,
        "yedekler": yedek.yedekleri_listele(),
    }


@router.post("", status_code=201)
def yedek_al():
    """Şimdi yedek alır: veritabanı dökümü + yüklenen dosyalar arşivi."""
    try:
        return yedek.yedek_al()
    except yedek.YedekHatasi as e:
        raise HTTPException(500, str(e)) from e


@router.get("/{ad}")
def indir(ad: str):
    try:
        yol = yedek.yedek_yolu(ad)
    except yedek.YedekHatasi as e:
        raise HTTPException(404, str(e)) from e
    return FileResponse(yol, media_type="application/octet-stream",
                        filename=yol.name)


@router.delete("/{ad}", status_code=204)
def sil(ad: str):
    try:
        yedek.yedek_yolu(ad).unlink()
    except yedek.YedekHatasi as e:
        raise HTTPException(404, str(e)) from e
