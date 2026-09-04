#!/usr/bin/env python3
"""IFS dökümünü envantere işler: seri no, donanım özellikleri ve zimmet.

İki IFS raporunu da okur (başlıktan anlar):

  * **Zimmet Edilen Demirbaş Listesi** (geniş biçim) — her satır bir cihaz:
    Cihaz Kodu · Seri Nesne Kodu · Kişi · Marka/Model · Şasi/Seri No ·
    İşlemci · Ram · Ekran Kartı · Hdd
  * **Seri Nesne Özellikleri** (uzun biçim) — her satır bir özellik:
    Nesne No · Ozellık Acıklaması · Deger Metnı · Bılgı

Eşleştirme sırası: Cihaz Kodu → Seri No → daha önce yazılmış IFS kodu.
Eşleşen cihazın BOŞ alanları doldurulur, dolu veriye dokunulmaz
(`--uzerine-yaz` bunu değiştirir). Kişi sütunu varsa cihaz o kişiye
zimmetlenir; cihaz başkasındaysa dokunulmaz, raporda gösterilir.

Kullanım:
    # Ne olacağını gör (hiçbir şey yazılmaz):
    ./.venv/bin/python scripts/ifs-aktar.py zimmet.xlsx --dry-run

    # Uygula: eksik künye + teknik özellikler + zimmetler
    ./.venv/bin/python scripts/ifs-aktar.py zimmet.xlsx

    # Envanterde olmayan IFS nesneleri için de kayıt aç
    ./.venv/bin/python scripts/ifs-aktar.py zimmet.xlsx --yeni-ekle

Seçenekler:
    --dry-run          Yazmadan raporla
    --yeni-ekle        Eşleşmeyen nesneler için yeni varlık aç
    --uzerine-yaz      Dolu alanları da IFS değeriyle değiştir
    --zimmet-yok       Kişi sütununu yok say (yalnız künye/özellik güncelle)
    --zimmet-degistir  Cihaz başkasındaysa zimmeti IFS'e göre değiştir
    --kisi-olustur     Personel kaydı yoksa aç (varsayılan: atla ve raporla)
    --tumu             Teknik verisi/seri no'su olmayan nesneleri de al
    --sinif METIN      Yalnızca bu teknik sınıf (uzun biçim raporunda)
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
from app.database import SessionLocal  # noqa: E402
from app.excel import sema  # noqa: E402
from app.excel.ice_aktar import _Onbellek as Onbellek  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.ortam_uyari import uyar  # noqa: E402

M, Y, S, N = "\033[36m", "\033[32m", "\033[33m", "\033[0m"

# IFS sütun sırası (rapor başlığı Türkçe karaktersiz geliyor)
SUTUN = {"nesne": 0, "aciklama": 1, "note": 2, "ait_site": 3, "site": 4,
         "malzeme": 5, "grup": 6, "tedarikci_no": 7, "tedarikci": 8,
         "pozisyon": 9, "tarih": 10, "maliyet": 11, "sinif_kodu": 12,
         "sinif": 13, "ozellik_kodu": 14, "ozellik": 15, "deger": 16,
         "bilgi": 17}


def _t(deger) -> str:
    return "" if deger is None else str(deger).strip()


def marka_ayikla(ham: str) -> str:
    """'M0098-EVEREST' → 'EVEREST'. Kodsuz gelirse olduğu gibi döner."""
    ham = ham.strip()
    m = re.fullmatch(r"[A-ZÇĞİÖŞÜ]\d{3,4}\s*-\s*(.+)", ham)
    return (m.group(1) if m else ham).strip()


def seri_ayikla(deger: str, bilgi: str) -> str:
    """Seri numarasını ayıklar: 'WB09071410 P/N: 59354223' → 'WB09071410'.

    IFS'te seri kimi zaman değer, kimi zaman bilgi sütununda; yanına parça
    numarası ya da açıklama yazılmış olabiliyor.
    """
    ham = (deger or bilgi or "").strip()
    if not ham:
        return ""
    ham = re.split(r"\s*(?:P/?N|PN|MODEL|MTM|MO)\s*[:.]", ham, maxsplit=1,
                   flags=re.I)[0]
    ham = re.sub(r"^SER[İI]\s*NO\s*[:.]?\s*", "", ham, flags=re.I)
    return ham.strip().strip("-–").strip()


def model_ayikla(deger: str, bilgi: str) -> tuple[str, str]:
    """Model adı ve tam metni: uzun IFS açıklamasından kısa model çıkarılır.

    'Z50-70 Model Name: 20354 MTM: 59432107 MO: YB04101586' → ('Z50-70', tamamı)
    Kısa ad model kaydının adı olur, tam metin özellik olarak saklanır.
    """
    tam = " ".join(x for x in (deger, bilgi) if x).strip()
    if not tam:
        return "", ""
    kisa = re.split(r"\s*(?:Model Name|MTM|MO|P/?N|Factory ID|Type)\s*[:.]",
                    tam, maxsplit=1)[0].strip(" -–")
    return (kisa or tam), tam


def _disk_serisi(bilgi: str) -> str:
    m = re.search(r"SER[İI]\s*NO\s*[:.]?\s*([A-Za-z0-9\-]+)", bilgi)
    return m.group(1) if m else ""


# IFS özelliği → (uygulama özellik grubu, alan adı) eşlemesi.
# Değer ve bilgi sütunları farklı alanlara gider: "16 GB" kapasite,
# "DDR4 SDRAM …" ise tam açıklamadır.
def ozellik_gruplari(oz: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    """IFS özelliklerini uygulamanın özellik gruplarına dağıtır."""
    gruplar: dict[str, dict[str, str]] = {}

    def yaz(grup: str, alan: str, deger: str) -> None:
        if deger:
            gruplar.setdefault(grup, {})[alan] = deger

    def al(ad: str) -> tuple[str, str]:
        return oz.get(ad, ("", ""))

    # Uzun biçimde tek özellik (değer + bilgi), geniş biçimde iki sütun
    d, b = al("İŞLEMCİ MARKA / MODEL")
    marka_d = al("İŞLEMCİ MARKASI")[0] or d
    model_d = al("İŞLEMCİ MODELİ")[0] or b or d
    yaz("İşlemci", "İşlemci Markası", marka_d)
    yaz("İşlemci", "İşlemci (Bütün)", model_d)

    d, b = al("RAM TİPİ")
    kapasite = al("RAM")[0] or d
    ram_tam = al("RAM TİPİ AÇIKLAMA")[0] or b
    yaz("Bellek", "Ram Kapasitesi", kapasite)
    yaz("Bellek", "Ram (Bütün)", " · ".join(x for x in (kapasite, ram_tam) if x))

    d, b = al("HDD BILGISI")
    hdd_kap = al("HDD")[0] or d
    hdd_tam = al("HDD MODELİ")[0] or b or d
    yaz("Depolama", "Harddisk Kapasitesi", hdd_kap)
    yaz("Depolama", "Harddisk (Bütün)", hdd_tam)
    yaz("Depolama", "Harddisk Serial", _disk_serisi(hdd_tam))

    d, b = al("KAPASITE")
    if d or b:
        gruplar.setdefault("Depolama", {}).setdefault(
            "Harddisk Kapasitesi", d or b)
        yaz("Depolama", "Kapasite", " · ".join(x for x in (d, b) if x))

    d, b = al("EKRAN KARTI")
    yaz("Anakart / Ekran Kartı", "Ekran Kartı Marka", d)
    yaz("Anakart / Ekran Kartı", "Ekran Kartı (Bütün)",
        al("EKRAN KARTI MODELİ")[0] or b or d)

    d, b = al("ANAKART")
    yaz("Anakart / Ekran Kartı", "Ana Kart", b or d)

    d, b = al("EKRAN BOYUTU")
    # Nötr ad: kayıt dizüstü de olabilir monitör de
    yaz("Ekran", "Ekran Boyutu", d or b)

    sasi, seri_metin = al("ŞASİ NO/SERİ NO")
    secilen = seri_ayikla(sasi, seri_metin)
    for ham in (sasi, seri_metin):
        if ham and ham != secilen:
            yaz("Diğer", "IFS Şasi / Seri Notu", ham)

    kisa, tam = model_ayikla(*al("MODEL"))
    if tam and tam != kisa:
        yaz("Diğer", "IFS Model Bilgisi", tam)

    for ifs_ad, alan in (("PLAKA NO", "Plaka No"), ("MOTOR NO", "Motor No"),
                         ("KULLANIM DURUMU", "IFS Kullanım Durumu"),
                         ("ZİMMETLENEN PERSONEL", "IFS Zimmetli Personel"),
                         ("KİRALANAN FİRMA", "Kiralanan Firma")):
        d, b = al(ifs_ad)
        yaz("Diğer", alan, b or d)
    return gruplar


# Geniş biçimdeki (zimmet listesi) sütun adları → iç alan adları
_GENIS_ESLEME = {
    "cihaz kodu": "CIHAZ KODU",
    "marka": "MARKA",
    "model": "MODEL",
    "islemci marka": "İŞLEMCİ MARKASI",
    "islemci model": "İŞLEMCİ MODELİ",
    "ram": "RAM",
    "ram tipi": "RAM TİPİ AÇIKLAMA",
    "ekran karti": "EKRAN KARTI",
    "ekran karti modeli": "EKRAN KARTI MODELİ",
    "hdd": "HDD",
    "hdd modeli": "HDD MODELİ",
}


def genis_oku(basliklar: list[str], satirlar) -> list[dict]:
    """Zimmet listesini (her satır bir cihaz) ortak kayıt biçimine çevirir."""
    yer = {_sadelestir(b): i for i, b in enumerate(basliklar)}

    def hucre(r, ad: str) -> str:
        i = yer.get(ad)
        return _t(r[i]) if i is not None and i < len(r) else ""

    kayitlar = []
    for r in satirlar:
        nesne = hucre(r, "seri nesne kodu")
        kod = hucre(r, "cihaz kodu")
        if not nesne and not kod:
            continue
        # Şasi no genelde gerçek seri numarasıdır; "Seri No" sütununda
        # çoğu zaman MTM/MO gibi ek kodlar bulunur (bkz. seri_ayikla).
        sasi, seri = hucre(r, "sasi no"), hucre(r, "seri no")
        oz: dict[str, tuple[str, str]] = {}
        for sutun, ad in _GENIS_ESLEME.items():
            deger = hucre(r, sutun)
            if deger:
                oz[ad] = (deger, "")
        oz["ŞASİ NO/SERİ NO"] = (sasi, seri)
        kayitlar.append({
            "nesne_no": nesne,
            "aciklama": hucre(r, "seri nesne adi"),
            "note": "",
            "site": hucre(r, "mevcut proje"),
            "ilk_site": hucre(r, "ilk proje"),
            "malzeme": "", "tedarikci": "", "pozisyon": "",
            "tarih": None, "maliyet": None, "sinif": "",
            "kisi": hucre(r, "kisi"),
            "oz": oz,
        })
    return kayitlar


def dosya_oku(yol: Path) -> tuple[list[dict], str]:
    """Raporu okur; (kayıtlar, biçim adı) döner. Biçim başlıktan anlaşılır."""
    import openpyxl

    ws = openpyxl.load_workbook(yol, data_only=True, read_only=True).worksheets[0]
    satirlar = ws.iter_rows(values_only=True)
    basliklar = [_t(c) for c in (next(satirlar, None) or ())]
    sade = {_sadelestir(b) for b in basliklar}
    if "cihaz kodu" in sade and "seri nesne kodu" in sade:
        return genis_oku(basliklar, satirlar), "zimmet listesi"
    return uzun_oku(satirlar), "seri nesne özellikleri"


def uzun_oku(satirlar) -> list[dict]:
    """Uzun biçimli IFS raporunu nesne bazında birleştirir."""
    kayitlar: dict[str, dict] = {}
    for r in satirlar:
        no = _t(r[SUTUN["nesne"]])
        if not no:
            continue
        k = kayitlar.get(no)
        if k is None:
            k = kayitlar[no] = {
                "nesne_no": no,
                "aciklama": _t(r[SUTUN["aciklama"]]),
                "note": _t(r[SUTUN["note"]]),
                "site": _t(r[SUTUN["site"]]),
                "malzeme": _t(r[SUTUN["malzeme"]]),
                "tedarikci": _t(r[SUTUN["tedarikci"]]),
                "pozisyon": _t(r[SUTUN["pozisyon"]]),
                "tarih": r[SUTUN["tarih"]],
                "maliyet": r[SUTUN["maliyet"]],
                "sinif": _t(r[SUTUN["sinif"]]),
                "kisi": "",
                "oz": {},
            }
        ad = _t(r[SUTUN["ozellik"]])
        deger, bilgi = _t(r[SUTUN["deger"]]), _t(r[SUTUN["bilgi"]])
        if ad and (deger or bilgi):
            k["oz"][ad] = (deger, bilgi)
    return list(kayitlar.values())


def ilginc_mi(k: dict) -> bool:
    """Teknik veri taşıyan nesne mi? (mobilya/konteyner elenir)"""
    return bool(k["oz"])


def _tarih(deger) -> dt.date | None:
    if isinstance(deger, dt.datetime):
        return deger.date()
    if isinstance(deger, dt.date):
        return deger
    metin = _t(deger)
    for bicim in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(metin, bicim).date()
        except ValueError:
            continue
    return None


def _para(deger) -> float | None:
    if isinstance(deger, (int, float)):
        return float(deger) or None
    metin = _t(deger).replace(".", "").replace(",", ".")
    try:
        return float(metin) or None
    except ValueError:
        return None


def _seri_anahtar(seri: str) -> str:
    """Seri karşılaştırması için sadeleştirme: boşluk/tire yok, büyük harf."""
    return re.sub(r"[^0-9A-Z]", "", (seri or "").upper())


def eslestir(kayit: dict, etiketler: dict[str, models.Asset],
             seriler: dict[str, models.Asset],
             ifs_kodlari: dict[str, models.Asset]) -> tuple[models.Asset | None, str]:
    """Envanterdeki cihazı bulur; hangi ölçütle bulunduğunu da döner."""
    kod = kayit["oz"].get("CIHAZ KODU", ("", ""))[0]
    if kod and _sadelestir(kod) in etiketler:
        return etiketler[_sadelestir(kod)], "cihaz kodu"
    seri = seri_ayikla(*kayit["oz"].get("ŞASİ NO/SERİ NO", ("", "")))
    if seri and _seri_anahtar(seri) in seriler:
        return seriler[_seri_anahtar(seri)], "seri no"
    if kayit["nesne_no"] in ifs_kodlari:
        return ifs_kodlari[kayit["nesne_no"]], "IFS no"
    return None, ""


def degisiklikler(varlik: models.Asset, kayit: dict, onbellek: Onbellek,
                  *, uzerine_yaz: bool) -> dict[str, tuple]:
    """Varlığa uygulanacak değişiklikleri (alan → eski/yeni) hesaplar."""
    yeni: dict[str, tuple] = {}

    def ata(alan: str, deger) -> None:
        if deger in (None, ""):
            return
        mevcut = getattr(varlik, alan, None)
        if mevcut in (None, "") or (uzerine_yaz and mevcut != deger):
            if mevcut != deger:
                yeni[alan] = (mevcut, deger)

    ata("serial", seri_ayikla(*kayit["oz"].get("ŞASİ NO/SERİ NO", ("", ""))))
    ata("muhasebe_kodu", kayit["nesne_no"])
    ata("purchase_date", _tarih(kayit["tarih"]))
    ata("purchase_cost", _para(kayit["maliyet"]))

    marka = marka_ayikla(kayit["oz"].get("MARKA", ("", ""))[0])
    model_adi = model_ayikla(*kayit["oz"].get("MODEL", ("", "")))[0]
    if kayit["tedarikci"]:
        tedarikci = onbellek.al(models.Supplier, kayit["tedarikci"])
        if tedarikci is not None:
            ata("supplier_id", tedarikci.id)
    if kayit["site"]:
        lok = onbellek.proje_lokasyonu(kayit["site"])
        if lok is not None:
            ata("location_id", lok.id)
    return yeni, marka, model_adi


def ozellik_birlestir(varlik: models.Asset, gruplar: dict[str, dict[str, str]],
                      *, uzerine_yaz: bool) -> int:
    """Teknik özellikleri custom JSON'a işler; kaç alan yazıldığını döner."""
    ozel = {g: dict(v) for g, v in (varlik.custom or {}).items()
            if isinstance(v, dict)}
    sayac = 0
    for grup, alanlar in gruplar.items():
        hedef = dict(ozel.get(grup) or {})
        for alan, deger in alanlar.items():
            if deger and (uzerine_yaz or not hedef.get(alan)):
                if hedef.get(alan) != deger:
                    hedef[alan] = deger
                    sayac += 1
        if hedef:
            ozel[grup] = hedef
    if sayac:
        varlik.custom = ozel                  # JSON sütunu yeni sözlük ister
    return sayac


