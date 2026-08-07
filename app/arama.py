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


def cihaz_idleri(db: Session, q: str) -> list[int]:
    """Terimle eşleşen cihaz kimlikleri (zimmetli personel adı dahil)."""
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

    satirlar = db.execute(
        select(models.Asset.id, models.Asset.asset_tag, models.Asset.serial,
               models.Asset.name, models.Asset.demirbas_no, models.Asset.ip_address,
               models.Asset.barkod, models.Asset.imei, models.Asset.hostname,
               models.Asset.assigned_user_id).limit(ARAMA_TAVANI)
    ).all()

    return [
        r.id for r in satirlar
        if _eslesir(terim, r.asset_tag, r.serial, r.name, r.demirbas_no,
                    r.ip_address, r.barkod, r.imei, r.hostname)
        or (r.assigned_user_id in kisi_idleri)
    ]


def hizli_ara(db: Session, q: str, *, limit: int = 10) -> dict:
    """Genel arama: cihazlar + personel, tek çağrıda.

    Arayüzdeki üst arama kutusu bunu kullanır; kullanıcı yazdıkça sonuç döner.
    """
    terim = normalle(q)
    if not terim:
        return {"cihazlar": [], "personel": [], "cihaz_toplam": 0,
                "personel_toplam": 0}

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

    kisi_adlari = {k.id: _kisi_adi(k) for k in kisiler}
    lokasyonlar = {
        lid: ad for lid, ad in db.execute(
            select(models.Location.id, models.Location.name)
        ).all()
    }

    return {
        "cihaz_toplam": len(cihazlar),
        "personel_toplam": len(kisi_bulunan),
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
