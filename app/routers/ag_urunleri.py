"""Ağ / network ürünleri uçları.

Ağ ürünleri normal varlıklardır (bkz. app/ag.py); bu router yalnızca türe
özel bir görünüm ve toplu ekleme kolaylığı sunar.
"""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ag, models, schemas
from app.auth import get_current_user, require_editor
from app.database import get_db

router = APIRouter(prefix="/ag", tags=["Ağ Ürünleri"])
READ = [Depends(get_current_user)]
WRITE = [Depends(require_editor)]


@router.get("/aileler", dependencies=READ)
def aileler():
    """Ürün aileleri (Ağ, Yangın, Alarm) — menü bunlardan üretilir."""
    return [{"aile": k, **v} for k, v in ag.AILELER.items()]


@router.get("/sablon", dependencies=READ)
def sablon(aile: str | None = Query(None, description="ag | yangin | alarm")):
    """Ürün türleri ve her türün teknik alanları (arayüz formu bundan üretilir)."""
    if aile and aile not in ag.AILELER:
        raise HTTPException(400, f"Bilinmeyen aile: {aile}")
    return ag.sablon(aile)


@router.get("/urunler", dependencies=READ)
def urunler(
    aile: str | None = Query(None, description="ag | yangin | alarm"),
    tur: str | None = Query(None, description="switch, sfp, dedektor, yangin_panel…"),
    location_id: int | None = None,
    proje_kodu: str | None = None,
    durum_id: int | None = None,
    q: str | None = Query(None, description="Marka/model/seri/özellik içinde ara"),
    db: Session = Depends(get_db),
):
    if tur and tur not in ag.TURLER:
        raise HTTPException(400, f"Bilinmeyen tür: {tur}")
    if aile and aile not in ag.AILELER:
        raise HTTPException(400, f"Bilinmeyen aile: {aile}")
    return ag.urunler(db, aile=aile, tur=tur, location_id=location_id,
                      proje_kodu=proje_kodu, durum_id=durum_id, q=q)


@router.get("/telefon-rehberi", dependencies=READ)
def telefon_rehberi(db: Session = Depends(get_db)):
    """Dahili numara rehberi (personel künyesi + IP telefonlar birleşik)."""
    return ag.telefon_rehberi(db)


def _rehber_cakisma(db: Session, dahili: str, *, kisi_id: int | None,
                    asset_id: int | None) -> None:
    """Aynı dahili başka kişide ya da başka telefonda olmasın."""
    kisi = db.scalar(select(models.User).where(models.User.dahili == dahili,
                                               models.User.id != (kisi_id or 0)))
    if kisi is not None:
        raise HTTPException(
            409, f"{dahili} dahilisi zaten {kisi.full_name} üzerinde kayıtlı")
    cihaz = db.scalar(select(models.Asset).where(
        models.Asset.telefon_no == dahili, models.Asset.id != (asset_id or 0)))
    if cihaz is not None:
        raise HTTPException(
            409, f"{dahili} dahilisi zaten {cihaz.asset_tag} telefonunda kayıtlı")


def _rehber_etiket(db: Session, dahili: str) -> str:
    """Yeni telefon için cihaz no üretir: TEL-1720, çakışırsa TEL-1720-2…"""
    kok = "TEL-" + re.sub(r"[^0-9A-Za-z]", "", dahili)
    etiket, n = kok, 1
    while db.scalar(select(models.Asset).where(models.Asset.asset_tag == etiket)):
        n += 1
        etiket = f"{kok}-{n}"
    return etiket


