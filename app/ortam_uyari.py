"""Kabukta export edilmiş ayarların .env'i ezmesine karşı uyarı.

`set -a; . ./.env; set +a` gibi bir komut çalıştırıldıysa ayarlar kabuğa
export edilir. pydantic-settings ortam değişkenlerine .env dosyasından
öncelik verdiği için, .env sonradan değişse bile ESKİ değer kullanılır ve
"password authentication failed" gibi kafa karıştırıcı hatalar çıkar.

Bu modül böyle bir durumu tespit edip anlaşılır bir uyarı basar.
"""

from __future__ import annotations

import os
from pathlib import Path

# Yanlış eşleşmesi en çok soruna yol açan ayarlar
ONEMLI = ("DATABASE_URL", "SECRET_KEY", "SNIPEIT_URL", "SNIPEIT_TOKEN")


def _env_dosyasini_oku(yol: Path) -> dict[str, str]:
    degerler: dict[str, str] = {}
    try:
        for satir in yol.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            anahtar, _, deger = satir.partition("=")
            anahtar = anahtar.strip()
            if anahtar.isidentifier():
                degerler[anahtar] = deger.strip().strip('"').strip("'")
    except OSError:
        pass
    return degerler


def catisma_kontrolu(env_yolu: str = ".env") -> list[str]:
    """Kabuktaki değeri .env'dekinden FARKLI olan ayarları döndürür."""
    yol = Path(env_yolu)
    if not yol.is_file():
        return []
    dosya = _env_dosyasini_oku(yol)
    return [
        anahtar for anahtar in ONEMLI
        if anahtar in os.environ
        and anahtar in dosya
        and os.environ[anahtar] != dosya[anahtar]
    ]


def uyar(env_yolu: str = ".env") -> None:
    """Çakışma varsa kullanıcıya ne yapması gerektiğini söyler."""
    catisan = catisma_kontrolu(env_yolu)
    if not catisan:
        return

    print("\033[1;33m" + "─" * 68)
    print("⚠  DİKKAT: Kabuğunuzdaki ortam değişkenleri .env dosyasını EZİYOR")
    print("─" * 68 + "\033[0m")
    print("Şu ayarlar kabukta farklı bir değerle tanımlı:")
    for anahtar in catisan:
        print(f"    • {anahtar}")
    print()
    print("Muhtemelen daha önce şuna benzer bir komut çalıştırdınız:")
    print("    set -a; . ./.env; set +a")
    print()
    print("\033[1mÇÖZÜM\033[0m — bu değişkenleri kaldırın, sonra tekrar deneyin:")
    print(f"    unset {' '.join(catisan)}")
    print("\nveya yeni bir kabuk açın (çıkış yapıp tekrar bağlanın).")
    print("\033[1;33m" + "─" * 68 + "\033[0m\n")
