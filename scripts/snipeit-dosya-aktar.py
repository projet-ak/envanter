#!/usr/bin/env python3
"""Snipe-IT'teki görselleri ve belgeleri sisteme aktarır.

Snipe-IT dosyaları veritabanında tutmaz; adları kayıtlarda, içerikleri diskte
durur. Bu yüzden iki şey gerekir: **döküm** (hangi dosya kime ait) ve
**Snipe-IT klasörü** (dosyaların kendisi).

Nereden ne alınır:

    cihaz görseli      assets.image            → cihaz eki (görsel)
    model görseli      models.image            → o modelin cihazlarına (isteğe bağlı)
    cihaz belgesi      action_logs (Asset)     → cihaz eki (belge)
    kişi belgesi       action_logs (User)      → kişi eki (imzalı zimmet formu)
    aksesuar/sarf/     accessories.image ve    → stok kaydı eki
    bileşen/lisans     action_logs (Accessory…)

Snipe-IT sürümleri dosyaları farklı klasörlere koyar (`public/uploads/assets`,
`storage/private_uploads/users`…). Bu yüzden verilen klasörün ALTINDA ad ile
arama yapılır; sürüm farkı sorun olmaz.

Kullanım:
    ./.venv/bin/python scripts/snipeit-dosya-aktar.py dokum.sql /path/snipe-it
    ./.venv/bin/python scripts/snipeit-dosya-aktar.py dokum.sql /path/snipe-it \\
        --uygula --model-gorselleri
"""

from __future__ import annotations

import argparse
import mimetypes
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402
from app.routers.dosyalar import (GORSEL_UZANTILAR, IZINLI_UZANTILAR,  # noqa: E402
                                  tam_yol, yeni_yol)

# Döküm okuma yardımcıları karşılaştırma betiğinden gelir (tek kaynak)
sys.path.insert(0, str(Path(__file__).resolve().parent))
_kars = __import__("importlib").import_module("importlib.util")
_spec = _kars.spec_from_file_location(
    "snipeit_karsilastir", Path(__file__).resolve().parent / "snipeit-karsilastir.py")
_mod = _kars.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sql_tablo, _onek_bul = _mod.sql_tablo, _mod._onek_bul

M, Y, S, K, N = '\033[36m', '\033[32m', '\033[33m', '\033[31m', '\033[0m'


def _dosya_dizini(kok: Path) -> dict[str, Path]:
    """Klasörün altındaki tüm dosyaları ada göre indeksler (ilk bulunan kazanır)."""
    dizin: dict[str, Path] = {}
    for yol in kok.rglob("*"):
        if yol.is_file():
            dizin.setdefault(yol.name, yol)
    return dizin


def _tur_sec(ad: str) -> models.DosyaTuru:
    uz = Path(ad).suffix.lower()
    if uz in GORSEL_UZANTILAR:
        return models.DosyaTuru.gorsel
    if "zimmet" in _sadelestir(ad) or "demirbas" in _sadelestir(ad):
        return models.DosyaTuru.zimmet_formu
    return models.DosyaTuru.diger


