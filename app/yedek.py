"""Yedekleme — veritabanı dökümü + yüklenen dosyaların arşivi.

Arayüzden (Ayarlar → Yedekleme) ve komut satırından kullanılır.

Tasarım notları:
- **Parola komut satırına yazılmaz.** `ps` çıktısı tüm kullanıcılara açıktır;
  PostgreSQL için `PGPASSWORD` ortam değişkeni, MySQL/MariaDB için geçici
  `--defaults-extra-file` kullanılır.
- Hata mesajları maskelenir: dış araçların çıktısı bağlantı dizesi içerebilir.
- Dosya adları sunucu üretir ve indirme sırasında yolun yedek klasörünün
  altında kaldığı ayrıca doğrulanır.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import settings

# Dış araç en fazla bu kadar çalışsın (büyük veritabanı + yavaş disk payı)
ZAMAN_ASIMI = 600

DOSYA_DESENI = re.compile(r"^envanter_\d{4}-\d{2}-\d{2}_\d{6}\.(dump|sql|sqlite|tar\.gz)$")


class YedekHatasi(RuntimeError):
    """Yedekleme başarısız oldu (mesajı kullanıcıya gösterilebilir)."""


def yedek_dizini() -> Path:
    d = Path(settings.backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _maskele(metin: str) -> str:
    """Bağlantı dizelerindeki parolayı gizler."""
    return re.sub(r"(://[^:/@\s]+):[^@\s]*@", r"\1:***@", metin or "")


def _calistir(komut: list[str], *, ortam: dict | None = None,
              cikti_dosyasi: Path | None = None) -> None:
    """Dış aracı çalıştırır; hata olursa maskelenmiş mesajla yükseltir."""
    tam_ortam = {**os.environ, **(ortam or {})}
    try:
        if cikti_dosyasi is not None:
            with cikti_dosyasi.open("wb") as f:
                sonuc = subprocess.run(komut, stdout=f, stderr=subprocess.PIPE,
                                       env=tam_ortam, timeout=ZAMAN_ASIMI)
        else:
            sonuc = subprocess.run(komut, capture_output=True, env=tam_ortam,
                                   timeout=ZAMAN_ASIMI)
    except FileNotFoundError as e:
        raise YedekHatasi(f"'{komut[0]}' bulunamadı — sunucuya kurulmalı") from e
    except subprocess.TimeoutExpired as e:
        raise YedekHatasi("Yedekleme zaman aşımına uğradı") from e
    if sonuc.returncode != 0:
        ayrinti = _maskele((sonuc.stderr or b"").decode(errors="replace").strip())
        raise YedekHatasi(f"{komut[0]} başarısız: {ayrinti[:300]}")


def _damga() -> str:
    return f"{dt.datetime.now():%Y-%m-%d_%H%M%S}"


# --------------------------------------------------------------------------- #
# Veritabanı dökümü
# --------------------------------------------------------------------------- #
def _postgres_yedegi(url, hedef: Path) -> None:
    komut = ["pg_dump", "-Fc", "--no-password",
             "-h", url.host or "localhost", "-p", str(url.port or 5432),
             "-U", url.username or "", url.database or ""]
    # Parola komut satırına konmaz; ortam değişkeniyle geçilir.
    ortam = {"PGPASSWORD": url.password or ""}
    _calistir(komut, ortam=ortam, cikti_dosyasi=hedef)


def _mysql_yedegi(url, hedef: Path) -> None:
    arac = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    if not arac:
        raise YedekHatasi("mysqldump/mariadb-dump bulunamadı — "
                          "kur: apt install -y mariadb-client")
    # Parola geçici seçenek dosyasına yazılır (ps çıktısında görünmesin)
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as f:
        f.write(f"[client]\nuser={url.username or ''}\n"
                f"password={url.password or ''}\n"
                f"host={url.host or 'localhost'}\nport={url.port or 3306}\n")
        konf = Path(f.name)
    konf.chmod(0o600)
    try:
        _calistir([arac, f"--defaults-extra-file={konf}", "--single-transaction",
                   "--default-character-set=utf8mb4", url.database or ""],
                  cikti_dosyasi=hedef)
    finally:
        konf.unlink(missing_ok=True)


def _sqlite_yedegi(url, hedef: Path) -> None:
    kaynak = Path(url.database or "")
    if not kaynak.is_absolute():
        kaynak = Path.cwd() / kaynak
    if not kaynak.exists():
        raise YedekHatasi(f"Veritabanı dosyası yok: {kaynak.name}")
    # sqlite3 .backup: uygulama yazarken de tutarlı kopya alır
    with sqlite3.connect(kaynak) as src, sqlite3.connect(hedef) as dst:
        src.backup(dst)


def veritabani_yedegi(hedef_dizin: Path | None = None) -> Path:
    """Veritabanının dökümünü alır ve oluşan dosyanın yolunu döndürür."""
    dizin = hedef_dizin or yedek_dizini()
    url = make_url(settings.database_url)
    surucu = url.get_backend_name()
    damga = _damga()

    if surucu == "postgresql":
        hedef = dizin / f"envanter_{damga}.dump"
        _postgres_yedegi(url, hedef)
    elif surucu == "mysql":
        hedef = dizin / f"envanter_{damga}.sql"
        _mysql_yedegi(url, hedef)
    elif surucu == "sqlite":
        hedef = dizin / f"envanter_{damga}.sqlite"
        _sqlite_yedegi(url, hedef)
    else:
        raise YedekHatasi(f"Desteklenmeyen veritabanı: {surucu}")
    return hedef


# --------------------------------------------------------------------------- #
# Yüklenen dosyalar
# --------------------------------------------------------------------------- #
def dosya_arsivi(hedef_dizin: Path | None = None) -> Path | None:
    """Yükleme klasörünü tar.gz'ler. Klasör boşsa None döner.

    Veritabanı dökümü bu dosyaları içermez — ayrı arşivlenmeleri şart.
    """
    dizin = hedef_dizin or yedek_dizini()
    kaynak = Path(settings.upload_dir)
    if not kaynak.exists() or not any(kaynak.rglob("*")):
        return None
    hedef = dizin / f"dosyalar_{_damga()}.tar.gz"
    with tarfile.open(hedef, "w:gz") as arsiv:
        arsiv.add(kaynak, arcname=kaynak.name)
    return hedef


# --------------------------------------------------------------------------- #
# Listeleme / temizlik
# --------------------------------------------------------------------------- #
def _tur(ad: str) -> str:
    return "dosyalar" if ad.startswith("dosyalar_") else "veritabani"


def yedekleri_listele() -> list[dict]:
    """Yedek klasöründeki dosyalar, yenisi başta."""
    dizin = yedek_dizini()
    kayitlar = []
    for y in dizin.iterdir():
        if not y.is_file() or not y.name.startswith(("envanter_", "dosyalar_")):
            continue
        bilgi = y.stat()
        kayitlar.append({
            "ad": y.name,
            "tur": _tur(y.name),
            "boyut": bilgi.st_size,
            "tarih": dt.datetime.fromtimestamp(bilgi.st_mtime).isoformat(),
        })
    return sorted(kayitlar, key=lambda k: k["tarih"], reverse=True)


def yedek_yolu(ad: str) -> Path:
    """Ad doğrulanır ve yolun yedek klasörünün altında kaldığı güvenceye alınır."""
    if "/" in ad or "\\" in ad or ad.startswith("."):
        raise YedekHatasi("Geçersiz yedek adı")
    kok = yedek_dizini().resolve()
    hedef = (kok / ad).resolve()
    if not hedef.is_relative_to(kok) or not hedef.is_file():
        raise YedekHatasi("Yedek bulunamadı")
    return hedef


def eskileri_sil(saklama_gun: int | None = None) -> int:
    """Belirtilen günden eski yedekleri siler, silinen sayısını döndürür."""
    gun = saklama_gun if saklama_gun is not None else settings.backup_keep_days
    if gun <= 0:
        return 0
    sinir = dt.datetime.now() - dt.timedelta(days=gun)
    silinen = 0
    for y in yedek_dizini().iterdir():
        if not y.is_file() or not y.name.startswith(("envanter_", "dosyalar_")):
            continue
        if dt.datetime.fromtimestamp(y.stat().st_mtime) < sinir:
            y.unlink(missing_ok=True)
            silinen += 1
    return silinen


def yedek_al() -> dict:
    """Veritabanı + dosya yedeğini alır ve özet döndürür."""
    vt = veritabani_yedegi()
    dosyalar = dosya_arsivi()
    silinen = eskileri_sil()
    return {
        "veritabani": vt.name,
        "veritabani_boyut": vt.stat().st_size,
        "dosyalar": dosyalar.name if dosyalar else None,
        "dosyalar_boyut": dosyalar.stat().st_size if dosyalar else 0,
        "silinen_eski": silinen,
    }
