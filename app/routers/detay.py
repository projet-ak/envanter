"""Detay uçları: cihazın tüm özellikleri, kişinin zimmetli cihazları."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/detay", tags=["Detay"],
                   dependencies=[Depends(get_current_user)])


def _ad(nesne) -> str | None:
    return nesne.name if nesne is not None else None


# İşlem geçmişindeki alan adları arayüzde Türkçe görünsün
ALAN_ADLARI = {
    "asset_tag": "Cihaz No", "name": "Ad", "serial": "Seri No",
    "demirbas_no": "Demirbaş No", "muhasebe_kodu": "IFS Kodu",
    "barkod": "Barkod", "ip_address": "IP", "hostname": "Hostname",
    "mac_address": "MAC", "imei": "IMEI", "telefon_no": "Telefon",
    "sim_no": "SIM", "operator": "Operatör", "fatura_no": "Fatura No",
    "purchase_date": "Alım Tarihi", "warranty_end": "Garanti Bitiş",
    "purchase_cost": "Bedel", "notes": "Açıklama", "custom": "Özellikler",
    "model_id": "Model", "location_id": "Lokasyon", "status_id": "Durum",
    "supplier_id": "Tedarikçi", "company_id": "Şirket",
    "assigned_user_id": "Zimmetli Kişi", "assigned_location_id": "Zimmet Yeri",
}

# id alanları geçmişte sayı değil adla görünsün
_AD_TABLOLARI = {
    "model_id": models.AssetModel, "location_id": models.Location,
    "status_id": models.StatusLabel, "supplier_id": models.Supplier,
    "company_id": models.Company,
    "assigned_location_id": models.Location,
}


def _deger_metni(db: Session, alan: str, deger) -> str:
    """Geçmişteki ham değeri okunur hale getirir (id -> ad)."""
    if deger in (None, "", "None"):
        return "—"
    tablo = _AD_TABLOLARI.get(alan)
    if tablo is not None:
        try:
            nesne = db.get(tablo, int(deger))
        except (TypeError, ValueError):
            return str(deger)
        return _ad(nesne) or str(deger)
    if alan == "assigned_user_id":
        try:
            return _kisi_adi(db.get(models.User, int(deger))) or str(deger)
        except (TypeError, ValueError):
            return str(deger)
    metin = str(deger)
    return metin if len(metin) <= 60 else metin[:57] + "…"


def _degisim_metinleri(db: Session, changes: dict | None) -> list[str]:
    """{"location_id": {"eski": 3, "yeni": 7}} -> ["Lokasyon: Depo → U070"]."""
    satirlar = []
    for alan, degisim in (changes or {}).items():
        if not isinstance(degisim, dict):
            continue
        etiket = ALAN_ADLARI.get(alan, alan)
        eski = _deger_metni(db, alan, degisim.get("eski"))
        yeni = _deger_metni(db, alan, degisim.get("yeni"))
        satirlar.append(f"{etiket}: {eski} → {yeni}")
    return satirlar


def _kisi_adi(k: models.User | None) -> str | None:
    if k is None:
        return None
    return " ".join(filter(None, [k.first_name, k.last_name]))


def _varlik_ozeti(db: Session, a: models.Asset) -> dict:
    mdl = db.get(models.AssetModel, a.model_id) if a.model_id else None
    return {
        "id": a.id,
        "asset_tag": a.asset_tag,
        "name": a.name,
        "serial": a.serial,
        "demirbas_no": a.demirbas_no,
        "kategori": _ad(db.get(models.Category, mdl.category_id))
                    if mdl and mdl.category_id else None,
        "marka": _ad(db.get(models.Manufacturer, mdl.manufacturer_id))
                 if mdl and mdl.manufacturer_id else None,
        "model": _ad(mdl),
        "durum": _ad(db.get(models.StatusLabel, a.status_id)) if a.status_id else None,
        "lokasyon": _ad(db.get(models.Location, a.location_id))
                    if a.location_id else None,
        "ip_address": a.ip_address,
        "purchase_cost": float(a.purchase_cost) if a.purchase_cost else None,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "warranty_end": a.warranty_end.isoformat() if a.warranty_end else None,
    }


@router.get("/asset/{asset_id}")
def varlik_detay(asset_id: int, db: Session = Depends(get_db)):
    """Cihazın tüm bilgileri: künye, teknik özellikler, zimmet, geçmiş."""
    a = db.get(models.Asset, asset_id)
    if a is None:
        raise HTTPException(404, "Cihaz bulunamadı")

    mdl = db.get(models.AssetModel, a.model_id) if a.model_id else None
    zimmetli = db.get(models.User, a.assigned_user_id) if a.assigned_user_id else None

    gecmis = db.scalars(
        select(models.ActivityLog)
        .where(models.ActivityLog.item_type == "asset",
               models.ActivityLog.item_id == asset_id)
        .order_by(models.ActivityLog.created_at.desc(),
                  models.ActivityLog.id.desc())
        .limit(100)
    ).all()

    return {
        "kunye": {
            **_varlik_ozeti(db, a),
            "muhasebe_kodu": a.muhasebe_kodu,
            "fatura_no": a.fatura_no,
            "barkod": a.barkod,
            "imei": a.imei,
            "mac_address": a.mac_address,
            "hostname": a.hostname,
            "telefon_no": a.telefon_no,
            "sim_no": a.sim_no,
            "operator": a.operator,
            "tedarikci": _ad(db.get(models.Supplier, a.supplier_id))
                         if a.supplier_id else None,
            "sirket": _ad(db.get(models.Company, a.company_id))
                      if a.company_id else None,
            "notes": a.notes,
        },
        "zimmet": {
            "tur": a.assigned_type.value if a.assigned_type else None,
            "kisi_id": zimmetli.id if zimmetli else None,
            "kisi": _kisi_adi(zimmetli),
            "departman": zimmetli.department if zimmetli else None,
            "unvan": zimmetli.job_title if zimmetli else None,
            "lokasyon": _ad(db.get(models.Location, a.assigned_location_id))
                        if a.assigned_location_id else None,
            "tarih": a.last_checkout.isoformat() if a.last_checkout else None,
        },
        # Teknik özellikler zaten gruplu JSON olarak saklanıyor
        "ozellikler": a.custom or {},
        "dosyalar": [
            {
                "id": d.id,
                "tur": d.tur.value,
                "dosya_adi": d.dosya_adi,
                "content_type": d.content_type,
                "boyut": d.boyut,
                "aciklama": d.aciklama,
                "yukleyen": d.yukleyen,
                "tarih": d.created_at.isoformat() if d.created_at else None,
            }
            for d in a.dosyalar
        ],
        "gecmis": [
            {
                "islem": g.action.value,
                "not": g.note,
                "degisiklikler": g.changes,
                # Arayüz için okunur satırlar: "Lokasyon: Depo → U070"
                "degisim_metinleri": _degisim_metinleri(db, g.changes),
                "yapan": g.actor,
                "tarih": g.created_at.isoformat() if g.created_at else None,
            }
            for g in gecmis
        ],
        "kullanim_gecmisi": _kullanim_gecmisi(db, asset_id),
    }


def _kullanim_gecmisi(db: Session, asset_id: int) -> list[dict]:
    """Cihazı kimler kullandı: checkout/checkin kayıtları eşleştirilir.

    Kronolojik sırada her checkout bir satır açar, onu izleyen checkin
    satırı kapatır; kapanmamış satır "hâlâ kullanımda" demektir.
    """
    loglar = db.scalars(
        select(models.ActivityLog)
        .where(models.ActivityLog.item_type == "asset",
               models.ActivityLog.item_id == asset_id,
               models.ActivityLog.action.in_(
                   [models.ActivityAction.checkout,
                    models.ActivityAction.checkin]))
        # Aynı saniyede yazılan kayıtlarda sıra kaybolmasın: id eşitlik bozucu
        .order_by(models.ActivityLog.created_at, models.ActivityLog.id)
    ).all()

    satirlar: list[dict] = []
    acik: dict | None = None
    for g in loglar:
        if g.action == models.ActivityAction.checkout:
            kisi = (db.get(models.User, g.target_id)
                    if g.target_type == "user" and g.target_id else None)
            lok = (db.get(models.Location, g.target_id)
                   if g.target_type == "location" and g.target_id else None)
            acik = {
                "kisi_id": kisi.id if kisi else None,
                "kime": _kisi_adi(kisi) if kisi
                        else (f"📍 {lok.name}" if lok else "—"),
                "alis": g.created_at.isoformat() if g.created_at else None,
                "iade": None,
                "not": g.note,
            }
            satirlar.append(acik)
        elif acik is not None:
            acik["iade"] = g.created_at.isoformat() if g.created_at else None
            acik = None
    satirlar.reverse()          # en yeni üstte
    return satirlar


@router.get("/lokasyon-sayilari")
def lokasyon_sayilari(db: Session = Depends(get_db)):
    """Lokasyon başına bağlı cihaz / zimmetli cihaz / personel sayıları.

    Tanımlar → Lokasyonlar listesi bu sayıları sütun olarak gösterir;
    tek istekte hepsi gelir (satır başına sorgu atılmaz).
    """
    from sqlalchemy import func

    cihaz = dict(db.execute(
        select(models.Asset.location_id, func.count())
        .where(models.Asset.location_id.is_not(None))
        .group_by(models.Asset.location_id)).all())
    zimmetli = dict(db.execute(
        select(models.Asset.location_id, func.count())
        .where(models.Asset.location_id.is_not(None),
               models.Asset.assigned_type.is_not(None))
        .group_by(models.Asset.location_id)).all())
    kisi = dict(db.execute(
        select(models.User.location_id, func.count())
        .where(models.User.location_id.is_not(None))
        .group_by(models.User.location_id)).all())

    return [
        {"location_id": lok_id,
         "cihaz": cihaz.get(lok_id, 0),
         "zimmetli": zimmetli.get(lok_id, 0),
         "kisi": kisi.get(lok_id, 0)}
        for lok_id in {*cihaz, *zimmetli, *kisi}
    ]


@router.get("/location/{location_id}")
def lokasyon_detay(location_id: int, db: Session = Depends(get_db)):
    """Lokasyonun künyesi + bağlı cihazlar ve personel.

    Cihazlar özet künyeyle döner; arayüz her satırdan düzenleme/detay
    penceresine geçer ("lokasyona tıkla → cihazları güncelle" akışı).
    """
    lok = db.get(models.Location, location_id)
    if lok is None:
        raise HTTPException(404, "Lokasyon bulunamadı")

    varliklar = db.scalars(
        select(models.Asset)
        .where(models.Asset.location_id == location_id)
        .order_by(models.Asset.asset_tag)).all()
    kisiler = db.scalars(
        select(models.User)
        .where(models.User.location_id == location_id)
        .order_by(models.User.first_name)).all()

    # Alt projeler: "U030-U031" altında Satış Ofisi, Yönetim Ofisi gibi
    from sqlalchemy import func

    # Gizli bağlantılar: silme/temizlik kararında görünmeleri gerekir —
    # "bağlı bir şey yok" sanılan lokasyonun zimmet yeri ya da stok kaydı
    # olabilir.
    zimmet_yeri = db.scalar(
        select(func.count(models.Asset.id))
        .where(models.Asset.assigned_location_id == location_id)) or 0
    stok = sum(db.scalar(
        select(func.count(t.id)).where(t.location_id == location_id)) or 0
        for t in (models.Accessory, models.Consumable, models.Component))

    ust = db.get(models.Location, lok.parent_id) if lok.parent_id else None
    altlar = db.scalars(
        select(models.Location)
        .where(models.Location.parent_id == location_id)
        .order_by(models.Location.name)).all()
    alt_cihaz = dict(db.execute(
        select(models.Asset.location_id, func.count())
        .where(models.Asset.location_id.in_([a.id for a in altlar]))
        .group_by(models.Asset.location_id)).all()) if altlar else {}

    cihazlar = []
    for a in varliklar:
        ozet = _varlik_ozeti(db, a)
        ozet["zimmetli"] = _kisi_adi(
            db.get(models.User, a.assigned_user_id)) \
            if a.assigned_user_id else None
        cihazlar.append(ozet)

    return {
        "lokasyon": {
            "id": lok.id, "name": lok.name, "proje_kodu": lok.proje_kodu,
            "city": lok.city, "address": lok.address, "renk": lok.renk,
        },
        "ust": {"id": ust.id, "name": ust.name} if ust else None,
        "alt_lokasyonlar": [
            {"id": a.id, "name": a.name, "renk": a.renk,
             "proje_kodu": a.proje_kodu, "cihaz": alt_cihaz.get(a.id, 0)}
            for a in altlar
        ],
        "cihaz_sayisi": len(cihazlar),
        "zimmetli_sayisi": sum(1 for c in varliklar
                               if c.assigned_type is not None),
        "zimmet_yeri_sayisi": zimmet_yeri,
        "stok_sayisi": stok,
        "cihazlar": cihazlar,
        "kisiler": [
            {"id": k.id, "ad": _kisi_adi(k), "unvan": k.job_title,
             "sicil": k.employee_num, "telefon": k.telefon}
            for k in kisiler
        ],
    }


class LokasyonBirlestirme(BaseModel):
    kaynak_id: int      # silinecek mükerrer kayıt
    hedef_id: int       # bağlantıların taşınacağı kalan kayıt


@router.post("/lokasyon-birlestir", status_code=200)
def lokasyon_birlestir(govde: LokasyonBirlestirme,
                       db: Session = Depends(get_db),
                       aktor: models.User = Depends(require_editor)):
    """Mükerrer lokasyonu hedefle birleştirir: kaynak silinir, hiçbir
    bağlantı kaybolmaz.

    Taşınanlar: cihazların lokasyonu ve zimmet yeri, personel, alt
    lokasyonlar, geçmiş kayıtlarının hedefi. Kaynağın dolu olup hedefte boş
    olan alanları (proje kodu, şehir, adres, renk) hedefe kopyalanır.
    """
    if govde.kaynak_id == govde.hedef_id:
        raise HTTPException(400, "Kaynak ve hedef aynı kayıt olamaz")
    kaynak = db.get(models.Location, govde.kaynak_id)
    hedef = db.get(models.Location, govde.hedef_id)
    if kaynak is None or hedef is None:
        raise HTTPException(404, "Lokasyon bulunamadı")

    tasinan = 0
    for sutun in (models.Asset.location_id, models.Asset.assigned_location_id,
                  models.User.location_id, models.Accessory.location_id,
                  models.Consumable.location_id, models.Component.location_id):
        tablo = sutun.parent.class_
        tasinan += db.execute(
            update(tablo).where(sutun == kaynak.id)
            .values({sutun.key: hedef.id})).rowcount
    db.execute(update(models.ActivityLog)
               .where(models.ActivityLog.target_type == "location",
                      models.ActivityLog.target_id == kaynak.id)
               .values(target_id=hedef.id))

    # Alt lokasyonlar hedefe bağlanır; hedef kaynağın altındaysa yukarı alınır
    for cocuk in db.scalars(select(models.Location).where(
            models.Location.parent_id == kaynak.id)).all():
        cocuk.parent_id = kaynak.parent_id if cocuk.id == hedef.id else hedef.id

    for alan in ("proje_kodu", "city", "address", "renk"):
        if not getattr(hedef, alan, None) and getattr(kaynak, alan, None):
            setattr(hedef, alan, getattr(kaynak, alan))

    db.add(models.ActivityLog(
        action=models.ActivityAction.update, item_type="location",
        item_id=hedef.id, actor=aktor.username,
        note=f"Mükerrer birleştirildi: '{kaynak.name}' → '{hedef.name}' "
             f"({tasinan} bağlantı taşındı)"))
    db.delete(kaynak)
    db.commit()
    return {"tasinan": tasinan, "hedef_id": hedef.id}


@router.get("/user/{user_id}")
def kisi_detay(user_id: int, db: Session = Depends(get_db)):
    """Kişinin bilgileri ve zimmetindeki tüm cihazlar (özellikleriyle)."""
    k = db.get(models.User, user_id)
    if k is None:
        raise HTTPException(404, "Personel bulunamadı")

    varliklar = db.scalars(
        select(models.Asset)
        .where(models.Asset.assigned_user_id == user_id)
        .order_by(models.Asset.asset_tag)
    ).all()

    cihazlar = []
    tur_sayilari: dict[str, int] = {}
    toplam_deger = 0.0
    for a in varliklar:
        ozet = _varlik_ozeti(db, a)
        ozet["ozellikler"] = a.custom or {}
        cihazlar.append(ozet)
        tur = ozet["kategori"] or "Diğer"
        tur_sayilari[tur] = tur_sayilari.get(tur, 0) + 1
        toplam_deger += ozet["purchase_cost"] or 0.0

    return {
        "kisi": {
            "id": k.id,
            "ad": _kisi_adi(k),
            "employee_num": k.employee_num,
            "department": k.department,
            "job_title": k.job_title,
            "sube": k.sube,
            "email": k.email,
            "telefon": k.telefon,
            "tckn": k.tckn,
            "ise_giris": k.ise_giris.isoformat() if k.ise_giris else None,
            "isten_cikis": k.isten_cikis.isoformat() if k.isten_cikis else None,
            "active": k.active,
            "notes": k.notes,
            "lokasyon": _ad(db.get(models.Location, k.location_id))
                        if k.location_id else None,
        },
        "cihaz_sayisi": len(cihazlar),
        "tur_dagilimi": dict(sorted(tur_sayilari.items(), key=lambda x: -x[1])),
        "toplam_deger": toplam_deger,
        "cihazlar": cihazlar,
        "gecmis": _kisi_gecmisi(db, user_id),
    }


def _kisi_gecmisi(db: Session, user_id: int) -> list[dict]:
    """Kişinin zimmet geçmişi: hangi cihazı ne zaman aldı / iade etti.

    checkout ve checkin logları hedefinde kişiyi taşır (target_type=user);
    eski zimmetler de burada görünür — "önceki kullanıcı ne kullanmıştı"
    sorusunun cevabı.
    """
    loglar = db.scalars(
        select(models.ActivityLog)
        .where(models.ActivityLog.target_type == "user",
               models.ActivityLog.target_id == user_id,
               models.ActivityLog.action.in_(
                   [models.ActivityAction.checkout,
                    models.ActivityAction.checkin]))
        .order_by(models.ActivityLog.created_at.desc(),
                  models.ActivityLog.id.desc())
        .limit(80)
    ).all()

    etiketler = dict(db.execute(
        select(models.Asset.id, models.Asset.asset_tag)).all())
    return [
        {
            "asset_id": g.item_id,
            "asset_tag": etiketler.get(g.item_id) or f"cihaz #{g.item_id}",
            "islem": ("aldı" if g.action == models.ActivityAction.checkout
                      else "iade etti"),
            "tarih": g.created_at.isoformat() if g.created_at else None,
            "not": g.note,
            "yapan": g.actor,
        }
        for g in loglar
    ]
