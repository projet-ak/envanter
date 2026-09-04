#!/usr/bin/env python3
"""Ağ / sistem ürünlerini metin tablosundan içe aktarır.

Excel'den kopyalanan tablo doğrudan verilebilir (.xlsx dosyası da).
Sütun ayracı sekme, "|" ya da 2+ boşluk olabilir; SSH'ta yapıştırırken
sekmeler bozulduğu için "|" tercih edilir. Başlık satırı varsa sütunlar
ADINDAN tanınır (sıra önemsiz):

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

Telefon rehberi (Excel dosyası da doğrudan verilebilir):

    ./.venv/bin/python scripts/ag-urun-aktar.py rehber.xlsx --tur ip_telefon \\
        --marka Karel --lokasyon "ERN HOLDİNG İSTANBUL MERKEZ OFİSİ" \\
        --proje-kodu Y005 --zimmet "HOLDİNG BİNASI" --etiket-onek "TEL-Y005-" \\
        --kisiye-zimmetle --dahili-yaz

Seçenekler:
    --tur           sfp | switch | access_point | ip_telefon | santral …
    --lokasyon      Ürünlerin bulunduğu yer (yoksa oluşturulur)
    --proje-kodu    Lokasyonu proje koduyla eşler (mükerrer şantiye açılmasın)
    --zimmet        Kişi yerine bir yere zimmetle (örn. "HOLDİNG BİNASI");
                    kayıt yoksa lokasyonun altında açılır
    --marka         Marka sütunu yoksa hepsine bu markayı yazar
    --marka-esle    Marka yazımını düzeltir (örn. "SİMENS=Siemens")
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
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import ag, models  # noqa: E402
from app.routers.ag_urunleri import mac_duzenle  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402


def excel_satirlari(yol: Path) -> list[list[str]]:
    """xlsx dosyasını satır listesine çevirir (boş hücreler korunur)."""
    import openpyxl

    ws = openpyxl.load_workbook(yol, data_only=True).worksheets[0]
    satirlar = []
    for ham in ws.iter_rows(values_only=True):
        hucreler = ["" if h is None else str(h).strip() for h in ham]
        if sum(1 for h in hucreler if h) >= 2:
            satirlar.append(hucreler)
    return satirlar


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
        elif "|" in ham:
            # SSH ile yapıştırmak için: sekme terminalde bozulur, "|" bozulmaz
            parcalar = [p.strip() for p in ham.split("|")]
        else:
            parcalar = [p.strip() for p in re.split(r" {2,}", ham.strip())]
        if sum(1 for p in parcalar if p) >= 2:
            satirlar.append(parcalar)
    return satirlar


# Başlık adı -> iç alan. Sıra önemli: "seri no" içinde "no" da geçtiği için
# daha belirgin anahtarlar önce denenir.
_BASLIK_ESLEME = [
    (("mac",), "mac"),
    (("ip",), "ip"),
    (("seri",), "seri"),
    (("marka", "uretici"), "marka"),
    # "TEL. MODEL" model sütunudur; "TEL. NO" dahili numaradır — model önce
    # denenir, yoksa "tel" geçen her başlık dahili sanılırdı.
    (("model", "parca no", "tip"), "model"),
    (("dahili", "tel no", "tel. no", "telefon", "numara"), "dahili"),
    (("soyisim", "soyad"), "soyad"),
    (("isim", "ad soyad", "kullanan", "kisi", "personel"), "ad"),
    (("kat",), "kat"),
    (("lokasyon", "konum", "yer", "nokta", "bolge", "oda"), "konum"),
    (("aciklama", "tanim", "not"), "tanim"),
]

# Kat kısaltmaları: aynı bina için AP listesiyle aynı yazım kullanılsın
_KAT_KISALTMA = {
    "mk": "MAKAM KATI", "zk": "ZEMİN KAT", "bk": "BODRUM KAT",
    "gk": "GİRİŞ KATI", "ck": "ÇATI KATI",
}


def kat_ac(ham: str) -> str:
    """'MK' → 'MAKAM KATI'. Tanınmayan değer olduğu gibi kalır."""
    return _KAT_KISALTMA.get(_sadelestir(ham), ham.strip())


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
    # Başlık satırında hücrelerin ÇOĞU tanınır; veri satırında bir iki hücre
    # tesadüfen eşleşebilir ("BODRUM KAT" → kat), bu yüzden oran da aranır.
    dolu = sum(1 for h in parcalar if h.strip())
    if len(harita) >= 3 and len(harita) >= 0.6 * dolu:
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


def yeni_marka_uyarisi(db, markalar: set[str]) -> list[tuple[str, str | None]]:
    """Listede geçen ama kayıtlı olmayan markalar ve benzerleri.

    "SİMENS" ile "Siemens" ayrı iki marka açar; içe aktarmadan ÖNCE
    söylenmezse mükerrer marka kaçınılmaz olur.
    """
    import difflib

    mevcut = {_sadelestir(m.name): m.name
              for m in db.scalars(select(models.Manufacturer)).all() if m.name}
    uyari = []
    for marka in sorted(markalar):
        sade = _sadelestir(marka)
        if not sade or sade in mevcut:
            continue
        yakin = difflib.get_close_matches(sade, list(mevcut), n=1, cutoff=0.75)
        uyari.append((marka, mevcut[yakin[0]] if yakin else None))
    return uyari


class _Satir(NamedTuple):
    """İçe aktarılacak tek ürün (rapor ve yazma adımı aynı yapıyı kullanır)."""

    etiket: str
    marka: str
    model: str
    seri: str
    mac: str | None
    ip: str
    dahili: str
    kisi: object | None          # eşleşen personel kaydı (varsa)
    ozel: dict


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
    ap.add_argument("--marka", help="Marka sütunu yoksa hepsine bu marka yazılır")
    ap.add_argument("--marka-esle", dest="marka_esle", action="append",
                    metavar="LISTEDEKI=DOGRUSU",
                    help="listedeki marka yazımını düzeltir "
                         "(örn. --marka-esle 'SİMENS=Siemens'), tekrarlanabilir")
    ap.add_argument("--kisiye-zimmetle", dest="kisiye_zimmetle",
                    action="store_true",
                    help="İSİM/SOYİSİM sütunundaki personele zimmetle; "
                         "kişi bulunamazsa --zimmet yerine düşer")
    ap.add_argument("--dahili-yaz", dest="dahili_yaz", action="store_true",
                    help="Eşleşen personelin künyesine dahili numarayı yaz")
    ap.add_argument("--nereden", help="Geldiği lokasyon (geçmişe not düşülür)")
    ap.add_argument("--dry-run", action="store_true", help="Yazmadan raporla")
    args = ap.parse_args()

    if args.dosya != "-" and Path(args.dosya).suffix.lower() in (".xlsx", ".xlsm"):
        ham_satirlar = excel_satirlari(Path(args.dosya))
    else:
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
        # Dahili numara da tekildir: aynı numara iki telefona verilemez
        mevcut_dahili = {t for t in db.scalars(select(models.Asset.telefon_no)).all() if t}

        # Marka yazım düzeltmeleri: "SİMENS=Siemens" → mükerrer marka açılmaz
        marka_haritasi = {}
        for cift in args.marka_esle or []:
            if "=" not in cift:
                print(f"\n{S}--marka-esle 'LISTEDEKI=DOGRUSU' biçiminde "
                      f"olmalı: {cift}{N}")
                return 1
            ham, dogru = cift.split("=", 1)
            marka_haritasi[_sadelestir(ham)] = dogru.strip()

        sira = _sonraki_sira(mevcut_etiket, args.etiket_onek)
        # Kişi eşleştirmesi için ad dizini (Türkçe karakter duyarsız)
        kisi_dizini: dict[str, list] = {}
        if args.kisiye_zimmetle or args.dahili_yaz:
            for k in db.scalars(select(models.User)).all():
                ad = _sadelestir(" ".join(filter(None, [k.first_name, k.last_name])))
                if ad:
                    kisi_dizini.setdefault(ad, []).append(k)

        eklenecek, atlanan, biçimsiz_mac = [], [], []
        for parcalar in satirlar:
            marka = _hucre(parcalar, harita, "marka") or (args.marka or "")
            marka = marka_haritasi.get(_sadelestir(marka), marka)
            model = _hucre(parcalar, harita, "model")
            seri = _hucre(parcalar, harita, "seri")
            tanim = _hucre(parcalar, harita, "tanim")
            mac = mac_duzenle(_hucre(parcalar, harita, "mac"))
            ip = _hucre(parcalar, harita, "ip")
            dahili = _hucre(parcalar, harita, "dahili")
            kat = kat_ac(_hucre(parcalar, harita, "kat"))
            konum = _hucre(parcalar, harita, "konum")
            kisi_adi = " ".join(filter(None, [_hucre(parcalar, harita, "ad"),
                                              _hucre(parcalar, harita, "soyad")]))
            kisi_adi = " ".join(kisi_adi.split())
            kimlik = dahili or konum or kisi_adi or seri or mac or marka

            # Kişi eşleşmesi: tam ad birebir tutmalı; birden çok kişi varsa
            # hangisi olduğu belirsizdir, yere zimmetlenir.
            adaylar = kisi_dizini.get(_sadelestir(kisi_adi), []) if kisi_adi else []
            kisi = adaylar[0] if len(adaylar) == 1 else None

            if dahili and dahili in mevcut_dahili:
                atlanan.append((kimlik, f"dahili {dahili} zaten kayıtlı"))
                continue
            if mac and mac in mevcut_mac:
                atlanan.append((kimlik, f"MAC {mac} zaten kayıtlı"))
                continue
            if seri and seri in mevcut_seriler:
                atlanan.append((kimlik, "seri no zaten kayıtlı"))
                continue

            # Cihaz no: seri no varsa o, yoksa üretilen sıra no, o da yoksa MAC
            if seri:
                etiket = seri
            elif args.etiket_onek and dahili:
                # Etikette boşluk/noktalama olmasın: "0216 266 64 96" → 02162666496
                etiket = args.etiket_onek + re.sub(r"[^0-9A-Za-z]", "", dahili)
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
            if kisi_adi:
                ozel["Kullanan"] = kisi_adi
            if mac and not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
                biçimsiz_mac.append((kimlik, mac))
            eklenecek.append(_Satir(etiket, marka, model, seri, mac, ip,
                                    dahili, kisi, ozel))
            mevcut_etiket.add(etiket)
            if mac:
                mevcut_mac.add(mac)
            if dahili:
                mevcut_dahili.add(dahili)

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
        for r in eklenecek[:50]:
            ek = ", ".join(f"{k}={v}" for k, v in r.ozel.items() if k != "Parça No")
            kime = f"→ {r.kisi.full_name}" if r.kisi else ""
            print(f"  + {r.etiket:<16} {r.marka:<11} {r.model:<8} "
                  f"{r.dahili:<7} {r.mac or '':<15} {ek} {kime}")
        for kimlik, sebep in atlanan[:20]:
            print(f"  - {kimlik:<24} ({sebep})")
        yeni_markalar = yeni_marka_uyarisi(db, {r.marka for r in eklenecek if r.marka})
        if yeni_markalar:
            print(f"\n\033[33m⚠ Kayıtlı olmayan {len(yeni_markalar)} marka "
                  f"açılacak:\033[0m")
            for marka, benzer in yeni_markalar:
                ek = f"  ← mevcut '{benzer}' ile aynı olabilir!" if benzer else ""
                print(f"    {marka}{ek}")
        if biçimsiz_mac:
            # 12 haneli onaltılık olmayan değerler olduğu gibi saklanır;
            # çoğu zaman listede yazım hatasıdır (harf O yerine sıfır gibi).
            print(f"\n\033[33m⚠ MAC biçimi tanınmayan {len(biçimsiz_mac)} kayıt "
                  f"(olduğu gibi yazılacak, listeyi kontrol edin):\033[0m")
            for kimlik, mac in biçimsiz_mac[:10]:
                print(f"    {kimlik:<24} {mac}")

        if args.dry_run:
            print("\n\033[33m⚠ KURU ÇALIŞTIRMA — hiçbir değişiklik yapılmadı.\033[0m")
            db.rollback()
            return 0
        if not eklenecek:
            print("\n\033[32m✓ Eklenecek yeni ürün yok.\033[0m")
            return 0

        simdi = dt.datetime.now(dt.timezone.utc)
        for r in eklenecek:
            mdl = _model_bul(db, args.tur, r.marka, r.model)
            # Ad künyede görünür: "HPE Aruba AP-615-RW — Sağ Koridor 1"
            ad = " ".join(filter(None, [r.marka, r.model])) or None
            # Ad künyede görünür: telefonda kullanan kişi, AP'de montaj yeri
            yer = r.ozel.get("Konum") or r.ozel.get("Kullanan") or (
                r.kisi.full_name if r.kisi else None)
            if ad and yer:
                ad = f"{ad} — {yer}"
            varlik = models.Asset(
                asset_tag=r.etiket,
                name=ad,
                serial=r.seri or None,
                mac_address=r.mac,
                ip_address=r.ip or None,
                telefon_no=r.dahili or None,
                model_id=mdl.id,
                location_id=lokasyon.id if lokasyon else None,
                custom={ag.GRUP: r.ozel},
            )
            # Zimmet: eşleşen kişi varsa ona, yoksa yere (bina)
            if r.kisi is not None:
                varlik.assigned_type = models.AssignedType.user
                varlik.assigned_user_id = r.kisi.id
                varlik.last_checkout = simdi
            elif zimmet_yeri is not None:
                varlik.assigned_type = models.AssignedType.location
                varlik.assigned_location_id = zimmet_yeri.id
                varlik.last_checkout = simdi
            if args.dahili_yaz and r.kisi is not None and r.dahili:
                r.kisi.dahili = r.dahili
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
            if r.kisi is not None:
                db.add(models.ActivityLog(
                    action=models.ActivityAction.checkout, item_type="asset",
                    item_id=varlik.id, target_type="user", target_id=r.kisi.id,
                    note=f"{r.kisi.full_name} üzerine zimmetlendi"))
            elif zimmet_yeri is not None:
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
