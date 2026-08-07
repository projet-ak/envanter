#!/usr/bin/env python3
"""Hangi kategoriler ağ ürünü sayılıyor, hangileri kaçıyor?

Ağ Ürünleri ekranı, kategori adından tür çıkarır (bkz. app/ag.py: tur_bul).
Bu script tüm kategorileri cihaz sayılarıyla listeler ve hangisinin hangi ağ
türüne eşlendiğini gösterir — eşleşmeyenler ayrı başlık altında toplanır.

Kullanım:
    ./.venv/bin/python scripts/ag-kategori-kontrol.py

Eşleşmeyen bir kategoriyi ağ ürünü yapmanın iki yolu var:
  1) Kategoriyi Tanımlar ekranından yeniden adlandır ("Switch" geçsin), ya da
  2) app/ag.py içindeki _KATEGORI_IPUCU listesine anahtar kelimeyi ekle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app import ag, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402

# Ağ donanımı olma ihtimali yüksek ama eşleşmemiş kategorileri işaretle
SUPHELI = ("switch", "swich", "swtich", "ap", "access", "wifi", "wi-fi", "kablosuz",
           "router", "modem", "firewall", "sfp", "fiber", "optik", "transceiver",
           "gbic", "patch", "kabinet", "kabin", "rack", "utp", "kablo", "hub",
           "nvr", "poe", "media", "converter", "omurga", "ethernet", "network", "ağ")


def main() -> int:
    uyar()
    db = SessionLocal()
    try:
        # Kategori -> cihaz sayısı (model üzerinden)
        sayilar = dict(db.execute(
            select(models.AssetModel.category_id, func.count(models.Asset.id))
            .select_from(models.AssetModel)
            .join(models.Asset, models.Asset.model_id == models.AssetModel.id)
            .group_by(models.AssetModel.category_id)
        ).all())

        kategoriler = db.scalars(
            select(models.Category).order_by(models.Category.name)).all()

        eslesen, kacan = [], []
        for k in kategoriler:
            adet = sayilar.get(k.id, 0)
            tur = ag.tur_bul(k.name)
            (eslesen if tur else kacan).append((k.name, adet, tur))

        M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'

        print(f"\n{M}Ağ ürünü sayılan kategoriler{N}")
        if eslesen:
            for ad, adet, tur in sorted(eslesen, key=lambda x: -x[1]):
                print(f"  {Y}✓{N} {ad:<42} {adet:>4} cihaz  →  {ag.TURLER[tur]['ad']}")
            print(f"\n  Toplam: {sum(a for _, a, _ in eslesen)} cihaz")
        else:
            print("  (yok)")

        # Eşleşmeyenler: önce şüpheliler, cihaz sayısına göre
        supheli = [(a, n) for a, n, _ in kacan
                   if any(s in (a or "").lower() for s in SUPHELI)]
        digerleri = [(a, n) for a, n, _ in kacan
                     if not any(s in (a or "").lower() for s in SUPHELI)]

        if supheli:
            print(f"\n{S}Ağ ürünü OLABİLİR ama eşleşmedi{N}")
            for ad, adet in sorted(supheli, key=lambda x: -x[1]):
                print(f"  ! {ad:<42} {adet:>4} cihaz")
            print("\n  Bunları Ağ Ürünleri ekranına almak için kategoriyi yeniden")
            print("  adlandırın ya da app/ag.py içindeki _KATEGORI_IPUCU'na ekleyin.")

        if digerleri:
            print(f"\n{M}Ağ dışı kategoriler{N}")
            for ad, adet in sorted(digerleri, key=lambda x: -x[1])[:30]:
                print(f"    {ad:<42} {adet:>4} cihaz")
            if len(digerleri) > 30:
                print(f"    … ve {len(digerleri) - 30} kategori daha")

        # Kategorisiz cihazlar da gözden kaçmasın
        kategorisiz = db.scalar(select(func.count(models.Asset.id)).where(
            models.Asset.model_id.is_(None)))
        if kategorisiz:
            print(f"\n{S}Modeli/kategorisi olmayan cihaz: {kategorisiz}{N}")
            print("  Bunlar hiçbir tür filtresine girmez.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
