"""Cihazları proje koduna (şantiyeye) göre ayrı lokasyonlara dağıtır.

Excel içe aktarımının ilk sürümü tüm cihazları tek bir genel "ŞANTİYE"
lokasyonuna koyuyordu; şantiye ayrımı ise cihazın özelliklerindeki
"Kullanılan Birim" (U023, U026…) alanında duruyordu. Buradaki `ayir()` o
bilgiyi kullanarak her proje için ayrı lokasyon oluşturur ve cihazları taşır.

Yeni içe aktarımlarda bu ayrım zaten `app.excel.ice_aktar` içinde yapılır;
`ayir()` geçmiş veriyi düzeltmek içindir ve tekrar çalıştırılabilir
(idempotent) — taşınacak cihaz kalmadığında hiçbir şey değiştirmez.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.excel import sema


def birim(varlik: models.Asset) -> str | None:
    """Cihazın özelliklerinde saklanan 'Kullanılan Birim' değerini bulur."""
    ozel = varlik.custom or {}
    for grup in ozel.values():
        if isinstance(grup, dict):
            for anahtar in ("Kullanılan Birim", "Kullanilan Birim"):
                if grup.get(anahtar):
                    return str(grup[anahtar])
    return None


def _projeye_ozel(ad: str | None, kod: str) -> bool:
    """Lokasyon adı zaten o projeyi içeriyor mu?

    Genel "ŞANTİYE" lokasyonu eski içe aktarımdan bir proje kodu taşıyor
    olabilir; hedef sayılması için adının o projeye özel olması gerekir.
    """
    return bool(ad) and sema.santiye_adi(ad, kod) == ad


def ayir(db: Session, *, kaynak: str | None = None, uygula: bool = True) -> dict:
    """Cihazları proje kodlarına göre şantiye lokasyonlarına dağıtır.

    `uygula=False` yalnızca planı hesaplar, veritabanına dokunmaz.
    `kaynak` verilirse sadece o lokasyondaki cihazlar taşınır.

    Dönen sözlük: toplam, kodsuz, plan (taşıma tanımı -> adet), tasinan,
    olusan (yeni lokasyon sayısı), temizlenen (kodu silinen boş lokasyon).
    """
    varliklar = db.scalars(select(models.Asset)).all()
    lokasyonlar = {l.id: l for l in db.scalars(select(models.Location)).all()}

    # Ad -> lokasyon (Türkçe duyarlı karşılaştırma; DB LOWER()'a güvenme)
    ada_gore = {sema._sadelestir(l.name): l for l in lokasyonlar.values() if l.name}

    kodsuz = 0
    aday: list[tuple[models.Asset, str | None, str]] = []
    for a in varliklar:
        mevcut = lokasyonlar.get(a.location_id)
        mevcut_ad = mevcut.name if mevcut else None
        if kaynak and (mevcut_ad or "") != kaynak:
            continue
        kod = sema.proje_kodu_normalle(birim(a))
        if not kod:
            kodsuz += 1
            continue
        aday.append((a, mevcut_ad, kod))

    # Lokasyonu olmayan cihazın hedef adı yalnızca kodun kendisi olurdu ("U023").
    # Aynı proje ikiye bölünmesin diye o kodun asıl şantiyesini bul: önce bu
    # çalıştırmada oluşacak şantiyeler, sonra adı zaten projeye özel olanlar.
    kod_hedefi: dict[str, str] = {}
    for _, mevcut_ad, kod in aday:
        if mevcut_ad:
            kod_hedefi.setdefault(kod, sema.santiye_adi(mevcut_ad, kod))
    for l in lokasyonlar.values():
        if l.proje_kodu and _projeye_ozel(l.name, l.proje_kodu):
            kod_hedefi.setdefault(l.proje_kodu, l.name)

    plan: Counter = Counter()
    tasinacak: list[tuple[models.Asset, str, str]] = []
    for a, mevcut_ad, kod in aday:
        hedef_ad = sema.santiye_adi(mevcut_ad, kod)
        if not mevcut_ad:
            hedef_ad = kod_hedefi.get(kod, hedef_ad)
        if not hedef_ad or hedef_ad == mevcut_ad:
            continue  # zaten doğru yerde
        tasinacak.append((a, hedef_ad, kod))
        plan[f"{mevcut_ad or '(lokasyonsuz)'} → {hedef_ad}"] += 1

    rapor = {
        "toplam": len(varliklar),
        "kodsuz": kodsuz,
        "plan": dict(plan),
        "tasinan": len(tasinacak),
        "olusan": 0,
        "temizlenen": 0,
    }
    if not uygula or not tasinacak:
        return rapor

    for a, hedef_ad, kod in tasinacak:
        # Hedef adı planlama aşamasında tekilleştirildi; burada ada bakmak yeterli.
        anahtar = sema._sadelestir(hedef_ad)
        hedef = ada_gore.get(anahtar)
        if hedef is None:
            hedef = models.Location(name=hedef_ad, proje_kodu=kod)
            db.add(hedef)
            db.flush()
            ada_gore[anahtar] = hedef
            rapor["olusan"] += 1
        elif not hedef.proje_kodu:
            hedef.proje_kodu = kod
        a.location_id = hedef.id

    # Boşalan genel lokasyonun eski içe aktarımdan kalan proje kodunu temizle;
    # aksi hâlde proje filtresinde 0 cihazlı hayalet bir kayıt olarak durur.
    db.flush()
    dolu = {a.location_id for a in varliklar if a.location_id}
    for l in lokasyonlar.values():
        if l.proje_kodu and l.id not in dolu and not _projeye_ozel(l.name, l.proje_kodu):
            l.proje_kodu = None
            rapor["temizlenen"] += 1

    db.commit()
    return rapor


def santiye_ozeti(db: Session) -> list[tuple[str, str | None, int]]:
    """(lokasyon adı, proje kodu, cihaz sayısı) — yalnızca dolu lokasyonlar."""
    from sqlalchemy import func

    return [
        (ad, kod, sayi)
        for ad, kod, sayi in db.execute(
            select(models.Location.name, models.Location.proje_kodu,
                   func.count(models.Asset.id))
            .select_from(models.Location)
            .join(models.Asset, models.Asset.location_id == models.Location.id)
            .group_by(models.Location.id)
            .order_by(models.Location.proje_kodu, models.Location.name)
        ).all()
    ]
