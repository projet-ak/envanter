#!/usr/bin/env python3
"""Kişiye bağlı belgelerin türünü düzeltir (Diğer → İmzalı zimmet formu).

Snipe-IT'ten aktarılan dosyaların adları çoğu zaman `tmp20241020161408.pdf`
gibidir; addan tür anlaşılmadığı için "Diğer" olarak gelirler. Oysa kişiye
bağlı PDF'lerin neredeyse tamamı imzalı zimmet formudur.

Bu betik yalnızca **PDF** ve türü **Diğer** olan kişi eklerini "İmzalı zimmet
formu" yapar. Excel/görsel dosyalara ve elle seçilmiş türlere dokunmaz.

Kullanım:
    ./.venv/bin/python scripts/kisi-belge-turu.py                 # rapor
    ./.venv/bin/python scripts/kisi-belge-turu.py --uygula        # yaz
    ./.venv/bin/python scripts/kisi-belge-turu.py --tumu --uygula # elle
                                                     yüklenenler de dahil

Varsayılan olarak yalnızca aktarımdan gelenler (yükleyen `snipeit-aktarim`)
işlenir; `--tumu` bu sınırı kaldırır.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402

M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'
AKTARIM = "snipeit-aktarim"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uygula", action="store_true",
                    help="değişikliği yaz (varsayılan: yalnızca rapor)")
    ap.add_argument("--tumu", action="store_true",
                    help="yalnızca aktarımdan gelenlerle sınırlı kalma")
    args = ap.parse_args()

    uyar()
    db = SessionLocal()
    try:
        hepsi = db.scalars(select(models.UserFile)).all()
        aday = [d for d in hepsi
                if d.tur == models.DosyaTuru.diger
                and Path(d.dosya_adi).suffix.lower() == ".pdf"
                and (args.tumu or d.yukleyen == AKTARIM)]

        tur_sayilari: dict[str, int] = {}
        for d in hepsi:
            tur_sayilari[d.tur.value] = tur_sayilari.get(d.tur.value, 0) + 1

        print(f"\n{M}Kişi belgeleri{N}")
        print(f"  Toplam            : {len(hepsi)}")
        for tur, n in sorted(tur_sayilari.items(), key=lambda x: -x[1]):
            print(f"    {tur:<16} {n:>4}")
        print(f"  {Y}Zimmet formu yapılacak: {len(aday)}{N}"
              f"  (PDF + 'Diğer'"
              f"{'' if args.tumu else ' + aktarımdan gelen'})")

        if not aday:
            print(f"\n{Y}✓ Düzeltilecek belge yok.{N}")
            if not args.tumu:
                print("  Elle yüklenenleri de kapsamak için: --tumu")
            return 0

        kisiler = {k.id: k.full_name for k in db.scalars(select(models.User)).all()}
        for d in aday[:15]:
            print(f"    {str(kisiler.get(d.user_id))[:26]:<26} {d.dosya_adi[:44]}")
        if len(aday) > 15:
            print(f"    … ve {len(aday) - 15} belge daha")

        # Dokunulmayanları da göster: yanlışlıkla bir şeyi kaçırmıyor muyuz?
        atlanan = [d for d in hepsi
                   if d.tur == models.DosyaTuru.diger and d not in aday]
        if atlanan:
            print(f"\n{M}Dokunulmayan 'Diğer' belgeler: {len(atlanan)}{N}")
            for d in atlanan[:8]:
                sebep = ("PDF değil" if Path(d.dosya_adi).suffix.lower() != ".pdf"
                         else "aktarımdan gelmemiş")
                print(f"    {d.dosya_adi[:40]:<40} ({sebep})")
            if len(atlanan) > 8:
                print(f"    … ve {len(atlanan) - 8} belge daha")

        if not args.uygula:
            print(f"\n{M}Rapor modundasınız — hiçbir şey değişmedi.{N}")
            print("  Yazmak için: --uygula")
            return 0

        for d in aday:
            d.tur = models.DosyaTuru.zimmet_formu
        db.commit()
        print(f"\n{Y}✓ {len(aday)} belge 'İmzalı zimmet formu' olarak "
              f"işaretlendi.{N}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