def _rehber_yaz(db: Session, payload: schemas.RehberKayit) -> dict:
    """Rehber satırını yazar: kişi künyesi ve/veya telefon kaydı."""
    dahili = payload.dahili.strip()
    if not dahili:
        raise HTTPException(400, "Dahili numara zorunlu")

    kisi = db.get(models.User, payload.kisi_id) if payload.kisi_id else None
    if payload.kisi_id and kisi is None:
        raise HTTPException(404, "Personel bulunamadı")
    varlik = db.get(models.Asset, payload.asset_id) if payload.asset_id else None
    if payload.asset_id and varlik is None:
        raise HTTPException(404, "Telefon kaydı bulunamadı")

    _rehber_cakisma(db, dahili, kisi_id=payload.kisi_id, asset_id=payload.asset_id)

    # Satırdaki kişi değiştiyse eskisinin dahilisi boşalsın
    if payload.eski_kisi_id and payload.eski_kisi_id != payload.kisi_id:
        eski = db.get(models.User, payload.eski_kisi_id)
        # Numara da değişmiş olabilir: satırın eski numarası da temizlenir,
        # ama kişinin ilgisiz başka bir dahilisi varsa ona dokunulmaz.
        if eski is not None and eski.dahili in {dahili, payload.eski_dahili}:
            eski.dahili = None

    if kisi is not None:
        kisi.dahili = dahili

    cihaz_alanlari = any([payload.marka, payload.model, payload.mac_address,
                          payload.ip_address, payload.kat, payload.konum,
                          payload.kullanan])
    if varlik is None and (payload.cihaz_olustur or cihaz_alanlari):
        varlik = models.Asset(asset_tag=_rehber_etiket(db, dahili),
                              location_id=payload.location_id)
        db.add(varlik)
        db.flush()
        db.add(models.ActivityLog(action=models.ActivityAction.create,
                                  item_type="asset", item_id=varlik.id,
                                  note="Telefon rehberinden eklendi"))

    if varlik is not None:
        mac = mac_duzenle(payload.mac_address)
        if mac:
            ayni = db.scalar(select(models.Asset).where(
                models.Asset.mac_address == mac, models.Asset.id != varlik.id))
            if ayni is not None:
                raise HTTPException(
                    409, f"'{mac}' MAC adresi zaten kayıtlı ({ayni.asset_tag})")
        varlik.telefon_no = dahili
        varlik.mac_address = mac
        varlik.ip_address = payload.ip_address or None
        if payload.location_id is not None:
            varlik.location_id = payload.location_id
        mdl = _model_bul(db, "ip_telefon", payload.marka, payload.model)
        varlik.model_id = mdl.id
        ozel = {g: dict(v) for g, v in (varlik.custom or {}).items()
                if isinstance(v, dict)}
        grup = dict(ozel.get(ag.GRUP) or {})
        for alan, deger in (("Kat", payload.kat), ("Konum", payload.konum),
                            ("Kullanan", payload.kullanan)):
            if deger:
                grup[alan] = deger
            else:
                grup.pop(alan, None)
        ozel[ag.GRUP] = grup
        varlik.custom = ozel
        yer = payload.konum or payload.kullanan or (kisi.full_name if kisi else None)
        varlik.name = " ".join(filter(None, [payload.marka, payload.model])) or None
        if varlik.name and yer:
            varlik.name = f"{varlik.name} — {yer}"

        # Telefon, dahilinin sahibine zimmetli olsun
        if kisi is not None and varlik.assigned_user_id != kisi.id:
            varlik.assigned_type = models.AssignedType.user
            varlik.assigned_user_id = kisi.id
            varlik.assigned_location_id = None
            varlik.last_checkout = dt.datetime.now(dt.timezone.utc)
            db.add(models.ActivityLog(
                action=models.ActivityAction.checkout, item_type="asset",
                item_id=varlik.id, target_type="user", target_id=kisi.id,
                note=f"{kisi.full_name} üzerine zimmetlendi (telefon rehberi)"))

    if kisi is None and varlik is None:
        raise HTTPException(400, "Kişi ya da telefon bilgisi verin")

    db.commit()
    return {"dahili": dahili,
            "kisi_id": kisi.id if kisi else None,
            "asset_id": varlik.id if varlik else None}


