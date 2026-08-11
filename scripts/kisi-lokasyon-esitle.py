#!/usr/bin/env python3
"""Kişi lokasyonlarını zimmetli cihazlarının lokasyonuna eşitler.

Cihazlar toplu taşınırken kişiler eski lokasyonda kalabiliyor; kişi bir
yerde, zimmetindeki cihazlar başka yerde görünüyor ve raporları yanıltıyor.
Bu betik her personelin zimmetindeki cihazların lokasyonlarına bakar:

- Cihazların TAMAMI (ya da çoğunluğu) tek lokasyondaysa ve kişi başka
  yerdeyse, kişinin lokasyonunu oraya çekmeyi önerir.
- Cihazlar birden çok lokasyona eşit dağılmışsa karar insana bırakılır —
  bu kayıtlar "elle bakılmalı" başlığında listelenir, hiçbir şey yazılmaz.
- Zimmeti olmayan kişilere dokunulmaz.

Arayüz tarafında da aynı bağ korunur: toplu taşıma penceresindeki
"Zimmetli kişileri de taşı" kutusu işaretliyken kişiler cihazlarıyla
birlikte gider — betik geçmişten kalan uyumsuzluk içindir.

Kullanım:
    ./.venv/bin/python scripts/kisi-lokasyon-esitle.py             # rapor
    ./.venv/bin/python scripts/kisi-lokasyon-esitle.py --uygula    # yaz
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402

M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'


def oneriler(db: Session) -> tuple[list[dict], list[dict]]:
    """(eşitlenecekler, elle bakılacaklar).

    Eşitlenecek: zimmetli cihazlarının açık ara en çok bulunduğu lokasyon
    kişininkinden farklı. Elle bakılacak: iki lokasyon başa baş.
    """
    lokasyon_adi = dict(db.execute(
        select(models.Location.id, models.Location.name)).all())

    kisi_cihazlari: dict[int, list[int]] = {}
    for uid, lok in db.execute(
            select(models.Asset.assigned_user_id, models.Asset.location_id)
            .where(models.Asset.assigned_user_id.is_not(None),
                   models.Asset.location_id.is_not(None))).all():
        kisi_cihazlari.setdefault(uid, []).append(lok)

    esitlenecek, elle = [], []
    for kisi in db.scalars(select(models.User)
                           .order_by(models.User.first_name)).all():
        lokasyonlar = kisi_cihazlari.get(kisi.id)
        if not lokasyonlar:
            continue
        sayim = Counter(lokasyonlar).most_common()
        hedef, adet = sayim[0]
        kayit = {
            "kisi": kisi,
            "ad": " ".join(filter(None, [kisi.first_name, kisi.last_name])),
            "mevcut": lokasyon_adi.get(kisi.location_id, "—"),
            "hedef_id": hedef,
            "hedef": lokasyon_adi.get(hedef, f"#{hedef}"),
            "dagilim": ", ".join(
                f"{lokasyon_adi.get(k, k)}: {n}" for k, n in sayim),
        }
        if len(sayim) > 1 and sayim[1][1] == adet:
            if kisi.location_id not in dict(sayim):
                elle.append(kayit)        # başa baş ve kişi ikisinde de değil
            continue                      # kişi zaten adaylardan birindeyse geç
        if kisi.location_id != hedef:
            esitlenecek.append(kayit)
    return esitlenecek, elle


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uygula", action="store_true",
                    help="önerileri yaz (varsayılan: yalnızca rapor)")
    args = ap.parse_args()

    from app.database import SessionLocal  # noqa: E402
    from app.ortam_uyari import uyar  # noqa: E402

    uyar()
    db = SessionLocal()
    try:
        esitlenecek, elle = oneriler(db)

        if esitlenecek:
            print(f"\n{M}Cihazlarıyla farklı lokasyonda görünen "
                  f"{len(esitlenecek)} kişi{N}")
            for o in esitlenecek:
                print(f"  {Y}→{N} {o['ad']:<28} {o['mevcut']:<26} "
                      f"⇒  {o['hedef']}")
                print(f"      cihazları: {o['dagilim']}")
        else:
            print(f"\n{Y}✓ Kişi lokasyonları cihazlarıyla uyumlu.{N}")

        if elle:
            print(f"\n{S}Elle bakılmalı — cihazları birden çok lokasyona "
                  f"eşit dağılmış{N}")
            for o in elle:
                print(f"  ? {o['ad']:<28} şu an: {o['mevcut']}")
                print(f"      cihazları: {o['dagilim']}")

        if not args.uygula:
            if esitlenecek:
                print(f"\n{M}Rapor modundasınız — hiçbir şey değişmedi.{N}")
                print("  Yazmak için: ./.venv/bin/python "
                      "scripts/kisi-lokasyon-esitle.py --uygula")
            return 0

        for o in esitlenecek:
            o["kisi"].location_id = o["hedef_id"]
        db.commit()
        print(f"\n{Y}✓ {len(esitlenecek)} kişinin lokasyonu cihazlarına "
              f"eşitlendi.{N}")
        if elle:
            print(f"  {len(elle)} kişi elle bakılmak üzere bırakıldı.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