def zimmet_karari(varlik: models.Asset, kisi: models.User | None,
                  *, degistir: bool) -> str:
    """Zimmet ne yapılmalı? 'kisi-yok' | 'ayni' | 'baskasinda' | 'yaz'

    Cihaz başkasının üzerindeyse sessizce el değiştirmez: IFS dökümü ile
    envanter çelişiyorsa bunu insanın görmesi gerekir.
    """
    if kisi is None:
        return "kisi-yok"
    if varlik.assigned_user_id == kisi.id:
        return "ayni"
    if varlik.assigned_type is not None and not degistir:
        return "baskasinda"
    return "yaz"


def kategori_adi(kayit: dict) -> str:
    """IFS açıklamasından kategori adı: sistem ürünüyse o türün adı."""
    tur = ag.tur_bul(kayit["aciklama"])
    if tur:
        return ag.kategori_adi(tur)
    return sema.cihaz_tipi_normalle(kayit["aciklama"])


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dosya", help="IFS raporu (.xlsx)")
    ap.add_argument("--dry-run", action="store_true", help="yazmadan raporla")
    ap.add_argument("--yeni-ekle", dest="yeni_ekle", action="store_true",
                    help="eşleşmeyen IFS nesneleri için varlık aç")
    ap.add_argument("--uzerine-yaz", dest="uzerine_yaz", action="store_true",
                    help="dolu alanları da IFS değeriyle değiştir")
    ap.add_argument("--zimmet-yok", dest="zimmet_yok", action="store_true",
                    help="kişi sütununu yok say (yalnız künye/özellik)")
    ap.add_argument("--zimmet-degistir", dest="zimmet_degistir",
                    action="store_true",
                    help="cihaz başkasındaysa zimmeti IFS'e göre değiştir")
    ap.add_argument("--kisi-olustur", dest="kisi_olustur", action="store_true",
                    help="personel kaydı yoksa aç (varsayılan: atla, raporla)")
    ap.add_argument("--tumu", action="store_true",
                    help="teknik verisi olmayan nesneleri de al")
    ap.add_argument("--sinif", help="yalnızca bu teknik sınıf (örn. Bilgisayar)")
    args = ap.parse_args()

    yol = Path(args.dosya)
    if not yol.exists():
        print(f"{S}Dosya bulunamadı: {yol}{N}", file=sys.stderr)
        return 1

    kayitlar, bicim = dosya_oku(yol)
    toplam = len(kayitlar)
    if not args.tumu:
        kayitlar = [k for k in kayitlar if ilginc_mi(k)]
    if args.sinif:
        aranan = _sadelestir(args.sinif)
        kayitlar = [k for k in kayitlar if aranan in _sadelestir(k["sinif"])]

    print(f"\n{M}→ IFS {bicim}: {toplam} nesne, işlenecek {len(kayitlar)}{N}")
    if not kayitlar:
        print(f"{S}Ölçüte uyan nesne yok.{N}")
        return 0

    uyar()
    db = SessionLocal()
    try:
        onbellek = Onbellek(db)
        varliklar = db.scalars(select(models.Asset)).all()
        etiketler = {_sadelestir(a.asset_tag): a for a in varliklar if a.asset_tag}
        seriler = {_seri_anahtar(a.serial): a for a in varliklar if a.serial}
        ifs_kodlari = {a.muhasebe_kodu: a for a in varliklar if a.muhasebe_kodu}

        # Zimmet için ad dizini (Türkçe karakter duyarsız, tam ad)
        kisi_dizini: dict[str, models.User] = {}
        for k in db.scalars(select(models.User)).all():
            ad = _sadelestir(" ".join(filter(None, [k.first_name, k.last_name])))
            if ad:
                kisi_dizini.setdefault(ad, k)
        zimmetlenen, zimmet_ayni = [], 0
        zimmet_baskasinda, kisi_bulunamayan = [], []

        guncellenen, dokunulmayan, eslesmeyen = [], 0, []
        alan_sayaci: dict[str, int] = {}
        ozellik_toplam = 0

        for k in kayitlar:
            varlik, olcut = eslestir(k, etiketler, seriler, ifs_kodlari)
            if varlik is None:
                eslesmeyen.append(k)
                continue
            yeni, marka, model_adi = degisiklikler(
                varlik, k, onbellek, uzerine_yaz=args.uzerine_yaz)
            oz_sayi = ozellik_birlestir(varlik, ozellik_gruplari(k["oz"]),
                                        uzerine_yaz=args.uzerine_yaz)
            # Marka/model yalnızca cihazın modeli hiç yoksa kurulur
            if (marka or model_adi) and (varlik.model_id is None or args.uzerine_yaz):
                uretici = onbellek.al(models.Manufacturer, marka)
                kategori = onbellek.al(models.Category, kategori_adi(k))
                mdl = onbellek.al(
                    models.AssetModel, model_adi or k["aciklama"] or marka,
                    manufacturer_id=uretici.id if uretici else None,
                    category_id=kategori.id if kategori else None)
                if mdl is not None and varlik.model_id != mdl.id:
                    yeni["model_id"] = (varlik.model_id, mdl.id)

            # --- Zimmet: kişi sütunu varsa cihaz sahibine bağlanır ---
            zimmet_notu = ""
            kisi_adi = k.get("kisi", "")
            if kisi_adi and not args.zimmet_yok:
                kisi = kisi_dizini.get(_sadelestir(kisi_adi))
                if kisi is None and args.kisi_olustur:
                    parca = kisi_adi.split()
                    kisi = models.User(first_name=parca[0],
                                       last_name=" ".join(parca[1:]) or None)
                    db.add(kisi)
                    db.flush()
                    kisi_dizini[_sadelestir(kisi_adi)] = kisi
                karar = zimmet_karari(varlik, kisi,
                                      degistir=args.zimmet_degistir)
                if karar == "kisi-yok":
                    kisi_bulunamayan.append((varlik.asset_tag, kisi_adi))
                elif karar == "ayni":
                    zimmet_ayni += 1
                elif karar == "baskasinda":
                    zimmet_baskasinda.append((varlik.asset_tag, kisi_adi))
                else:
                    zimmet_notu = kisi_adi
                    zimmetlenen.append((varlik.asset_tag, kisi_adi))
                    if not args.dry_run:
                        varlik.assigned_type = models.AssignedType.user
                        varlik.assigned_user_id = kisi.id
                        varlik.assigned_location_id = None
                        varlik.assigned_asset_id = None
                        varlik.last_checkout = dt.datetime.now(dt.timezone.utc)
                        db.add(models.ActivityLog(
                            action=models.ActivityAction.checkout,
                            item_type="asset", item_id=varlik.id,
                            target_type="user", target_id=kisi.id,
                            note=f"{kisi_adi} üzerine zimmetlendi (IFS dökümü)",
                            actor="IFS aktarım"))

            if not yeni and not oz_sayi and not zimmet_notu:
                dokunulmayan += 1
                continue
            for alan in yeni:
                alan_sayaci[alan] = alan_sayaci.get(alan, 0) + 1
            ozellik_toplam += oz_sayi
            guncellenen.append((varlik, k, yeni, oz_sayi, olcut))
            if not args.dry_run:
                for alan, (_eski, yeni_deger) in yeni.items():
                    setattr(varlik, alan, yeni_deger)
                db.add(models.ActivityLog(
                    action=models.ActivityAction.update, item_type="asset",
                    item_id=varlik.id, note="IFS dökümünden güncellendi",
                    changes={a: {"eski": str(e), "yeni": str(y)}
                             for a, (e, y) in yeni.items()} or None,
                    actor="IFS aktarım"))

        if not args.zimmet_yok:
            print(f"  Zimmetlenecek          : {len(zimmetlenen)}"
                  if args.dry_run else
                  f"  Zimmetlenen            : {len(zimmetlenen)}")
            print(f"  Zimmeti zaten doğru    : {zimmet_ayni}")
            if zimmet_baskasinda:
                print(f"  {S}Başkasında (atlandı)   : {len(zimmet_baskasinda)}{N}")
            if kisi_bulunamayan:
                print(f"  {S}Personel kaydı yok     : {len(kisi_bulunamayan)}{N}")
        print(f"  Eşleşen ve güncellenen : {len(guncellenen)}")
        print(f"  Eşleşen, değişiklik yok: {dokunulmayan}")
        print(f"  Envanterde bulunamayan : {len(eslesmeyen)}")
        if alan_sayaci:
            print(f"\n{M}Doldurulan alanlar{N}")
            for alan, n in sorted(alan_sayaci.items(), key=lambda x: -x[1]):
                print(f"    {alan:<16} {n}")
            print(f"    {'teknik özellik':<16} {ozellik_toplam}")

        print(f"\n{M}Örnek güncellemeler{N}")
        for varlik, k, yeni, oz_sayi, olcut in guncellenen[:15]:
            alanlar = ", ".join(yeni) or "—"
            print(f"  ~ {varlik.asset_tag:<12} ({olcut:<10}) {alanlar}"
                  + (f" +{oz_sayi} özellik" if oz_sayi else ""))
        if zimmet_baskasinda:
            print(f"\n{S}Cihaz başka kişide — dokunulmadı "
                  f"(--zimmet-degistir ile değişir){N}")
            for etiket, ad in zimmet_baskasinda[:10]:
                print(f"  ! {etiket:<10} IFS'e göre: {ad}")
        if kisi_bulunamayan:
            print(f"\n{S}Personel kaydı bulunamayan kişiler "
                  f"(--kisi-olustur ile açılır){N}")
            for etiket, ad in kisi_bulunamayan[:10]:
                print(f"  ? {etiket:<10} {ad}")
        if eslesmeyen:
            print(f"\n{S}Envanterde bulunamayan ilk 15 nesne{N}")
            for k in eslesmeyen[:15]:
                kod = k["oz"].get("CIHAZ KODU", ("", ""))[0]
                seri = seri_ayikla(*k["oz"].get("ŞASİ NO/SERİ NO", ("", "")))
                print(f"  ? {k['nesne_no']:<28} {k['aciklama'][:24]:<24} "
                      f"kod={kod or '—':<6} seri={seri or '—'}")

        yeni_varlik = 0
        if args.yeni_ekle and eslesmeyen and not args.dry_run:
            kullanilan = {a.asset_tag for a in varliklar}
            for k in eslesmeyen:
                kod = k["oz"].get("CIHAZ KODU", ("", ""))[0]
                seri = seri_ayikla(*k["oz"].get("ŞASİ NO/SERİ NO", ("", "")))
                etiket = kod or seri or k["nesne_no"]
                if etiket in kullanilan:
                    etiket = k["nesne_no"]
                kullanilan.add(etiket)
                marka = marka_ayikla(k["oz"].get("MARKA", ("", ""))[0])
                model_adi = model_ayikla(*k["oz"].get("MODEL", ("", "")))[0]
                uretici = onbellek.al(models.Manufacturer, marka)
                kategori = onbellek.al(models.Category, kategori_adi(k))
                mdl = onbellek.al(
                    models.AssetModel, model_adi or k["aciklama"] or marka,
                    manufacturer_id=uretici.id if uretici else None,
                    category_id=kategori.id if kategori else None)
                lok = onbellek.proje_lokasyonu(k["site"]) if k["site"] else None
                tedarikci = (onbellek.al(models.Supplier, k["tedarikci"])
                             if k["tedarikci"] else None)
                varlik = models.Asset(
                    asset_tag=etiket, name=k["aciklama"] or None,
                    serial=seri or None, muhasebe_kodu=k["nesne_no"],
                    model_id=mdl.id if mdl else None,
                    location_id=lok.id if lok else None,
                    supplier_id=tedarikci.id if tedarikci else None,
                    purchase_date=_tarih(k["tarih"]),
                    purchase_cost=_para(k["maliyet"]),
                    notes=k["note"] or None)
                ozellik_birlestir(varlik, ozellik_gruplari(k["oz"]),
                                  uzerine_yaz=True)
                db.add(varlik)
                db.flush()
                db.add(models.ActivityLog(
                    action=models.ActivityAction.create, item_type="asset",
                    item_id=varlik.id, note="IFS dökümünden eklendi",
                    actor="IFS aktarım"))
                yeni_varlik += 1
        elif args.yeni_ekle and eslesmeyen:
            yeni_varlik = len(eslesmeyen)      # kuru çalıştırmada sayısı

        if args.dry_run:
            db.rollback()
            print(f"\n{S}⚠ KURU ÇALIŞTIRMA — hiçbir değişiklik yapılmadı.{N}")
            if not args.yeni_ekle and eslesmeyen:
                print(f"  Bulunamayanları da eklemek için --yeni-ekle verin.")
            return 0

        db.commit()
        print(f"\n{Y}✓ {len(guncellenen)} cihaz güncellendi"
              + (f", {len(zimmetlenen)} zimmet yazıldı" if zimmetlenen else "")
              + (f", {yeni_varlik} yeni varlık eklendi" if yeni_varlik else "")
              + f".{N}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
