#!/usr/bin/env python3
"""Adı bir sistem türünü söyleyen ama yanlış kategoride duran modelleri düzeltir.

Sistem ekranları (Ağ / Yangın / Alarm / Geçiş / Kantar) cihazın türünü
**kategori adından** çıkarır (bkz. app/sistem_sablonlari.py: tur_bul). Model
yanlış kategoriye bağlandıysa — örn. LigoWave linkleri "Projeksiyon"
kategorisinde — cihaz hem yanlış türde listelenir hem de sistem ekranlarına
hiç düşmez.

Bu betik her modelin adına (gerekirse marka + ad ve cihaz adlarına) bakar;
bilinen bir sistem türü çıkıyorsa ama modelin mevcut kategorisi o türe
eşlenmiyorsa, modeli doğru kategoriye taşımayı önerir. Hedef kategori yoksa
türün resmi adıyla (örn. "Noktadan Noktaya Link") açılır.

Kullanım:
    ./.venv/bin/python scripts/kategori-duzelt.py             # yalnızca rapor
    ./.venv/bin/python scripts/kategori-duzelt.py --uygula    # önerileri yaz

Cihaz kayıtlarına dokunulmaz: yalnızca modelin category_id alanı değişir,
zimmet/dosya/etiket aynen kalır. Betik idempotenttir — ikinci koşuşta
"öneri yok" der.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import ag, models  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402


def _tur_tahmini(model: models.AssetModel, marka: str | None,
                 cihaz_adlari: list[str]) -> str | None:
    """Modelin hangi sistem türüne ait olduğunu adlardan çıkarır.

    Önce modelin kendi adı ve "marka + ad" denenir; oradan tür çıkmazsa bu
    modeli kullanan cihazların adlarına bakılır. Cihaz adları yalnızca hepsi
    AYNI türü söylüyorsa kabul edilir — biri switch biri kamera diyorsa model
    karışıktır, tahmin yapılmaz.
    """
    for metin in (model.name, f"{marka or ''} {model.name or ''}"):
        tur = ag.tur_bul(metin)
        if tur:
            return tur
    turler = {t for t in (ag.tur_bul(ad) for ad in cihaz_adlari) if t}
    return turler.pop() if len(turler) == 1 else None


def oneri_listesi(db: Session) -> list[dict]:
    """Yanlış kategorideki modeller için taşıma önerileri.

    Her öneri: {model, tahmin, eski_kategori, yeni_kategori_adi, adet}.
    Mevcut kategorisi zaten doğru türe eşlenen modeller atlanır.
    """
    kategori_tur = {k.id: ag.tur_bul(k.name)
                    for k in db.scalars(select(models.Category)).all()}
    kategori_adi = dict(db.execute(
        select(models.Category.id, models.Category.name)).all())
    markalar = {m.id: m.name
                for m in db.scalars(select(models.Manufacturer)).all()}
    sayilar = dict(db.execute(
        select(models.Asset.model_id, func.count(models.Asset.id))
        .where(models.Asset.model_id.is_not(None))
        .group_by(models.Asset.model_id)).all())
    cihaz_adlari: dict[int, list[str]] = {}
    for mid, ad in db.execute(
            select(models.Asset.model_id, models.Asset.name)
            .where(models.Asset.model_id.is_not(None),
                   models.Asset.name.is_not(None))).all():
        cihaz_adlari.setdefault(mid, []).append(ad)

    oneriler = []
    for m in db.scalars(select(models.AssetModel)
                        .order_by(models.AssetModel.name)).all():
        mevcut_tur = kategori_tur.get(m.category_id)
        tahmin = _tur_tahmini(m, markalar.get(m.manufacturer_id),
                              cihaz_adlari.get(m.id, []))
        if not tahmin or tahmin == mevcut_tur:
            continue
        oneriler.append({
            "model": m,
            "tahmin": tahmin,
            "eski_kategori": kategori_adi.get(m.category_id),
            "yeni_kategori_adi": ag.kategori_adi(tahmin),
            "adet": sayilar.get(m.id, 0),
        })
    return oneriler


def uygula(db: Session, oneriler: list[dict]) -> int:
    """Önerileri yazar; hedef kategori yoksa açar. Açılan kategori sayısı döner."""
    sade_kategori = {_sadelestir(k.name): k
                     for k in db.scalars(select(models.Category)).all() if k.name}
    acilan = 0
    for o in oneriler:
        hedef = sade_kategori.get(_sadelestir(o["yeni_kategori_adi"]))
        if hedef is None:
            hedef = models.Category(name=o["yeni_kategori_adi"])
            db.add(hedef)
            db.flush()
            sade_kategori[_sadelestir(hedef.name)] = hedef
            acilan += 1
        o["model"].category_id = hedef.id
    db.commit()
    return acilan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uygula", action="store_true",
                    help="önerileri veritabanına yaz (varsayılan: yalnızca rapor)")
    args = ap.parse_args()

    from app.database import SessionLocal  # noqa: E402  (testler içeri almasın)
    from app.ortam_uyari import uyar  # noqa: E402

    uyar()
    db = SessionLocal()
    M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'
    try:
        oneriler = oneri_listesi(db)
        if not oneriler:
            print(f"\n{Y}✓ Yanlış kategoride model bulunamadı.{N}")
            return 0

        print(f"\n{M}Yanlış kategorideki modeller{N}")
        for o in sorted(oneriler, key=lambda x: -x["adet"]):
            aile = ag.AILELER[ag.TURLER[o["tahmin"]]["aile"]]["ad"]
            print(f"  {S}→{N} {o['model'].name:<38} {o['adet']:>4} cihaz")
            print(f"      {o['eski_kategori'] or '(kategorisiz)'}"
                  f"  ⇒  {Y}{o['yeni_kategori_adi']}{N}  ({aile})")
        etkilenen = sum(o["adet"] for o in oneriler)
        print(f"\n  {len(oneriler)} model, {etkilenen} cihaz düzelecek.")

        if not args.uygula:
            print(f"\n{M}Rapor modundasınız — hiçbir şey değişmedi.{N}")
            print("  Yazmak için: ./.venv/bin/python scripts/kategori-duzelt.py "
                  "--uygula")
            return 0

        acilan = uygula(db, oneriler)
        print(f"\n{Y}✓ {len(oneriler)} model doğru kategoriye taşındı"
              f" ({acilan} yeni kategori açıldı).{N}")
        print("  Cihazlar artık ilgili sistem ekranında görünür; sunucuyu "
              "yeniden başlatmak gerekmez.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