def _snipe_adi(ham: str) -> str:
    """`user-3-0mQ0RyRs-yldz-demirbas-zimmet-rep-766984.pdf` içindeki asıl adı verir.

    Snipe-IT yüklerken başa `<tür>-<id>-<rastgele>-` ekler; kullanıcının
    göreceği adda bu gürültü olmasın.
    """
    m = re.match(r"^(?:asset|user|model|accessory|component|consumable|license)"
                 r"[-_]?[a-z]*-?\d*-[A-Za-z0-9]{6,}-(.+)$", ham)
    return m.group(1) if m else ham


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dokum", type=Path, help="Snipe-IT mysqldump dosyası (.sql)")
    ap.add_argument("klasor", type=Path,
                    help="Snipe-IT kurulum klasörü (içinde aranır)")
    ap.add_argument("--uygula", action="store_true",
                    help="dosyaları kopyala ve kaydet (varsayılan: rapor)")
    ap.add_argument("--model-gorselleri", action="store_true",
                    help="model görselini o modelin cihazlarına da ekle")
    ap.add_argument("--kisi-pdf-zimmet", action="store_true",
                    help="kişiye bağlı PDF'leri baştan 'imzalı zimmet formu' "
                         "say (adları tmp… olduğu için addan anlaşılmıyor)")
    args = ap.parse_args()

    for yol in (args.dokum, args.klasor):
        if not yol.exists():
            print(f"{K}Bulunamadı: {yol}{N}")
            return 1

    dokum = args.dokum.read_text("utf-8", errors="replace")
    o = _onek_bul(dokum)
    ast = {a["id"]: a for a in sql_tablo(dokum, o + "assets")}
    # Boş ya da yarım kalmış döküm sessizce "0 dosya" olarak geçmesin:
    # mysqldump parola hatası verdiğinde dosya 0 byte kalıyor.
    if not ast:
        print(f"{K}Dökümde cihaz kaydı bulunamadı: {args.dokum} "
              f"({args.dokum.stat().st_size} byte){N}")
        print("  • Dosya boşsa mysqldump başarısız olmuştur (parola hatası?)")
        print("  • Dosya doluysa beklenen tablo yok: `assets` ya da `<önek>_assets`")
        return 1
    mdl = {m["id"]: m for m in sql_tablo(dokum, o + "models")}
    kul = {k["id"]: k for k in sql_tablo(dokum, o + "users")}
    loglar = [x for x in sql_tablo(dokum, o + "action_logs") if x.get("filename")]
    # Stok kayıtları: Snipe-IT sınıf adı -> (bizdeki tür, tablo, döküm satırları)
    STOK = {
        "Accessory": (models.StokTuru.accessory, models.Accessory,
                      {s["id"]: s for s in sql_tablo(dokum, o + "accessories")}),
        "Consumable": (models.StokTuru.consumable, models.Consumable,
                       {s["id"]: s for s in sql_tablo(dokum, o + "consumables")}),
        "Component": (models.StokTuru.component, models.Component,
                      {s["id"]: s for s in sql_tablo(dokum, o + "components")}),
        "License": (models.StokTuru.license, models.License,
                    {s["id"]: s for s in sql_tablo(dokum, o + "licenses")}),
    }

    diskte = _dosya_dizini(args.klasor)
    print(f"\n{M}Kaynak{N}")
    print(f"  Döküm tablo öneki : {o or '(yok)'}")
    print(f"  Klasördeki dosya  : {len(diskte)}")

    uyar()
    db = SessionLocal()
    try:
        # Sistemdeki eşleşmeler: cihaz etiketiyle, kişi ad-soyadla
        varliklar = {_sadelestir(a.asset_tag): a
                     for a in db.scalars(select(models.Asset)).all() if a.asset_tag}
        kisiler = {}
        for k in db.scalars(select(models.User)).all():
            kisiler.setdefault(_sadelestir(k.full_name), k)

        # Stok kayıtları ada göre eşleşir (Snipe-IT kimlikleri bizde saklı değil)
        stok_kayitlari: dict[models.StokTuru, dict] = {}
        for tur_ad, (stok_turu, tablo, _) in STOK.items():
            harita = {}
            for nesne in db.scalars(select(tablo)).all():
                if nesne.name:
                    harita.setdefault(_sadelestir(nesne.name), nesne)
            stok_kayitlari[stok_turu] = harita

        # Zaten aktarılmış mı? Aynı dosya adı iki kez eklenmesin.
        var_olan = {("cihaz", d.asset_id, d.dosya_adi)
                    for d in db.scalars(select(models.AssetFile)).all()}
        var_olan |= {("kisi", d.user_id, d.dosya_adi)
                     for d in db.scalars(select(models.UserFile)).all()}
        var_olan |= {(d.kayit_turu.value, d.kayit_id, d.dosya_adi)
                     for d in db.scalars(select(models.StockFile)).all()}

        isler: list[tuple] = []          # (sahip_tipi, sahip, kaynak_yol, ad, tür)
        eksik_dosya, eslesmeyen = [], []

        def ekle(sahip_tipi, sahip, dosya_adi, kaynak_etiket):
            """sahip_tipi: "cihaz" | "kisi" | StokTuru değeri ("accessory"…)"""
            kaynak = diskte.get(dosya_adi)
            if kaynak is None:
                eksik_dosya.append((kaynak_etiket, dosya_adi))
                return
            ad = _snipe_adi(dosya_adi)
            if Path(ad).suffix.lower() not in IZINLI_UZANTILAR:
                eksik_dosya.append((kaynak_etiket, f"{dosya_adi} (izinsiz tür)"))
                return
            if (sahip_tipi, sahip.id, ad) in var_olan:
                return                                     # zaten aktarılmış
            tur = _tur_sec(ad)
            if (args.kisi_pdf_zimmet and sahip_tipi == "kisi"
                    and Path(ad).suffix.lower() == ".pdf"):
                tur = models.DosyaTuru.zimmet_formu
            isler.append((sahip_tipi, sahip, kaynak, ad, tur))

        # 1) Cihaz görselleri
        for a in ast.values():
            if not a.get("image") or a.get("deleted_at"):
                continue
            hedef = varliklar.get(_sadelestir(a.get("asset_tag") or ""))
            if hedef is None:
                eslesmeyen.append(("cihaz", a.get("asset_tag")))
                continue
            ekle("cihaz", hedef, a["image"], a.get("asset_tag"))

        # 2) Model görselleri -> o modelin cihazlarına
        if args.model_gorselleri:
            for m in mdl.values():
                if not m.get("image"):
                    continue
                for a in ast.values():
                    if a.get("model_id") != m["id"] or a.get("deleted_at"):
                        continue
                    hedef = varliklar.get(_sadelestir(a.get("asset_tag") or ""))
                    if hedef is not None:
                        ekle("cihaz", hedef, m["image"], a.get("asset_tag"))

        # 3) Stok kayıtlarının görselleri (accessories.image vb.)
        for tur_ad, (stok_turu, _, satirlar) in STOK.items():
            for kayit in satirlar.values():
                if not kayit.get("image") or kayit.get("deleted_at"):
                    continue
                ad = kayit.get("name") or ""
                hedef = stok_kayitlari[stok_turu].get(_sadelestir(ad))
                if hedef is None:
                    eslesmeyen.append((stok_turu.value, ad))
                    continue
                ekle(stok_turu.value, hedef, kayit["image"], ad)

        # 4) Loglardaki yüklemeler: cihaz, kişi ve stok ekleri
        aksesuar_atlanan = 0
        for l in loglar:
            tur = (l.get("item_type") or "").split("\\")[-1].replace("\\", "")
            if tur == "Asset":
                a = ast.get(l["item_id"])
                hedef = varliklar.get(_sadelestir((a or {}).get("asset_tag") or ""))
                if hedef is None:
                    eslesmeyen.append(("cihaz", (a or {}).get("asset_tag")))
                    continue
                ekle("cihaz", hedef, l["filename"], (a or {}).get("asset_tag"))
            elif tur == "User":
                k = kul.get(l["item_id"])
                ad = " ".join(filter(None, [(k or {}).get("first_name"),
                                            (k or {}).get("last_name")]))
                hedef = kisiler.get(_sadelestir(ad))
                if hedef is None:
                    eslesmeyen.append(("kişi", ad))
                    continue
                ekle("kisi", hedef, l["filename"], ad)
            elif tur in STOK:
                stok_turu, _, satirlar = STOK[tur]
                kayit = satirlar.get(l["item_id"]) or {}
                ad = kayit.get("name") or ""
                hedef = stok_kayitlari[stok_turu].get(_sadelestir(ad))
                if hedef is None:
                    eslesmeyen.append((stok_turu.value, ad or f"#{l['item_id']}"))
                    continue
                ekle(stok_turu.value, hedef, l["filename"], ad)
            elif tur == "AssetModel":
                m = mdl.get(l["item_id"])
                if not (args.model_gorselleri and m):
                    aksesuar_atlanan += 1
                    continue
                for a in ast.values():
                    if a.get("model_id") == m["id"] and not a.get("deleted_at"):
                        hedef = varliklar.get(
                            _sadelestir(a.get("asset_tag") or ""))
                        if hedef is not None:
                            ekle("cihaz", hedef, l["filename"],
                                 a.get("asset_tag"))

        cihaz_isleri = [i for i in isler if i[0] == "cihaz"]
        kisi_isleri = [i for i in isler if i[0] == "kisi"]
        stok_isleri = [i for i in isler if i[0] not in ("cihaz", "kisi")]
        print(f"\n{M}Aktarılacak{N}")
        print(f"  {Y}Cihaz eki : {len(cihaz_isleri)}{N}")
        print(f"  {Y}Kişi eki  : {len(kisi_isleri)}{N}")
        print(f"  {Y}Stok eki  : {len(stok_isleri)}{N}"
              f"  (aksesuar/sarf/bileşen/lisans)")
        if aksesuar_atlanan:
            print(f"  {S}Atlanan   : {aksesuar_atlanan} "
                  f"(model eki — tek bir cihaza bağlanamıyor, "
                  f"--model-gorselleri ile alınabilir){N}")
        for tip, sahip, kaynak, ad, tur in isler[:15]:
            kime = (sahip.asset_tag if tip == "cihaz"
                    else sahip.full_name if tip == "kisi" else sahip.name)
            print(f"    {tip:<5} {str(kime)[:26]:<26} ← {ad[:40]} "
                  f"[{tur.value}]")
        if len(isler) > 15:
            print(f"    … ve {len(isler) - 15} dosya daha")

        if eksik_dosya:
            print(f"\n{S}Kayıtta var ama klasörde yok: {len(eksik_dosya)}{N}")
            for kim, ad in eksik_dosya[:10]:
                print(f"    {str(kim)[:24]:<24} {ad}")
            if len(eksik_dosya) > 10:
                print(f"    … ve {len(eksik_dosya) - 10} dosya daha")
            print("    → Snipe-IT klasörünün tamamını verdiğinizden emin olun")
        if eslesmeyen:
            benzersiz = sorted({f"{t}: {a}" for t, a in eslesmeyen if a})
            print(f"\n{S}Sistemde karşılığı bulunamayan sahip: "
                  f"{len(benzersiz)}{N}")
            for x in benzersiz[:10]:
                print(f"    {x}")

        if not args.uygula:
            print(f"\n{M}Rapor modundasınız — hiçbir dosya kopyalanmadı.{N}")
            print("  Kopyalamak için --uygula ekleyin.")
            if not args.model_gorselleri:
                print("  Model görsellerini de cihazlara eklemek için: "
                      "--model-gorselleri")
            return 0

        if not isler:
            print(f"\n{Y}✓ Aktarılacak yeni dosya yok.{N}")
            return 0

        kopyalanan = 0
        for tip, sahip, kaynak, ad, tur in isler:
            icerik = kaynak.read_bytes()
            on_ek = {"cihaz": "", "kisi": "k", "accessory": "a",
                     "consumable": "s", "component": "b", "license": "l"}[tip]
            goreli = yeni_yol(sahip.id, tur, Path(ad).suffix.lower(), on_ek=on_ek)
            hedef = tam_yol(goreli)
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(icerik)
            ortak = dict(tur=tur, dosya_adi=ad, yol=goreli,
                         content_type=mimetypes.guess_type(ad)[0],
                         boyut=len(icerik), aciklama="Snipe-IT'ten aktarıldı",
                         yukleyen="snipeit-aktarim")
            if tip == "cihaz":
                db.add(models.AssetFile(asset_id=sahip.id, **ortak))
            elif tip == "kisi":
                db.add(models.UserFile(user_id=sahip.id, **ortak))
            else:
                db.add(models.StockFile(kayit_turu=models.StokTuru(tip),
                                        kayit_id=sahip.id, **ortak))
            kopyalanan += 1
        db.commit()
        print(f"\n{Y}✓ {kopyalanan} dosya aktarıldı "
              f"({len(cihaz_isleri)} cihaz, {len(kisi_isleri)} kişi, "
              f"{len(stok_isleri)} stok eki).{N}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
