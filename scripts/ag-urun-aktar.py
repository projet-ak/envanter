#!/usr/bin/env python3
"""Ağ / sistem ürünlerini metin tablosundan içe aktarır.

Excel'den kopyalanan tablo doğrudan verilebilir. Başlık satırı varsa
sütunlar ADINDAN tanınır (sıra önemsiz):

    MARKA  MODEL  LOKASYON  SERİ NO  MAC ADRESİ  KAT

Tanınan başlıklar: marka · model/parça no · seri no · mac adresi ·
kat · lokasyon/konum/yer (cihazın binadaki yeri) · açıklama.
Başlık yoksa eski sıra varsayılır: Marka, Model, Seri No, Açıklama.

Kullanım:
    # Önce ne olacağını gör (hiçbir şey yazılmaz):
    ./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur access_point --dry-run

    # Uygula: lokasyona yerleştir, binaya zimmetle, etiketleri üret
    ./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur access_point \
        --lokasyon "ERN HOLDİNG İSTANBUL MERKEZ OFİSİ" --proje-kodu Y005 \
        --zimmet "HOLDİNG BİNASI" --etiket-onek "AP-Y005-"

Seçenekler:
    --tur           sfp | switch | access_point | router | kabinet | diger …
    --lokasyon      Ürünlerin bulunduğu yer (yoksa oluşturulur)
    --proje-kodu    Lokasyonu proje koduyla eşler (mükerrer şantiye açılmasın)
    --zimmet        Kişi yerine bir yere zimmetle (örn. "HOLDİNG BİNASI");
                    kayıt yoksa lokasyonun altında açılır
    --etiket-onek   Seri no olmayanlara sıralı cihaz no üretir (AP-Y005-01…)
    --nereden       Geldiği lokasyon (yalnızca geçmişe transfer notu düşer)
    --dry-run       Yazmadan raporla

Aynı MAC ya da aynı seri no ikinci kez eklenmez; betik tekrar çalıştırılsa
da mükerrer kayıt oluşmaz.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import ag, models  # noqa: E402
from app.routers.ag_urunleri import mac_duzenle  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402


def satirlari_coz(metin: str) -> list[list[str]]:
    """Sütunları çıkarır; boş satırları atar.

    Sekmeli metinde BOŞ HÜCRELER KORUNUR (`\t\t` iki sütun demektir) —
    yoksa seri no sütunu boş olan satırlarda MAC, seri no sanılırdı.
    """
    satirlar = []
    for ham in metin.rstrip().splitlines():
        if not ham.strip():
            continue
        if "\t" in ham:
            parcalar = [p.strip() for p in ham.split("\t")]
        else:
            parcalar = [p.strip() for p in re.split(r" {2,}", ham.strip())]
        if sum(1 for p in parcalar if p) >= 2:
            satirlar.append(parcalar)
    return satirlar


# Başlık adı -> iç alan. Sıra önemli: "seri no" içinde "no" da geçtiği için
# daha belirgin anahtarlar önce denenir.
_BASLIK_ESLEME = [
    (("mac",), "mac"),
    (("seri",), "seri"),
    (("marka", "uretici"), "marka"),
    (("model", "parca no", "tip"), "model"),
    (("kat",), "kat"),
    (("lokasyon", "konum", "yer", "nokta", "bolge"), "konum"),
    (("aciklama", "tanim", "not"), "tanim"),
]


def basliklari_coz(parcalar: list[str]) -> dict[str, int] | None:
    """Başlık satırından sütun haritası çıkarır; başlık değilse None."""
    harita: dict[str, int] = {}
    for i, hucre in enumerate(parcalar):
        sade = _sadelestir(hucre)
        if not sade:
            continue
        for anahtarlar, alan in _BASLIK_ESLEME:
            if any(a in sade for a in anahtarlar):
                harita.setdefault(alan, i)
                break
    # "marka" tek başına yeterli değil: veri satırında da geçebilir
    if "marka" in harita and len(harita) >= 3:
        return harita
    return None


def _hucre(parcalar: list[str], harita: dict[str, int], alan: str) -> str:
    i = harita.get(alan)
    return parcalar[i].strip() if i is not None and i < len(parcalar) else ""


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


def _sonraki_sira(mevcut_etiket: set[str], onek: str | None) -> int:
    """Önekli etiketlerde kaldığı yerden devam etsin (AP-Y005-07 → 8)."""
    if not onek:
        return 1
    en_buyuk = 0
    for e in mevcut_etiket:
        if e and e.startswith(onek):
            kuyruk = e[len(onek):]
            if kuyruk.isdigit():
                en_buyuk = max(en_buyuk, int(kuyruk))
    return en_buyuk + 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Ağ ürünlerini listeden içe aktar")
    ap.add_argument("dosya", help="Sütunlu metin dosyası ('-' ile stdin)")
    ap.add_argument("--tur", default="sfp", choices=sorted(ag.TURLER))
    ap.add_argument("--lokasyon", help="Ürünlerin konulacağı lokasyon adı")
    ap.add_argument("--proje-kodu", dest="proje_kodu",
                    help="lokasyonu proje koduyla eşle (mükerrer açılmasın)")
    ap.add_argument("--zimmet",
                    help="kişi yerine bir yere zimmetle (örn. 'HOLDİNG BİNASI')")
    ap.add_argument("--etiket-onek", dest="etiket_onek",
                    help="seri no olmayanlara sıralı cihaz no üret (AP-Y005-)")
    ap.add_argument("--nereden", help="Geldiği lokasyon (geçmişe not düşülür)")
    ap.add_argument("--dry-run", action="store_true", help="Yazmadan raporla")
    args = ap.parse_args()

    metin = sys.stdin.read() if args.dosya == "-" else Path(args.dosya).read_text()
    ham_satirlar = satirlari_coz(metin)
    harita = None
    satirlar = []
    parca_no_yaz = True                      # başlıksız listelerde eski davranış
    for parcalar in ham_satirlar:
        if harita is None:
            bulunan = basliklari_coz(parcalar)
            if bulunan:                      # başlık satırı: haritayı al, atla
                harita = bulunan
                # Sütun "MODEL" ise model adıdır, parça no değil — ikisini
                # ayırmazsak künyede aynı değer iki kere görünür.
                basi = harita.get("model")
                parca_no_yaz = basi is not None and "parca" in _sadelestir(
                    parcalar[basi])
                continue
        satirlar.append(parcalar)
    if harita is None:                       # başlıksız: eski sıra varsayılır
        harita = {"marka": 0, "model": 1, "seri": 2, "tanim": 3}
    if not satirlar:
        print("✗ Okunabilir satır yok.", file=sys.stderr)
        return 1

    uyar()
    db = SessionLocal()
    try:
        from app.routers.ag_urunleri import _model_bul, _referans

        # Lokasyon: önce proje koduyla ara (aynı şantiye ikinci kez açılmasın),
        # sonra adla; hiçbiri tutmazsa yeni kayıt açılır.
        lokasyon = None
        if args.proje_kodu:
            lokasyon = db.scalar(select(models.Location).where(
                models.Location.proje_kodu == args.proje_kodu))
        if lokasyon is None and args.lokasyon:
            lokasyon = _referans(db, models.Location, args.lokasyon)
            if args.proje_kodu and not lokasyon.proje_kodu:
                lokasyon.proje_kodu = args.proje_kodu

        # Zimmet hedefi: kişi değil bir yer (bina, blok). Yeni açılıyorsa
        # lokasyonun altına bağlanır ki lokasyon ağacında yerini bulsun.
        zimmet_yeri = None
        if args.zimmet:
            zimmet_yeri = _referans(db, models.Location, args.zimmet)
            if zimmet_yeri.parent_id is None and lokasyon is not None \
                    and zimmet_yeri.id != lokasyon.id:
                zimmet_yeri.parent_id = lokasyon.id

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
        mevcut_mac = {m for m in db.scalars(select(models.Asset.mac_address)).all() if m}

        sira = _sonraki_sira(mevcut_etiket, args.etiket_onek)
        eklenecek, atlanan = [], []
        for parcalar in satirlar:
            marka = _hucre(parcalar, harita, "marka")
            model = _hucre(parcalar, harita, "model")
            seri = _hucre(parcalar, harita, "seri")
            tanim = _hucre(parcalar, harita, "tanim")
            mac = mac_duzenle(_hucre(parcalar, harita, "mac"))
            kat = _hucre(parcalar, harita, "kat")
            konum = _hucre(parcalar, harita, "konum")
            kimlik = konum or seri or mac or marka

            if mac and mac in mevcut_mac:
                atlanan.append((kimlik, f"MAC {mac} zaten kayıtlı"))
                continue
            if seri and seri in mevcut_seriler:
                atlanan.append((kimlik, "seri no zaten kayıtlı"))
                continue

            # Cihaz no: seri no varsa o, yoksa üretilen sıra no, o da yoksa MAC
            if seri:
                etiket = seri
            elif args.etiket_onek:
                etiket = f"{args.etiket_onek}{sira:02d}"
                sira += 1
            else:
                etiket = mac or f"{marka}-{model}"
            if etiket in mevcut_etiket:
                atlanan.append((kimlik, f"'{etiket}' etiketi zaten kullanımda"))
                continue

            ozel = sfp_ozellikleri(tanim) if args.tur == "sfp" else (
                {"Açıklama": tanim} if tanim else {})
            if model and parca_no_yaz:
                ozel["Parça No"] = model
            if kat:
                ozel["Kat"] = kat
            if konum:
                ozel["Konum"] = konum
            eklenecek.append((etiket, marka, model, seri, mac, ozel))
            mevcut_etiket.add(etiket)
            if mac:
                mevcut_mac.add(mac)

        print(f"\n\033[1;36m→ {len(satirlar)} satır okundu\033[0m")
        print(f"  Eklenecek : {len(eklenecek)}")
        print(f"  Atlanacak : {len(atlanan)}")
        print(f"  Tür       : {ag.TURLER[args.tur]['ad']}")
        if lokasyon is not None:
            print(f"  Lokasyon  : {lokasyon.name}"
                  + (f" ({lokasyon.proje_kodu})" if lokasyon.proje_kodu else ""))
        if zimmet_yeri is not None:
            print(f"  Zimmet    : {zimmet_yeri.name} (yere zimmet)")
        print()
        for etiket, marka, model, seri, mac, ozel in eklenecek[:50]:
            ek = ", ".join(f"{k}={v}" for k, v in ozel.items() if k != "Parça No")
            print(f"  + {etiket:<16} {marka:<12} {model:<14} {mac or '':<19} {ek}")
        for kimlik, sebep in atlanan[:20]:
            print(f"  - {kimlik:<24} ({sebep})")

        if args.dry_run:
            print("\n\033[33m⚠ KURU ÇALIŞTIRMA — hiçbir değişiklik yapılmadı.\033[0m")
            db.rollback()
            return 0
        if not eklenecek:
            print("\n\033[32m✓ Eklenecek yeni ürün yok.\033[0m")
            return 0

        simdi = dt.datetime.now(dt.timezone.utc)
        for etiket, marka, model, seri, mac, ozel in eklenecek:
            mdl = _model_bul(db, args.tur, marka, model)
            # Ad künyede görünür: "HPE Aruba AP-615-RW — Sağ Koridor 1"
            ad = " ".join(filter(None, [marka, model])) or None
            if ad and ozel.get("Konum"):
                ad = f"{ad} — {ozel['Konum']}"
            varlik = models.Asset(
                asset_tag=etiket,
                name=ad,
                serial=seri or None,
                mac_address=mac,
                model_id=mdl.id,
                location_id=lokasyon.id if lokasyon else None,
                custom={ag.GRUP: ozel},
            )
            if zimmet_yeri is not None:
                varlik.assigned_type = models.AssignedType.location
                varlik.assigned_location_id = zimmet_yeri.id
                varlik.last_checkout = simdi
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
            if zimmet_yeri is not None:
                db.add(models.ActivityLog(
                    action=models.ActivityAction.checkout, item_type="asset",
                    item_id=varlik.id, target_type="location",
                    target_id=zimmet_yeri.id,
                    note=f"{zimmet_yeri.name} üzerine zimmetlendi"))
        db.commit()
        print(f"\n\033[1;32m✓ {len(eklenecek)} ağ ürünü eklendi.\033[0m")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
