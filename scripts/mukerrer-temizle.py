#!/usr/bin/env python3
"""Mükerrer kayıtları bulur: lokasyonları birleştirir, cihazları raporlar.

İki tür mükerrer birikmişti:

1) **Lokasyonlar** — aynı şantiye farklı yazımlarla birden çok kez açılmış
   ("ŞANTİYE U026" / "Şantiye U026" / "SANTIYE U026"). Betik adları
   sadeleştirip gruplar; --uygula ile her grupta TEK kayıt kalır: cihaz,
   zimmet-yeri ve personel bağlantıları kalan kayda taşınır, boş alanları
   (proje kodu, şehir, adres) silinenlerden tamamlanır. Veri kaybolmaz.

2) **Cihazlar** — içe aktarım aynı cihazı "-2, -3" ekleriyle çoğaltmıştı
   (B001, B001-2, B001-3) ya da aynı seri numarası iki kayıtta duruyor.
   Cihaz birleştirme OTOMATİK YAPILMAZ: iki kayıt gerçekten aynı fiziksel
   cihaz mı, karar insanındır. Betik grupları yan yana döker; silinecekleri
   Varlıklar ekranındaki onay kutuları + "Seçilileri sil" ile temizlersiniz.

Bundan sonrası zaten engelli: içe aktarım serisiz satırları etiketle
eşleştirir, arayüz aynı adla lokasyon ve aynı seri numarasıyla cihaz açtırmaz.

Kullanım:
    ./.venv/bin/python scripts/mukerrer-temizle.py             # yalnızca rapor
    ./.venv/bin/python scripts/mukerrer-temizle.py --uygula    # lokasyonları birleştir
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402

M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'


# --------------------------------------------------------------------------- #
# Lokasyonlar
# --------------------------------------------------------------------------- #
def lokasyon_gruplari(db: Session) -> list[list[models.Location]]:
    """Sadeleştirilmiş adı aynı olan lokasyon grupları (yalnız 2+ üyeliler)."""
    gruplar: dict[str, list[models.Location]] = {}
    for lok in db.scalars(select(models.Location)).all():
        if lok.name:
            gruplar.setdefault(_sadelestir(lok.name), []).append(lok)
    return [sorted(g, key=lambda x: x.id) for g in gruplar.values()
            if len(g) > 1]


_LOKASYON_SUTUNLARI = (
    models.Asset.location_id, models.Asset.assigned_location_id,
    models.User.location_id, models.Accessory.location_id,
    models.Consumable.location_id, models.Component.location_id,
)


def _referans_sayilari(db: Session) -> dict[int, int]:
    """Lokasyon başına bağlantı sayısı (cihaz + zimmet yeri + personel + stok)."""
    sayilar: dict[int, int] = {}
    for sutun in _LOKASYON_SUTUNLARI:
        tablo = sutun.parent.class_
        for kimlik, adet in db.execute(
                select(sutun, func.count()).select_from(tablo)
                .where(sutun.is_not(None)).group_by(sutun)).all():
            sayilar[kimlik] = sayilar.get(kimlik, 0) + adet
    return sayilar


def lokasyonlari_birlestir(db: Session, gruplar, sayilar) -> tuple[int, int]:
    """Her grupta bir kayıt kalır; (silinen, taşınan bağlantı) döner."""
    silinen = tasinan = 0
    for grup in gruplar:
        # Kalacak kayıt: proje kodu dolu olan; eşitse en çok bağlantılı olan
        kalan = max(grup, key=lambda x: (bool(x.proje_kodu),
                                         sayilar.get(x.id, 0), -x.id))
        digerleri = [x for x in grup if x.id != kalan.id]
        kimlikler = [x.id for x in digerleri]

        for sutun in _LOKASYON_SUTUNLARI:
            tablo = sutun.parent.class_
            tasinan += db.execute(
                update(tablo).where(sutun.in_(kimlikler))
                .values({sutun.key: kalan.id})).rowcount
        # Geçmiş kayıtları da kalan kayda baksın
        db.execute(update(models.ActivityLog)
                   .where(models.ActivityLog.target_type == "location",
                          models.ActivityLog.target_id.in_(kimlikler))
                   .values(target_id=kalan.id))

        # Alt lokasyonlar kalan kayda bağlanır (kalan, silinenin altındaysa
        # yukarı alınır — kendi kendisinin altına düşmesin)
        for d in digerleri:
            for cocuk in db.scalars(select(models.Location).where(
                    models.Location.parent_id == d.id)).all():
                cocuk.parent_id = d.parent_id if cocuk.id == kalan.id \
                    else kalan.id

        for alan in ("proje_kodu", "city", "address", "renk"):
            if not getattr(kalan, alan, None):
                for d in digerleri:
                    deger = getattr(d, alan, None)
                    if deger:
                        setattr(kalan, alan, deger)
                        break
        for d in digerleri:
            db.delete(d)
            silinen += 1
    db.commit()
    return silinen, tasinan


# --------------------------------------------------------------------------- #
# Cihazlar (yalnızca rapor)
# --------------------------------------------------------------------------- #
def cihaz_gruplari(db: Session) -> tuple[list[list], list[list]]:
    """(aynı seri numaralılar, taban etiketi aynı olanlar) — 2+ üyeli gruplar."""
    varliklar = db.scalars(select(models.Asset)
                           .order_by(models.Asset.asset_tag)).all()

    seri: dict[str, list] = {}
    for a in varliklar:
        if (a.serial or "").strip():
            seri.setdefault(a.serial.strip(), []).append(a)

    etiketler = {a.asset_tag for a in varliklar}
    taban: dict[str, list] = {}
    for a in varliklar:
        e = a.asset_tag or ""
        kok = re.sub(r"-\d+$", "", e)
        # "B001-2" yalnızca "B001" diye bir kayıt gerçekten VARSA şüphelidir
        if kok != e and kok in etiketler:
            taban.setdefault(kok, [])
    for a in varliklar:
        kok = re.sub(r"-\d+$", "", a.asset_tag or "")
        if kok in taban:
            taban[kok].append(a)

    return ([g for g in seri.values() if len(g) > 1],
            [sorted(g, key=lambda x: x.asset_tag) for g in taban.values()
             if len(g) > 1])


def _cihaz_satiri(db: Session, a: models.Asset) -> str:
    lok = db.get(models.Location, a.location_id) if a.location_id else None
    durum = db.get(models.StatusLabel, a.status_id) if a.status_id else None
    kisi = db.get(models.User, a.assigned_user_id) if a.assigned_user_id else None
    dosya = db.scalar(select(func.count(models.AssetFile.id))
                      .where(models.AssetFile.asset_id == a.id)) or 0
    parcalar = [
        f"{a.asset_tag:<18}", (a.name or "—")[:28].ljust(28),
        f"seri:{(a.serial or '—')[:16]:<16}",
        (lok.name if lok else "—")[:20].ljust(20),
        (durum.name if durum else "—")[:14].ljust(14),
    ]
    if kisi:
        parcalar.append(f"{S}zimmetli:{kisi.first_name}{N}")
    if dosya:
        parcalar.append(f"{dosya} dosya")
    return "  ".join(parcalar)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uygula", action="store_true",
                    help="mükerrer lokasyonları birleştir (cihazlar her zaman "
                         "yalnızca raporlanır)")
    args = ap.parse_args()

    from app.database import SessionLocal  # noqa: E402
    from app.ortam_uyari import uyar  # noqa: E402

    uyar()
    db = SessionLocal()
    try:
        gruplar = lokasyon_gruplari(db)
        sayilar = _referans_sayilari(db)

        if gruplar:
            print(f"\n{M}Mükerrer lokasyonlar — {len(gruplar)} grup{N}")
            for grup in gruplar:
                print()
                for lok in grup:
                    print(f"  #{lok.id:<5} {lok.name:<40} "
                          f"proje:{lok.proje_kodu or '—':<8} "
                          f"{sayilar.get(lok.id, 0):>4} bağlantı")
        else:
            print(f"\n{Y}✓ Mükerrer lokasyon yok.{N}")

        seri_grup, etiket_grup = cihaz_gruplari(db)
        if seri_grup:
            print(f"\n{M}Aynı seri numaralı cihazlar — {len(seri_grup)} grup "
                  f"(büyük olasılıkla aynı cihaz){N}")
            for g in seri_grup[:20]:
                print()
                for a in g:
                    print("  " + _cihaz_satiri(db, a))
            if len(seri_grup) > 20:
                print(f"\n  … ve {len(seri_grup) - 20} grup daha")
        if etiket_grup:
            print(f"\n{M}Sonekli etiket grupları — {len(etiket_grup)} grup "
                  f"(B001 / B001-2 gibi){N}")
            for g in etiket_grup[:20]:
                print()
                for a in g:
                    print("  " + _cihaz_satiri(db, a))
            if len(etiket_grup) > 20:
                print(f"\n  … ve {len(etiket_grup) - 20} grup daha")
        if not seri_grup and not etiket_grup:
            print(f"\n{Y}✓ Mükerrer cihaz görünmüyor.{N}")
        else:
            print(f"\n  Cihazlar otomatik birleştirilmez: hangisinin kalacağına "
                  f"bakıp Varlıklar ekranında\n  onay kutularıyla seçip "
                  f"{S}Seçilileri sil{N} ile temizleyin.")

        if not args.uygula:
            if gruplar:
                print(f"\n{M}Rapor modundasınız — hiçbir şey değişmedi.{N}")
                print("  Lokasyonları birleştirmek için: "
                      "./.venv/bin/python scripts/mukerrer-temizle.py --uygula")
            return 0

        if gruplar:
            silinen, tasinan = lokasyonlari_birlestir(db, gruplar, sayilar)
            print(f"\n{Y}✓ {silinen} mükerrer lokasyon silindi, "
                  f"{tasinan} bağlantı kalan kayda taşındı.{N}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
