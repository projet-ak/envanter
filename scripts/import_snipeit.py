"""Snipe-IT'ten veriyi yeni envanter sistemine taşır (salt-okunur, idempotent).

Kullanım:
    SNIPEIT_URL=https://snipe.ornek.com SNIPEIT_TOKEN=xxx \\
    DATABASE_URL=postgresql+psycopg2://... \\
    python scripts/import_snipeit.py

Notlar:
- Snipe-IT'in REST API'sini kullanır (DB erişimi gerekmez, sürümden bağımsız).
- Her kayıt `external_id` ile eşlenir; script tekrar çalıştırıldığında veriyi
  çoğaltmaz, günceller. Yani güvenle birden çok kez çalıştırabilirsin.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo kökünü import yoluna ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datetime as dt  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #
def _client() -> httpx.Client:
    if not settings.snipeit_url or not settings.snipeit_token:
        raise SystemExit("SNIPEIT_URL ve SNIPEIT_TOKEN ortam değişkenleri gerekli.")
    return httpx.Client(
        base_url=settings.snipeit_url.rstrip("/") + "/api/v1",
        headers={
            "Authorization": f"Bearer {settings.snipeit_token}",
            "Accept": "application/json",
        },
        timeout=60,
    )


def fetch_all(client: httpx.Client, path: str, limit: int | None = None) -> list[dict]:
    """Snipe-IT'in sayfalı listesini çeker. `limit` verilirse o kadar kayıtla sınırlar."""
    rows: list[dict] = []
    offset = 0
    page = 100
    while True:
        resp = client.get(path, params={"limit": page, "offset": offset})
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("rows", [])
        rows.extend(batch)
        total = data.get("total", len(rows))
        offset += page
        if limit and len(rows) >= limit:
            return rows[:limit]
        if offset >= total or not batch:
            break
    return rows


