#!/usr/bin/env python3
"""Markası boş modelleri bulur, istenirse addan çıkararak doldurur.

Marka cihaz kaydında değil **modelde** durur (Asset -> AssetModel ->
Manufacturer). Model kaydı markasız açıldıysa cihaz detayında "Marka" satırı
boş görünür — 410 cihazın hepsinde olduğu gibi.

Kullanım:
    ./.venv/bin/python scripts/marka-kontrol.py             # yalnızca rapor
    ./.venv/bin/python scripts/marka-kontrol.py --uygula    # tahminleri yaz

Tahmin nasıl yapılır: model ya da cihaz adının **başında** bilinen bir marka
geçiyorsa ("HP ProBook 450", "LENOVO V15") o marka bağlanır. Bilinen markalar
= veritabanındaki Üretici kayıtları + aşağıdaki yaygın liste. Ortada/sonda
geçen adlar sayılmaz ("Dell Dock" markadır ama "Kablo Dell'e uygun" değildir),
emin olunamayan kayıtlar elle düzeltilmek üzere listelenir.

Toplu ve kesin çözüm: Excel'i yeniden içe aktarmak. İçe aktarım artık eksik
marka/kategoriyi mevcut model kaydına işler (yalnızca boş alanları doldurur).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402

# Veritabanında üretici kaydı hiç yoksa da tanınsın diye yaygın markalar
YAYGIN = [
    "HP", "Hewlett Packard", "Dell", "Lenovo", "Asus", "Acer", "Apple",
    "Casper", "Monster", "MSI", "Toshiba", "Samsung", "LG", "Philips",
    "Huawei", "Xiaomi", "Cisco", "TP-Link", "Mikrotik", "Ubiquiti",
    "Hikvision", "Dahua", "Canon", "Epson", "Brother", "Xerox", "Zebra",
    "Kyocera", "Ricoh", "Lexmark", "Logitech", "Microsoft", "Sony",
    "Intel", "AMD", "Seagate", "Western Digital", "Kingston", "Corsair",
    "APC", "Eaton", "Tuncmatik", "Paradox", "Jablotron", "Bosch",
    "Mavigard", "Fortinet", "Sophos", "Baykon", "Evolis", "ZKTeco", "CAME",
]


def _markalar(db) -> list[tuple[str, models.Manufacturer | None, str]]:
    """(sade ad, kayıt, görünen ad) — uzun adlar önce eşleşsin diye sıralı."""
    liste: list[tuple[str, models.Manufacturer | None, str]] = []
    görülen = set()
    for m in db.scalars(select(models.Manufacturer)).all():
        if m.name:
            sade = _sadelestir(m.name)
            liste.append((sade, m, m.name))
            görülen.add(sade)
    for ad in YAYGIN:
        sade = _sadelestir(ad)
        if sade not in görülen:
            liste.append((sade, None, ad))
            görülen.add(sade)
    # "hewlett packard" > "hp": önce uzun adı dene
    return sorted(liste, key=lambda x: -len(x[0]))


def _tahmin(metinler: list[str], markalar) -> tuple[str, models.Manufacturer | None,
                                                    str] | None:
    """Adın BAŞINDA marka geçiyorsa döner; ortada geçen ad sayılmaz."""
    for metin in metinler:
        sade = _sadelestir(metin or "")
        if not sade:
            continue
        for anahtar, kayit, gorunen in markalar:
            if sade == anahtar or sade.startswith(anahtar + " "):
                return anahtar, kayit, gorunen
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uygula", action="store_true",
                    help="tahminleri veritabanına yaz (varsayılan: yalnızca rapor)")
    args = ap.parse_args()

    uyar()
    db = SessionLocal()
    M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'
    try:
        cihaz_sayilari = dict(db.execute(
            select(models.AssetModel.id, func.count(models.Asset.id))
            .select_from(models.AssetModel)
            .join(models.Asset, models.Asset.model_id == models.AssetModel.id)
            .group_by(models.AssetModel.id)
        ).all())

        modeller = db.scalars(select(models.AssetModel)
                              .order_by(models.AssetModel.name)).all()
        markasiz = [m for m in modeller if m.manufacturer_id is None]
        markali = len(modeller) - len(markasiz)
        etkilenen = sum(cihaz_sayilari.get(m.id, 0) for m in markasiz)

        print(f"\n{M}Model kayıtları{N}")
        print(f"  Toplam model      : {len(modeller)}")
        print(f"  Markası olan      : {markali}")
        print(f"  {S}Markası boş       : {len(markasiz)}"
              f"  →  {etkilenen} cihazda marka görünmüyor{N}")
        print(f"  Üretici kaydı     : "
              f"{db.scalar(select(func.count(models.Manufacturer.id)))}")

        if not markasiz:
            print(f"\n{Y}✓ Markası boş model yok.{N}")
            return 0

        # Modeli kullanan bir cihazın adı da ipucu olabilir ("HP N439")
        ornek_ad: dict[int, str] = {}
        for mid, ad in db.execute(
                select(models.Asset.model_id, models.Asset.name)
                .where(models.Asset.model_id.is_not(None),
                       models.Asset.name.is_not(None))).all():
            ornek_ad.setdefault(mid, ad)

        markalar = _markalar(db)
        bulunan, bulunamayan = [], []
        for m in markasiz:
            t = _tahmin([m.name, ornek_ad.get(m.id, "")], markalar)
            (bulunan if t else bulunamayan).append((m, t))

        if bulunan:
            print(f"\n{M}Addan çıkarılabilen marka{N}")
            for m, (_, kayit, gorunen) in bulunan:
                adet = cihaz_sayilari.get(m.id, 0)
                yeni = "" if kayit else f" {S}(üretici kaydı açılacak){N}"
                print(f"  {Y}→{N} {m.name:<38} {adet:>4} cihaz  ⇒  {gorunen}{yeni}")

        if bulunamayan:
            print(f"\n{S}Marka çıkarılamadı — elle düzeltilmeli{N}")
            sirali = sorted(bulunamayan,
                            key=lambda x: -cihaz_sayilari.get(x[0].id, 0))
            for m, _ in sirali[:40]:
                print(f"  ? {m.name:<38} {cihaz_sayilari.get(m.id, 0):>4} cihaz")
            if len(sirali) > 40:
                print(f"    … ve {len(sirali) - 40} model daha")
            print("\n  Bunları Tanımlar → Modeller ekranından tek tek "
                  "seçebilirsiniz;")
            print("  ya da Excel'i yeniden içe aktarın (marka sütunu doldurur).")

        if not args.uygula:
            print(f"\n{M}Rapor modundasınız — hiçbir şey değişmedi.{N}")
            print("  Yazmak için: ./.venv/bin/python scripts/marka-kontrol.py "
                  "--uygula")
            return 0

        yeni_uretici = 0
        for m, (_, kayit, gorunen) in bulunan:
            if kayit is None:
                kayit = models.Manufacturer(name=gorunen)
                db.add(kayit)
                db.flush()
                yeni_uretici += 1
                # aynı marka ikinci kez açılmasın
                markalar = _markalar(db)
            m.manufacturer_id = kayit.id
        db.commit()
        print(f"\n{Y}✓ {len(bulunan)} model markalandı"
              f" ({yeni_uretici} yeni üretici kaydı).{N}")
        print(f"  Kalan: {len(bulunamayan)} model hâlâ markasız.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
