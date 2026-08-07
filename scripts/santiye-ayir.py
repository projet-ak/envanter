#!/usr/bin/env python3
"""Tek bir genel lokasyondaki cihazları proje koduna göre şantiyelere ayırır.

Eski içe aktarımla gelmiş veriyi düzeltmek içindir; yeni Excel aktarımları
şantiyeleri zaten ayrı ayrı oluşturur. Tekrar çalıştırılabilir: taşınacak
cihaz kalmadığında hiçbir şeyi değiştirmez.

Kullanım:
    # Önce ne olacağını gör (hiçbir şey değişmez):
    ./.venv/bin/python scripts/santiye-ayir.py --dry-run

    # Uygula:
    ./.venv/bin/python scripts/santiye-ayir.py

Seçenekler:
    --dry-run       Yazmadan raporla
    --kaynak "ad"   Yalnızca bu lokasyondakileri ayır (varsayılan: hepsi)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import santiye  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Şantiyeleri proje koduna göre ayır")
    ap.add_argument("--dry-run", action="store_true", help="Yazmadan raporla")
    ap.add_argument("--kaynak", help="Yalnızca bu lokasyon adındakileri ayır")
    args = ap.parse_args()

    uyar()
    db = SessionLocal()
    try:
        rapor = santiye.ayir(db, kaynak=args.kaynak, uygula=not args.dry_run)

        print(f"\n\033[1;36m→ Toplam cihaz: {rapor['toplam']}\033[0m")
        print(f"  Taşınacak      : {rapor['tasinan']}")
        print(f"  Proje kodu yok : {rapor['kodsuz']} (dokunulmayacak)")
        if rapor["plan"]:
            print("\n\033[1mPlanlanan taşımalar\033[0m")
            for tanim, adet in sorted(rapor["plan"].items(),
                                      key=lambda x: -x[1]):
                print(f"  {adet:>5}  {tanim}")

        if not rapor["tasinan"]:
            print("\n\033[32m✓ Ayrılacak cihaz yok, her şey zaten yerinde.\033[0m")
            return 0

        if args.dry_run:
            print("\n\033[33m⚠ KURU ÇALIŞTIRMA — hiçbir değişiklik yapılmadı.\033[0m")
            print("  Uygulamak için --dry-run olmadan çalıştır.")
            return 0

        print(f"\n\033[1;32m✓ {rapor['tasinan']} cihaz taşındı, "
              f"{rapor['olusan']} yeni şantiye lokasyonu oluşturuldu.\033[0m")
        if rapor["temizlenen"]:
            print(f"  {rapor['temizlenen']} boş lokasyonun eski proje kodu "
                  "temizlendi.")

        print("\n\033[1mŞantiyeler\033[0m")
        for ad, kod, sayi in santiye.santiye_ozeti(db):
            print(f"  {ad:<28} kod: {kod or '—':<8} {sayi} cihaz")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