def parse_date(value) -> dt.date | None:
    if not value:
        return None
    raw = value.get("date") if isinstance(value, dict) else value
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def parse_float(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def nested_id(value) -> int | None:
    if isinstance(value, dict):
        return value.get("id")
    return value


def upsert(db: Session, model, external_id: int, defaults: dict):
    """external_id'ye göre var olanı günceller, yoksa oluşturur."""
    obj = db.scalar(select(model).where(model.external_id == external_id))
    if obj is None:
        obj = model(external_id=external_id, **defaults)
        db.add(obj)
    else:
        for key, value in defaults.items():
            setattr(obj, key, value)
    return obj


def id_map(db: Session, model) -> dict[int, int]:
    """external_id -> yerel id eşlemesi."""
    rows = db.execute(
        select(model.external_id, model.id).where(model.external_id.is_not(None))
    ).all()
    return {ext: local for ext, local in rows}


# --------------------------------------------------------------------------- #
# İçe aktarım adımları
# --------------------------------------------------------------------------- #
def run(dry_run: bool = False, limit: int | None = None) -> None:
    Base.metadata.create_all(bind=engine)
    client = _client()
    db = SessionLocal()

    def step() -> None:
        # Kuru çalıştırmada veriyi yazmadan (flush) ilerle; sonunda geri al.
        db.flush() if dry_run else db.commit()

    def fetch(path: str) -> list[dict]:
        return fetch_all(client, path, limit=limit)

    if dry_run:
        print("⚠ KURU ÇALIŞTIRMA (dry-run): hiçbir şey kalıcı olarak yazılmayacak.\n")

    try:
        print("→ Kategoriler…")
        for row in fetch("/categories"):
            upsert(
                db,
                models.Category,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "type": _category_type(row.get("category_type")),
                },
            )
        step()

        print("→ Üreticiler…")
        for row in fetch("/manufacturers"):
            upsert(
                db,
                models.Manufacturer,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "url": row.get("url"),
                    "support_phone": row.get("support_phone"),
                    "support_email": row.get("support_email"),
                },
            )
        step()

        print("→ Tedarikçiler…")
        for row in fetch("/suppliers"):
            upsert(
                db,
                models.Supplier,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "address": _as_text(row.get("address")),
                    "phone": row.get("phone"),
                    "email": row.get("email"),
                },
            )
        step()

        print("→ Şirketler…")
        for row in fetch("/companies"):
            upsert(db, models.Company, row["id"], {"name": row.get("name") or "Adsız"})
        step()

        print("→ Durum etiketleri…")
        for row in fetch("/statuslabels"):
            upsert(
                db,
                models.StatusLabel,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "type": _status_type(row.get("type")),
                },
            )
        step()

        print("→ Lokasyonlar (1. geçiş)…")
        for row in fetch("/locations"):
            upsert(
                db,
                models.Location,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "address": _as_text(row.get("address")),
                    "city": row.get("city"),
                    "country": row.get("country"),
                },
            )
        step()
        # 2. geçiş: parent ilişkisi
        loc_map = id_map(db, models.Location)
        print("→ Lokasyonlar (parent ilişkisi)…")
        for row in fetch("/locations"):
            parent_ext = nested_id(row.get("parent"))
            if parent_ext and parent_ext in loc_map:
                obj = db.scalar(
                    select(models.Location).where(
                        models.Location.external_id == row["id"]
                    )
                )
                if obj:
                    obj.parent_id = loc_map[parent_ext]
        step()

        cat_map = id_map(db, models.Category)
        man_map = id_map(db, models.Manufacturer)
        print("→ Modeller…")
        for row in fetch("/models"):
            upsert(
                db,
                models.AssetModel,
                row["id"],
                {
                    "name": row.get("name") or "Adsız",
                    "model_number": row.get("model_number"),
                    "category_id": cat_map.get(nested_id(row.get("category"))),
                    "manufacturer_id": man_map.get(nested_id(row.get("manufacturer"))),
                    "notes": row.get("notes"),
                },
            )
        step()

        print("→ Kullanıcılar…")
        for row in fetch("/users"):
            upsert(
                db,
                models.User,
                row["id"],
                {
                    "first_name": row.get("first_name") or "Adsız",
                    "last_name": row.get("last_name"),
                    "username": row.get("username"),
                    "email": row.get("email"),
                    "employee_num": row.get("employee_num"),
                    "job_title": row.get("jobtitle"),
                    "department": _as_text(row.get("department")),
                    "location_id": loc_map.get(nested_id(row.get("location"))),
                    "notes": row.get("notes"),
                    "active": bool(row.get("activated", True)),
                },
            )
        step()

        model_map = id_map(db, models.AssetModel)
        status_map = id_map(db, models.StatusLabel)
        sup_map = id_map(db, models.Supplier)
        comp_map = id_map(db, models.Company)
        print("→ Varlıklar (1. geçiş: temel veri)…")
        for row in fetch("/hardware"):
            upsert(
                db,
                models.Asset,
                row["id"],
                {
                    "asset_tag": row.get("asset_tag") or f"SNIPE-{row['id']}",
                    "name": row.get("name"),
                    "serial": row.get("serial"),
                    "model_id": model_map.get(nested_id(row.get("model"))),
                    "status_id": status_map.get(nested_id(row.get("status_label"))),
                    "supplier_id": sup_map.get(nested_id(row.get("supplier"))),
                    "location_id": loc_map.get(
                        nested_id(row.get("rtd_location") or row.get("location"))
                    ),
                    "company_id": comp_map.get(nested_id(row.get("company"))),
                    "purchase_date": parse_date(row.get("purchase_date")),
                    "purchase_cost": parse_float(row.get("purchase_cost")),
                    "order_number": row.get("order_number"),
                    "warranty_months": _warranty(row.get("warranty_months")),
                    "notes": row.get("notes"),
                    "image_url": row.get("image"),
                    "custom": _custom_fields(row.get("custom_fields")),
                },
            )
        step()

        # 2. geçiş: zimmet (assigned_to) — tüm varlıklar/kullanıcılar var artık
        user_map = id_map(db, models.User)
        asset_map = id_map(db, models.Asset)
        print("→ Varlıklar (2. geçiş: zimmet)…")
        for row in fetch("/hardware"):
            assigned = row.get("assigned_to")
            if not assigned:
                continue
            obj = db.scalar(
                select(models.Asset).where(models.Asset.external_id == row["id"])
            )
            if obj is None:
                continue
            atype = (assigned.get("type") or "user").lower()
            aid = assigned.get("id")
            obj.last_checkout = _parse_datetime(row.get("last_checkout"))
            obj.expected_checkin = parse_date(row.get("expected_checkin"))
            if atype == "user" and user_map.get(aid):
                obj.assigned_type = models.AssignedType.user
                obj.assigned_user_id = user_map[aid]
            elif atype == "location" and loc_map.get(aid):
                obj.assigned_type = models.AssignedType.location
                obj.assigned_location_id = loc_map[aid]
            elif atype == "asset" and asset_map.get(aid):
                obj.assigned_type = models.AssignedType.asset
                obj.assigned_asset_id = asset_map[aid]
        step()

        # Diğer varlık türleri: aksesuar / sarf / bileşen / lisans
        def _stock_defaults(row: dict) -> dict:
            return {
                "name": row.get("name") or "Adsız",
                "model_number": row.get("model_number"),
                "category_id": cat_map.get(nested_id(row.get("category"))),
                "manufacturer_id": man_map.get(nested_id(row.get("manufacturer"))),
                "supplier_id": sup_map.get(nested_id(row.get("supplier"))),
                "location_id": loc_map.get(nested_id(row.get("location"))),
                "company_id": comp_map.get(nested_id(row.get("company"))),
                "purchase_date": parse_date(row.get("purchase_date")),
                "purchase_cost": parse_float(row.get("purchase_cost")),
                "order_number": row.get("order_number"),
                "notes": row.get("notes"),
                "qty": _int(row.get("qty"), 1),
                "min_qty": _int(row.get("min_amt"), 0),
            }

        print("→ Aksesuarlar…")
        for row in fetch("/accessories"):
            upsert(db, models.Accessory, row["id"], _stock_defaults(row))
        step()

        print("→ Sarf malzemeleri…")
        for row in fetch("/consumables"):
            upsert(db, models.Consumable, row["id"], _stock_defaults(row))
        step()

        print("→ Bileşenler…")
        for row in fetch("/components"):
            defaults = _stock_defaults(row)
            defaults["serial"] = row.get("serial")
            upsert(db, models.Component, row["id"], defaults)
        step()

        print("→ Lisanslar…")
        for row in fetch("/licenses"):
            upsert(db, models.License, row["id"], {
                "name": row.get("name") or "Adsız",
                "seats": _int(row.get("seats"), 1),
                "license_key": row.get("product_key"),
                "licensed_to_name": row.get("license_name"),
                "licensed_to_email": row.get("license_email"),
                "manufacturer_id": man_map.get(nested_id(row.get("manufacturer"))),
                "supplier_id": sup_map.get(nested_id(row.get("supplier"))),
                "company_id": comp_map.get(nested_id(row.get("company"))),
                "category_id": cat_map.get(nested_id(row.get("category"))),
                "purchase_date": parse_date(row.get("purchase_date")),
                "purchase_cost": parse_float(row.get("purchase_cost")),
                "order_number": row.get("order_number"),
                "expiration_date": parse_date(row.get("expiration_date")),
                "maintained": bool(row.get("maintained", False)),
                "notes": row.get("notes"),
            })
        step()

        _summary(db)
        if dry_run:
            db.rollback()
            print("\n⚠ KURU ÇALIŞTIRMA: değişiklikler geri alındı, kalıcı yazma yapılmadı.")
    finally:
        db.close()
        client.close()


