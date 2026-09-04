#!/usr/bin/env python3
"""Cihaz numarasının önekine göre kategori işler (N… → Dizüstü, M… → Monitör).

Kurumdaki numaralandırma cihaz tipini söylüyor: N245 bir dizüstü, M229 bir
monitör. Eski aktarımlarda kategori boş kaldıysa ya da yanlış kategoriye
düştüyse bu betik numaradan yola çıkıp düzeltir.

Önek kuralı harf + RAKAM olarak aranır (`^N\\d`): "N245" eşleşir, "NVR-01"
eşleşmez — yoksa NVR kayıtları dizüstü sanılırdı.

Kategori cihazda değil MODELDE tutulur. Betik cihazın modelini korur:
  * model yoksa       → kategori adıyla bir model açılır ve cihaza bağlanır
  * modeli tek cihaz kullanıyorsa → modelin kategorisi taşınır
  * modeli başkaları da kullanıyorsa → hedef kategoride aynı adlı model
    bulunur/açılır ve YALNIZ bu cihaz ona bağlanır (diğerleri etkilenmez)

Kullanım:
    # Ne olacağını gör (hiçbir şey yazılmaz):
    ./.venv/bin/python scripts/kod-kategori.py

    # Uygula:
    ./.venv/bin/python scripts/kod-kategori.py --uygula

    # Başka önekler de ekle (varsayılanların üstüne):
    ./.venv/bin/python scripts/kod-kategori.py --kural "B=Masaüstü Bilgisayar"

Her değişiklik cihazın işlem geçmişine yazılır.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402

M, Y, S, N = "\033[36m", "\033[32m", "\033[33m", "\033[0m"

VARSAYILAN_KURALLAR = {"N": "Dizüstü Bilgisayar", "M": "Monitör"}


def kural_coz(ciftler: list[str] | None) -> dict[str, str]:
    """--kural 'B=Masaüstü Bilgisayar' değerlerini sözlüğe çevirir."""
    kurallar = dict(VARSAYILAN_KURALLAR)
    for cift in ciftler or []:
        if "=" not in cift:
            raise ValueError(f"--kural 'ONEK=Kategori' biçiminde olmalı: {cift}")
        onek, kategori = cift.split("=", 1)
        onek, kategori = onek.strip().upper(), kategori.strip()
        if not onek or not kategori:
            raise ValueError(f"Eksik kural: {cift}")
        kurallar[onek] = kategori
    return kurallar


def kategori_bul(etiket: str | None, kurallar: dict[str, str]) -> str | None:
    """Cihaz numarasının önekinden kategori adı. Eşleşme yoksa None.

    Harften sonra RAKAM gelmeli: 'N245' → Dizüstü, 'NVR-01' → None.
    """
    ham = (etiket or "").strip().upper()
    for onek, kategori in kurallar.items():
        if re.match(rf"^{re.escape(onek)}\s*[-_]?\d", ham):
            return kategori
    return None


def _kategori_al(db: Session, ad: str, onbellek: dict) -> models.Category:
    anahtar = _sadelestir(ad)
    kategori = onbellek.get(anahtar)
    if kategori is None:
        kategori = models.Category(name=ad)
        db.add(kategori)
        db.flush()
        onbellek[anahtar] = kategori
    return kategori


def _model_al(db: Session, ad: str, kategori_id: int, uretici_id: int | None,
              onbellek: dict) -> models.AssetModel:
    anahtar = (_sadelestir(ad), kategori_id)
    model = onbellek.get(anahtar)
    if model is None:
        model = models.AssetModel(name=ad, category_id=kategori_id,
                                  manufacturer_id=uretici_id)
        db.add(model)
        db.flush()
        onbellek[anahtar] = model
    return model


def oneriler(db: Session, kurallar: dict[str, str]) -> list[dict]:
    """Kategorisi kurala uymayan cihazlar için değişiklik listesi."""
    kategoriler = {k.id: k for k in db.scalars(select(models.Category)).all()}
    modeller = {m.id: m for m in db.scalars(select(models.AssetModel)).all()}
    model_kullanim = dict(db.execute(
        select(models.Asset.model_id, func.count(models.Asset.id))
        .where(models.Asset.model_id.is_not(None))
        .group_by(models.Asset.model_id)).all())

    liste = []
    for a in db.scalars(select(models.Asset).order_by(models.Asset.asset_tag)).all():
        hedef_ad = kategori_bul(a.asset_tag, kurallar)
        if not hedef_ad:
            continue
        model = modeller.get(a.model_id)
        mevcut = kategoriler.get(model.category_id) if model else None
        if mevcut is not None and _sadelestir(mevcut.name) == _sadelestir(hedef_ad):
            continue
        liste.append({
            "varlik": a,
            "model": model,
            "eski_kategori": mevcut.name if mevcut else None,
            "yeni_kategori": hedef_ad,
            # Modeli tek bu cihaz kullanıyorsa modelin kendisi taşınabilir
            "model_tekil": bool(model) and model_kullanim.get(model.id, 0) <= 1,
        })
    return liste


def uygula(db: Session, liste: list[dict]) -> dict:
    """Önerileri yazar; taşınan model / açılan model sayısını döner."""
    kategori_onbellek = {_sadelestir(k.name): k
                         for k in db.scalars(select(models.Category)).all()}
    model_onbellek = {(_sadelestir(m.name), m.category_id): m
                      for m in db.scalars(select(models.AssetModel)).all()}
    tasinan = acilan = baglanan = 0

    for o in liste:
        varlik, model = o["varlik"], o["model"]
        kategori = _kategori_al(db, o["yeni_kategori"], kategori_onbellek)
        eski = o["eski_kategori"] or "—"

        if model is None:
            # Modelsiz cihaz: kategori adıyla bir model açılıp bağlanır
            yeni_model = _model_al(db, o["yeni_kategori"], kategori.id, None,
                                   model_onbellek)
            varlik.model_id = yeni_model.id
            acilan += 1
        elif o["model_tekil"]:
            # Modeli yalnız bu cihaz kullanıyor: modelin kategorisi taşınır
            model_onbellek.pop((_sadelestir(model.name), model.category_id), None)
            model.category_id = kategori.id
            model_onbellek[(_sadelestir(model.name), kategori.id)] = model
            tasinan += 1
        else:
            # Model paylaşımlı: hedef kategoride aynı adlı model bulunur/açılır,
            # yalnız bu cihaz oraya bağlanır — diğer cihazlar etkilenmez
            yeni_model = _model_al(db, model.name, kategori.id,
                                   model.manufacturer_id, model_onbellek)
            varlik.model_id = yeni_model.id
            baglanan += 1

        db.add(models.ActivityLog(
            action=models.ActivityAction.update, item_type="asset",
            item_id=varlik.id, actor="kod-kategori",
            note=f"Cihaz numarasına göre kategori: {eski} → {o['yeni_kategori']}",
            changes={"kategori": {"eski": eski, "yeni": o["yeni_kategori"]}}))
    db.commit()
    return {"tasinan_model": tasinan, "acilan_model": acilan,
            "baglanan_cihaz": baglanan}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kural", action="append", metavar="ONEK=Kategori",
                    help="ek önek kuralı (örn. 'B=Masaüstü Bilgisayar')")
    ap.add_argument("--uygula", action="store_true", help="değişiklikleri yaz")
    args = ap.parse_args()

    try:
        kurallar = kural_coz(args.kural)
    except ValueError as hata:
        print(f"{S}{hata}{N}", file=sys.stderr)
        return 1

    uyar()
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        liste = oneriler(db, kurallar)
        print(f"\n{M}Kurallar{N}")
        for onek, kategori in kurallar.items():
            print(f"  {onek}<rakam>… → {kategori}")

        if not liste:
            print(f"\n{Y}✓ Kurala uymayan cihaz yok.{N}")
            return 0

        print(f"\n{M}Değişecek cihaz: {len(liste)}{N}")
        sayac: dict[str, int] = {}
        for o in liste:
            anahtar = f"{o['eski_kategori'] or '(kategorisiz)'} → {o['yeni_kategori']}"
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
        for anahtar, n in sorted(sayac.items(), key=lambda x: -x[1]):
            print(f"  {anahtar:<52} {n}")

        print(f"\n{M}Örnekler{N}")
        for o in liste[:20]:
            model_ad = o["model"].name if o["model"] else "—"
            print(f"  {o['varlik'].asset_tag:<10} {model_ad:<24} "
                  f"{o['eski_kategori'] or '(kategorisiz)':<24} → {o['yeni_kategori']}")

        if not args.uygula:
            print(f"\n{S}⚠ Yalnızca rapor — yazmak için --uygula ekleyin.{N}")
            return 0

        sonuc = uygula(db, liste)
        print(f"\n{Y}✓ {len(liste)} cihazın kategorisi düzeltildi{N}")
        print(f"  Modeli taşınan      : {sonuc['tasinan_model']}")
        print(f"  Yeni modele bağlanan: {sonuc['baglanan_cihaz']}")
        print(f"  Model açılan        : {sonuc['acilan_model']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