@router.post("/telefon-rehberi", status_code=201, dependencies=WRITE)
def rehber_ekle(payload: schemas.RehberKayit, db: Session = Depends(get_db)):
    """Rehbere yeni dahili ekler (kişiye ve/veya telefona)."""
    return _rehber_yaz(db, payload)


@router.put("/telefon-rehberi", dependencies=WRITE)
def rehber_guncelle(payload: schemas.RehberKayit, db: Session = Depends(get_db)):
    """Rehber satırını günceller."""
    return _rehber_yaz(db, payload)


@router.delete("/telefon-rehberi", status_code=204, dependencies=WRITE)
def rehber_sil(
    kisi_id: int | None = None,
    asset_id: int | None = None,
    cihazi_sil: bool = Query(False, description="Telefon kaydını da sil"),
    db: Session = Depends(get_db),
):
    """Dahiliyi rehberden kaldırır.

    Varsayılan davranış numarayı boşaltmaktır; telefon envanterde kalır.
    `cihazi_sil` verilirse telefon kaydı da silinir.
    """
    if not kisi_id and not asset_id:
        raise HTTPException(400, "kisi_id ya da asset_id gerekli")
    if kisi_id:
        kisi = db.get(models.User, kisi_id)
        if kisi is not None:
            kisi.dahili = None
    if asset_id:
        varlik = db.get(models.Asset, asset_id)
        if varlik is not None:
            if cihazi_sil:
                db.add(models.ActivityLog(action=models.ActivityAction.delete,
                                          item_type="asset", item_id=varlik.id,
                                          note=f"{varlik.asset_tag} silindi "
                                               f"(telefon rehberi)"))
                db.delete(varlik)
            else:
                varlik.telefon_no = None
    db.commit()


@router.get("/ozet", dependencies=READ)
def ozet(aile: str | None = Query(None, description="ag | yangin | alarm"),
         db: Session = Depends(get_db)):
    if aile and aile not in ag.AILELER:
        raise HTTPException(400, f"Bilinmeyen aile: {aile}")
    return ag.ozet(db, aile=aile)


