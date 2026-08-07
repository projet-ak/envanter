"""Türkçe duyarlı hızlı arama (yazdıkça listeleme).

Neden veritabanı `ILIKE`'ı değil:
SQL'in büyük/küçük harf eşlemesi Türkçe'de doğru çalışmaz. PostgreSQL'de
`lower('ERTEKİN')` sonucu `erteki̇n` (i + birleşen nokta) olur, `ertekin`
ile eşleşmez; SQLite'ın `LOWER()`'ı ise yalnızca ASCII harfleri çevirir
(`'ŞANTİYE'` -> `'Şantİye'`). Yani kullanıcı "ertekin" ya da "santiye"
yazdığında SQL hiçbir şey bulmaz.

Bunun yerine her iki taraf da Python'da ASCII'ye indirgenip karşılaştırılır
(`sema._sadelestir`): "santiye" -> "ŞANTİYE", "ertekin" -> "ERTEKİN" bulunur.
Veri kümesi kurum envanteri ölçeğinde (bin(ler)ce kayıt) olduğu için bu
karşılaştırma bellekte yapılır; sınır `ARAMA_TAVANI` ile korunur.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.excel.sema import _sadelestir

# Bellekte taranacak azami kayıt sayısı. Aşılırsa arama yine çalışır ama
# yalnızca ilk bu kadar kayıt taranır (uyarı olarak bildirilir).
ARAMA_TAVANI = 50_000


def normalle(metin: str | None) -> str:
    return _sadelestir(metin) if metin else ""


def _eslesir(terim: str, *alanlar: str | None) -> bool:
    return any(terim in normalle(a) for a in alanlar if a)


def _kisi_adi(k: models.User | None) -> str | None:
    if k is None:
        return None
    return " ".join(filter(None, [k.first_name, k.last_name]))


def _eslesen_lokasyonlar(db: Session, terim: str) -> set[int]:
    """Adı ya da proje kodu terimle eşleşen lokasyonların kimlikleri."""
    return {
        lid for lid, ad, kod in db.execute(
            select(models.Location.id, models.Location.name,
                   models.Location.proje_kodu).limit(ARAMA_TAVANI)
        ).all()
        if _eslesir(terim, ad, kod)
    }


def cihaz_idleri(db: Session, q: str) -> list[int]:
    """Terimle eşleşen cihaz kimlikleri.

    Cihazın kendi alanlarının yanı sıra zimmetli olduğu personelin adı ve
    bulunduğu lokasyonun adı / proje kodu da kapsanır.
    """
    terim = normalle(q)
    if not terim:
        return []

    # Zimmetli personelin adına göre de eşleşsin: önce eşleşen kişileri bul.
    kisiler = db.execute(
        select(models.User.id, models.User.first_name, models.User.last_name,
               models.User.employee_num).limit(ARAMA_TAVANI)
    ).all()
    kisi_idleri = {
        kid for kid, ad, soyad, sicil in kisiler
        if _eslesir(terim, " ".join(filter(None, [ad, soyad])), sicil)
    }
    lokasyon_idleri = _eslesen_lokasyonlar(db, terim)

    satirlar = db.execute(
        select(models.Asset.id, models.Asset.asset_tag, models.Asset.serial,
               models.Asset.name, models.Asset.demirbas_no, models.Asset.ip_address,
               models.Asset.barkod, models.Asset.imei, models.Asset.hostname,
               models.Asset.assigned_user_id,
               models.Asset.location_id).limit(ARAMA_TAVANI)
    ).all()

    return [
        r.id for r in satirlar
        if _eslesir(terim, r.asset_tag, r.serial, r.name, r.demirbas_no,
                    r.ip_address, r.barkod, r.imei, r.hostname)
        or (r.assigned_user_id in kisi_idleri)
        or (r.location_id in lokasyon_idleri)
    ]


def personel_ara(db: Session, q: str, *, limit: int = 20) -> list[dict]:
    """Zimmet verirken personel seçmek için ada/sicile göre arama.

    Terim boşsa en çok cihaz taşıyanlardan başlayarak liste döner; böylece
    kutu açılır açılmaz seçilebilecek isimler görünür.
    """
    from sqlalchemy import func

    sayilar = dict(db.execute(
        select(models.Asset.assigned_user_id, func.count(models.Asset.id))
        .where(models.Asset.assigned_user_id.is_not(None))
        .group_by(models.Asset.assigned_user_id)
    ).all())

    terim = normalle(q)
    kisiler = db.scalars(
        select(models.User).where(models.User.active.is_(True)).limit(ARAMA_TAVANI)
    ).all()
    if terim:
        kisiler = [
            k for k in kisiler
            if _eslesir(terim, _kisi_adi(k), k.employee_num, k.department,
                        k.sube, k.email)
        ]
        kisiler.sort(key=lambda k: normalle(_kisi_adi(k)))
    else:
        kisiler = sorted(kisiler, key=lambda k: -sayilar.get(k.id, 0))

    return [
        {
            "id": k.id,
            "ad": _kisi_adi(k),
            "employee_num": k.employee_num,
            "department": k.department,
            "sube": k.sube,
            "cihaz_sayisi": sayilar.get(k.id, 0),
        }
        for k in kisiler[:limit]
    ]


def hizli_ara(db: Session, q: str, *, limit: int = 10) -> dict:
    """Genel arama: cihazlar + personel, tek çağrıda.

    Arayüzdeki üst arama kutusu bunu kullanır; kullanıcı yazdıkça sonuç döner.
    """
    terim = normalle(q)
    if not terim:
        return {"cihazlar": [], "personel": [], "lokasyonlar": [],
                "cihaz_toplam": 0, "personel_toplam": 0, "lokasyon_toplam": 0}

    # --- Personel ---
    kisiler = db.scalars(select(models.User).limit(ARAMA_TAVANI)).all()
    kisi_bulunan = [
        k for k in kisiler
        if _eslesir(terim, _kisi_adi(k), k.employee_num, k.department, k.email)
    ]
    # Ada göre sırala (Türkçe indirgenmiş hâliyle)
    kisi_bulunan.sort(key=lambda k: normalle(_kisi_adi(k)))

    # --- Cihazlar ---
    idler = set(cihaz_idleri(db, q))
    cihazlar = []
    if idler:
        cihazlar = db.scalars(
            select(models.Asset)
            .where(models.Asset.id.in_(idler))
            .order_by(models.Asset.asset_tag)
        ).all()

    # --- Lokasyonlar (ad ya da proje kodu) ---
    from sqlalchemy import func

    lokasyon_sayilari = dict(db.execute(
        select(models.Asset.location_id, func.count(models.Asset.id))
        .where(models.Asset.location_id.is_not(None))
        .group_by(models.Asset.location_id)
    ).all())
    tum_lokasyonlar = db.scalars(select(models.Location).limit(ARAMA_TAVANI)).all()
    lokasyon_bulunan = [
        l for l in tum_lokasyonlar if _eslesir(terim, l.name, l.proje_kodu)
    ]
    # Çok cihazlı şantiye önce gelsin
    lokasyon_bulunan.sort(key=lambda l: -lokasyon_sayilari.get(l.id, 0))

    kisi_adlari = {k.id: _kisi_adi(k) for k in kisiler}
    lokasyonlar = {l.id: l.name for l in tum_lokasyonlar}

    return {
        "cihaz_toplam": len(cihazlar),
        "personel_toplam": len(kisi_bulunan),
        "lokasyon_toplam": len(lokasyon_bulunan),
        "lokasyonlar": [
            {
                "id": l.id,
                "ad": l.name,
                "proje_kodu": l.proje_kodu,
                "cihaz_sayisi": lokasyon_sayilari.get(l.id, 0),
            }
            for l in lokasyon_bulunan[:limit]
        ],
        "cihazlar": [
            {
                "id": a.id,
                "asset_tag": a.asset_tag,
                "name": a.name,
                "serial": a.serial,
                "demirbas_no": a.demirbas_no,
                "lokasyon": lokasyonlar.get(a.location_id),
                "zimmetli": kisi_adlari.get(a.assigned_user_id),
            }
            for a in cihazlar[:limit]
        ],
        "personel": [
            {
                "id": k.id,
                "ad": _kisi_adi(k),
                "employee_num": k.employee_num,
                "department": k.department,
            }
            for k in kisi_bulunan[:limit]
        ],
    }
