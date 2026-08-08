"""Dosya deposu: ek yükleme/indirme/silmenin ortak makinesi.

Üç sahip türü aynı kuralları paylaşır — cihaz (`asset_files`), kişi
(`user_files`) ve stok kaydı (`stock_files`). Doğrulama, yol üretimi, disk
yazımı ve indirme başlıkları burada tek yerdedir; router'lar yalnızca sahibi
bulur ve kaydı hangi tabloya yazacağını söyler.

Klasör düzeni türe ve aya göre ayrılır:

    yuklemeler/
      gorseller/2026/08/12-a1b2c3d4e5f6a7b8.png     cihaz eki
      belgeler/2026/08/k42-9f8e7d6c5b4a3210.pdf     kişi eki (ön ek "k")
      faturalar/2026/08/a7-...                       aksesuar eki (ön ek "a")

Neden tarih klasörü: tek klasörde on binlerce dosya biriktiğinde listeleme ve
yedekleme yavaşlar; ay bazlı bölme bunu önler. Dosya adları kullanıcıdan
gelmez — sunucu üretir — böylece yol geçişi (``../``) ve ad çakışması mümkün
olmaz. Okumada da yolun kök klasörün altında kaldığı ayrıca doğrulanır.
"""

from __future__ import annotations

import datetime as dt
import mimetypes
import secrets
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import models
from app.config import settings

# Kabul edilen türler. Yürütülebilir/betik içerik alınmaz.
IZINLI_UZANTILAR = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic",   # görseller
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",    # belgeler
}
GORSEL_UZANTILAR = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic"}

# Tür -> klasör adı
KLASORLER = {
    models.DosyaTuru.gorsel: "gorseller",
    models.DosyaTuru.zimmet_formu: "belgeler",
    models.DosyaTuru.fatura: "faturalar",
    models.DosyaTuru.diger: "belgeler",
}


def yukleme_dizini() -> Path:
    d = Path(settings.upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _uzanti(ad: str) -> str:
    return Path(ad).suffix.lower()


def _guvenli_ad(ad: str) -> str:
    """Görüntülenecek dosya adını zararsız hâle getirir (yol bileşeni değil)."""
    ad = Path(ad).name                       # dizin kısmını at
    ad = unicodedata.normalize("NFC", ad)
    return ad[:200] or "dosya"


def yeni_yol(sahip_id: int, tur: models.DosyaTuru, uzanti: str,
             on_ek: str = "") -> str:
    """Yeni dosya için göreli yol üretir: <klasör>/<yıl>/<ay>/<id>-<rastgele><uz>.

    `on_ek` sahibi ayırt eder: cihazda boş, kişide "k", stokta kayıt türünün
    baş harfi — aynı klasörde dosyalar karışmaz, ada bakınca sahibi bellidir.
    """
    bugun = dt.date.today()
    return (f"{KLASORLER.get(tur, 'belgeler')}/{bugun:%Y/%m}/"
            f"{on_ek}{sahip_id}-{secrets.token_hex(8)}{uzanti}")


def tam_yol(goreli: str) -> Path:
    """Göreli yolu diskteki tam yola çevirir ve kök klasörün altında tutar.

    Veritabanındaki değer bozulsa ya da elle değiştirilse bile yükleme
    klasörünün dışına çıkılamaz.
    """
    kok = yukleme_dizini().resolve()
    hedef = (kok / goreli).resolve()
    if not hedef.is_relative_to(kok):
        raise HTTPException(400, "Geçersiz dosya yolu")
    return hedef


def dogrula(ad: str, tur: models.DosyaTuru) -> str:
    """Uzantıyı denetler; döndürdüğü değer küçük harfli uzantıdır."""
    uzanti = _uzanti(ad)
    if uzanti not in IZINLI_UZANTILAR:
        raise HTTPException(
            415, f"'{uzanti or 'uzantısız'}' dosya türü kabul edilmiyor. "
                 f"İzinliler: {', '.join(sorted(IZINLI_UZANTILAR))}")
    if tur == models.DosyaTuru.gorsel and uzanti not in GORSEL_UZANTILAR:
        raise HTTPException(415, "Görsel için bir resim dosyası seçin")
    return uzanti


def boyut_denetle(icerik: bytes) -> None:
    sinir = settings.max_upload_mb * 1024 * 1024
    if len(icerik) > sinir:
        raise HTTPException(
            413, f"Dosya çok büyük ({len(icerik) // 1024 // 1024} MB). "
                 f"Sınır: {settings.max_upload_mb} MB")
    if not icerik:
        raise HTTPException(400, "Dosya boş")


async def diske_yaz(file: UploadFile, tur: models.DosyaTuru, sahip_id: int,
                    on_ek: str = "") -> dict:
    """Dosyayı doğrulayıp diske yazar; kayıt alanlarını sözlük olarak döner.

    Router yalnızca sahibi doğrular ve dönen sözlüğü kendi tablosunun
    kaydına açar: `models.AssetFile(asset_id=..., **alanlar)` gibi.
    """
    ad = _guvenli_ad(file.filename or "dosya")
    uzanti = dogrula(ad, tur)
    icerik = await file.read()
    boyut_denetle(icerik)

    goreli = yeni_yol(sahip_id, tur, uzanti, on_ek=on_ek)
    hedef = tam_yol(goreli)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(icerik)
    return {
        "tur": tur,
        "dosya_adi": ad,
        "yol": goreli,
        "content_type": file.content_type or mimetypes.guess_type(ad)[0],
        "boyut": len(icerik),
    }


def indir(kayit) -> FileResponse:
    """Kaydın dosyasını sunar: görseller tarayıcıda açılır, diğerleri iner."""
    yol = tam_yol(kayit.yol)
    if not yol.exists():
        raise HTTPException(404, "Dosya diskte bulunamadı")
    icerde = _uzanti(kayit.dosya_adi) in GORSEL_UZANTILAR
    return FileResponse(
        yol,
        media_type=kayit.content_type or "application/octet-stream",
        headers={"Content-Disposition":
                 f"{'inline' if icerde else 'attachment'}; "
                 f"filename*=UTF-8''{quote(kayit.dosya_adi)}"},
    )


def diskten_sil(kayit) -> None:
    tam_yol(kayit.yol).unlink(missing_ok=True)