@router.get("/transferler", dependencies=READ)
def transferler(limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    """Lokasyonu değişen cihazlar — hangi şantiyeden hangisine gitti."""
    return ag.transferler(db, limit=limit)


# --------------------------------------------------------------------------- #
# Ekleme
# --------------------------------------------------------------------------- #
def _referans(db: Session, model, ad: str | None):
    """Ada göre kaydı bulur, yoksa oluşturur (Türkçe duyarlı karşılaştırma)."""
    from app.excel.sema import _sadelestir

    ad = (ad or "").strip()
    if not ad:
        return None
    aranan = _sadelestir(ad)
    for nesne in db.scalars(select(model)).all():
        if nesne.name and _sadelestir(nesne.name) == aranan:
            return nesne
    nesne = model(name=ad)
    db.add(nesne)
    db.flush()
    return nesne


def _model_bul(db: Session, tur: str, marka_adi: str | None, model_adi: str | None):
    """Ağ ürünü için model kaydını bulur/oluşturur ve doğru kategoriye bağlar."""
    kategori = _referans(db, models.Category, ag.kategori_adi(tur))
    marka = _referans(db, models.Manufacturer, marka_adi)
    ad = (model_adi or "").strip() or (marka_adi or "").strip() or ag.kategori_adi(tur)

    from app.excel.sema import _sadelestir
    aranan = _sadelestir(ad)
    for m in db.scalars(select(models.AssetModel)).all():
        if (m.name and _sadelestir(m.name) == aranan
                and m.category_id == kategori.id
                and m.manufacturer_id == (marka.id if marka else None)):
            return m
    m = models.AssetModel(name=ad, category_id=kategori.id,
                          manufacturer_id=marka.id if marka else None)
    db.add(m)
    db.flush()
    return m


def mac_duzenle(ham: str | None) -> str | None:
    """MAC'i tek biçime getirir: büyük harf, iki haneli gruplar, iki nokta.

    'd4-19-72-c5-4b-46', 'D41972C54B46' ve 'd4:19:72:c5:4b:46' aynı cihazdır;
    tek biçime indirgenmezse mükerrer kayıt kaçınılmaz olur.
    """
    if not ham:
        return None
    temiz = re.sub(r"[^0-9A-Fa-f]", "", ham).upper()
    if len(temiz) != 12:
        return ham.strip() or None          # tanımadığımız biçim: olduğu gibi
    return ":".join(temiz[i:i + 2] for i in range(0, 12, 2))


@router.post("/urunler", status_code=201, dependencies=WRITE)
def urun_ekle(payload: schemas.AgUrunEkle, db: Session = Depends(get_db)):
    """Ağ ürünü ekler: kategori, marka ve model gerekirse kendiliğinden açılır."""
    if payload.tur not in ag.TURLER:
        raise HTTPException(400, f"Bilinmeyen tür: {payload.tur}")

    mac = mac_duzenle(payload.mac_address)
    etiket = ((payload.asset_tag or "").strip() or (payload.serial or "").strip()
              or (mac or ""))
    if not etiket:
        raise HTTPException(400, "Cihaz no, seri no ya da MAC adresi zorunlu")
    if db.scalar(select(models.Asset).where(models.Asset.asset_tag == etiket)):
        raise HTTPException(409, f"'{etiket}' etiketi zaten kullanımda")
    # MAC cihazın parmak izi: aynı MAC ikinci kez girilemesin
    if mac:
        ayni = db.scalar(select(models.Asset).where(models.Asset.mac_address == mac))
        if ayni is not None:
            raise HTTPException(
                409, f"'{mac}' MAC adresi zaten kayıtlı ({ayni.asset_tag})")

    mdl = _model_bul(db, payload.tur, payload.marka, payload.model)
    varlik = models.Asset(
        asset_tag=etiket,
        name=payload.ad or " ".join(filter(None, [payload.marka, payload.model])) or None,
        serial=payload.serial or None,
        demirbas_no=payload.demirbas_no or None,
        ip_address=payload.ip_address or None,
        mac_address=mac,
        operator=payload.operator or None,
        telefon_no=payload.telefon_no or None,
        sim_no=payload.sim_no or None,
        imei=payload.imei or None,
        model_id=mdl.id,
        location_id=payload.location_id,
        status_id=payload.status_id,
        notes=payload.notes or None,
        custom={ag.GRUP: {k: v for k, v in (payload.ozellikler or {}).items() if v}},
    )
    db.add(varlik)
    db.flush()
    db.add(models.ActivityLog(action=models.ActivityAction.create,
                              item_type="asset", item_id=varlik.id,
                              note=f"Ağ ürünü eklendi ({ag.TURLER[payload.tur]['ad']})"))
    db.commit()
    db.refresh(varlik)
    return {"id": varlik.id, "asset_tag": varlik.asset_tag}


@router.put("/urunler/{asset_id}/ozellikler", dependencies=WRITE)
def ozellikleri_yaz(asset_id: int, ozellikler: dict[str, str],
                    db: Session = Depends(get_db)):
    """Ağ özelliklerini topluca günceller (boş değerler silinir)."""
    varlik = db.get(models.Asset, asset_id)
    if varlik is None:
        raise HTTPException(404, "Varlık bulunamadı")

    # JSON sütunu yerinde değişikliği izlemez; yeni sözlük atanır
    ozel = {g: dict(v) for g, v in (varlik.custom or {}).items() if isinstance(v, dict)}
    temiz = {k: v for k, v in ozellikler.items() if v not in (None, "")}
    if temiz:
        ozel[ag.GRUP] = temiz
    else:
        ozel.pop(ag.GRUP, None)
    varlik.custom = ozel

    db.add(models.ActivityLog(action=models.ActivityAction.update,
                              item_type="asset", item_id=asset_id,
                              note="Ağ özellikleri güncellendi"))
    db.commit()
    return {"id": asset_id, "ozellikler": temiz}