# --------------------------------------------------------------------------- #
# Alan dönüştürücüler
# --------------------------------------------------------------------------- #
def _category_type(value) -> models.CategoryType:
    try:
        return models.CategoryType(str(value or "asset").lower())
    except ValueError:
        return models.CategoryType.asset


def _status_type(value) -> models.StatusType:
    try:
        return models.StatusType(str(value or "deployable").lower())
    except ValueError:
        return models.StatusType.deployable


def _as_text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("address")
    return value


def _int(value, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _warranty(value) -> int | None:
    if value in (None, ""):
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else None


def _custom_fields(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out: dict = {}
    for name, payload in value.items():
        if isinstance(payload, dict):
            out[name] = payload.get("value")
        else:
            out[name] = payload
    return out


def _parse_datetime(value) -> dt.datetime | None:
    if not value:
        return None
    raw = value.get("datetime") if isinstance(value, dict) else value
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _summary(db: Session) -> None:
    from sqlalchemy import func

    print("\n✓ İçe aktarım tamamlandı:")
    for label, model in [
        ("Kategori", models.Category),
        ("Üretici", models.Manufacturer),
        ("Tedarikçi", models.Supplier),
        ("Şirket", models.Company),
        ("Durum", models.StatusLabel),
        ("Lokasyon", models.Location),
        ("Model", models.AssetModel),
        ("Kullanıcı", models.User),
        ("Varlık", models.Asset),
        ("Aksesuar", models.Accessory),
        ("Sarf", models.Consumable),
        ("Bileşen", models.Component),
        ("Lisans", models.License),
    ]:
        count = db.scalar(select(func.count()).select_from(model))
        print(f"  - {label}: {count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Snipe-IT verisini içe aktar")
    parser.add_argument("--dry-run", action="store_true",
                        help="Yazmadan dene; ne aktarılacağını göster")
    parser.add_argument("--limit", type=int, default=None,
                        help="Her türden en fazla N kayıt (hızlı test için)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
