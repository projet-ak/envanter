#!/usr/bin/env python3
"""Ağ ürünlerini metin tablosundan içe aktarır.

Elinizdeki liste sekme/çok boşlukla ayrılmış sütunlardan oluşuyorsa doğrudan
verebilirsiniz. SFP/modül listesi için beklenen sütunlar:

    Marka   Model/Parça No   Seri Numarası   Hız / Mesafe / Mod

Örnek:
    HIKVISION  HK-SFP-1.25G-1310-DF-MM  30004735548  1.25G / 1310nm / Multi-Mode

Kullanım:
    # Önce ne olacağını gör (hiçbir şey yazılmaz):
    ./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur sfp --dry-run

    # Uygula, lokasyona yerleştir ve transferi kaydet:
    ./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur sfp \
        --lokasyon "ŞANTİYE U030-U031" --nereden "ŞANTİYE U025"

Seçenekler:
    --tur         sfp | switch | access_point | router | kabinet | diger
    --lokasyon    Ürünlerin konulacağı lokasyon adı (yoksa oluşturulur)
    --nereden     Geldiği lokasyon (yalnızca geçmişe transfer notu düşer)
    --dry-run     Yazmadan raporla
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import ag, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402


def satirlari_coz(metin: str) -> list[list[str]]:
    """Sekme ya da 2+ boşlukla ayrılmış sütunları çıkarır; boş satırları atar."""
    satirlar = []
    for ham in metin.splitlines():
        ham = ham.strip()
        if not ham:
            continue
        parcalar = [p.strip() for p in re.split(r"\t+| {2,}", ham) if p.strip()]
        if len(parcalar) >= 2:
            satirlar.append(parcalar)
    return satirlar


def _basliksa(parcalar: list[str]) -> bool:
    sade = _sadelestir(" ".join(parcalar))
    return "marka" in sade and ("model" in sade or "seri" in sade)


def sfp_ozellikleri(tanim: str) -> dict[str, str]:
    """'1.25G / 1310nm / Multi-Mode' → {Hız, Dalga Boyu, Mesafe, Mod}."""
    ozel: dict[str, str] = {}
    for parca in [p.strip() for p in tanim.split("/") if p.strip()]:
        sade = parca.lower()
        if re.fullmatch(r"[\d.]+\s*g( fc)?", sade):
            ozel["Hız"] = parca
        elif sade.endswith("nm"):
            ozel["Dalga Boyu"] = parca
        elif re.fullmatch(r"[\d.]+\s*(m|km)", sade):
            ozel["Mesafe"] = parca
        elif "mode" in sade or "mod" in sade:
            ozel["Mod"] = parca
        else:
            ozel.setdefault("Açıklama", parca)
    return ozel


def main() -> int:
    ap = argparse.ArgumentParser(description="Ağ ürünlerini listeden içe aktar")
    ap.add_argument("dosya", help="Sütunlu metin dosyası ('-' ile stdin)")
    ap.add_argument("--tur", default="sfp", choices=sorted(ag.TURLER))
    ap.add_argument("--lokasyon", help="Ürünlerin konulacağı lokasyon adı")
    ap.add_argument("--nereden", help="Geldiği lokasyon (geçmişe not düşülür)")
    ap.add_argument("--dry-run", action="store_true", help="Yazmadan raporla")
    args = ap.parse_args()

    metin = sys.stdin.read() if args.dosya == "-" else Path(args.dosya).read_text()
    satirlar = [s for s in satirlari_coz(metin) if not _basliksa(s)]
    if not satirlar:
        print("✗ Okunabilir satır yok.", file=sys.stderr)
        return 1

    uyar()
    db = SessionLocal()
    try:
        from app.routers.ag_urunleri import _model_bul, _referans

        lokasyon = None
        if args.lokasyon:
            lokasyon = _referans(db, models.Location, args.lokasyon)

        # Kaynak lokasyon kayıtlıysa kimliğini kullan; değilse adı olduğu gibi
        # yazılır (transfer görünümü ikisini de çözebiliyor). Var olmayan bir
        # lokasyonu burada OLUŞTURMUYORUZ — hayalet kayıt açmasın.
        kaynak_deger = None
        if args.nereden:
            aranan = _sadelestir(args.nereden)
            eslesen = next((loc for loc in db.scalars(select(models.Location)).all()
                            if loc.name and _sadelestir(loc.name) == aranan), None)
            kaynak_deger = str(eslesen.id) if eslesen else args.nereden

        mevcut_seriler = {s for s in db.scalars(select(models.Asset.serial)).all() if s}
        mevcut_etiket = {e for e in db.scalars(select(models.Asset.asset_tag)).all()}

        eklenecek, atlanan = [], []
        for parcalar in satirlar:
            marka = parcalar[0]
            model = parcalar[1] if len(parcalar) > 1 else ""
            seri = parcalar[2] if len(parcalar) > 2 else ""
            tanim = parcalar[3] if len(parcalar) > 3 else ""

            etiket = seri or f"{marka}-{model}"
            if seri and seri in mevcut_seriler:
                atlanan.append((etiket, "seri no zaten kayıtlı"))
                continue
            if etiket in mevcut_etiket:
                atlanan.append((etiket, "etiket zaten kullanımda"))
                continue

            ozel = sfp_ozellikleri(tanim) if args.tur == "sfp" else (
                {"Açıklama": tanim} if tanim else {})
            if model:
                ozel["Parça No"] = model
            eklenecek.append((etiket, marka, model, seri, ozel))
            mevcut_etiket.add(etiket)

        print(f"\n\033[1;36m→ {len(satirlar)} satır okundu\033[0m")
        print(f"  Eklenecek : {len(eklenecek)}")
        print(f"  Atlanacak : {len(atlanan)}")
        print(f"  Tür       : {ag.TURLER[args.tur]['ad']}")
        if lokasyon is not None:
            print(f"  Lokasyon  : {lokasyon.name}")
        print()
        for etiket, marka, model, seri, ozel in eklenecek[:50]:
            ek = ", ".join(f"{k}={v}" for k, v in ozel.items() if k != "Parça No")
            print(f"  + {etiket:<18} {marka:<12} {model:<28} {ek}")
        for etiket, sebep in atlanan[:20]:
            print(f"  - {etiket:<18} ({sebep})")

        if args.dry_run:
            print("\n\033[33m⚠ KURU ÇALIŞTIRMA — hiçbir değişiklik yapılmadı.\033[0m")
            db.rollback()
            return 0
        if not eklenecek:
            print("\n\033[32m✓ Eklenecek yeni ürün yok.\033[0m")
            return 0

        for etiket, marka, model, seri, ozel in eklenecek:
            mdl = _model_bul(db, args.tur, marka, model)
            varlik = models.Asset(
                asset_tag=etiket,
                name=" ".join(filter(None, [marka, model])) or None,
                serial=seri or None,
                model_id=mdl.id,
                location_id=lokasyon.id if lokasyon else None,
                custom={ag.GRUP: ozel},
            )
            db.add(varlik)
            db.flush()
            db.add(models.ActivityLog(
                action=models.ActivityAction.create, item_type="asset",
                item_id=varlik.id,
                note=(f"Ağ ürünü içe aktarıldı"
                      + (f" — {args.nereden} → {lokasyon.name}"
                         if args.nereden and lokasyon else "")),
                # Transfer görünümü lokasyon değişimini buradan okur
                changes=({"location_id": {"eski": kaynak_deger,
                                          "yeni": str(lokasyon.id)}}
                         if kaynak_deger and lokasyon else None),
            ))
        db.commit()
        print(f"\n\033[1;32m✓ {len(eklenecek)} ağ ürünü eklendi.\033[0m")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
