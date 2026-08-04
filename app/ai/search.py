"""Doğal dil arama — Claude sorguyu yapısal `SearchFilter`'a çevirir.

Güvenlik: Modele asla ham SQL yazdırmayız. Claude yalnızca yapısal bir filtre
(JSON) üretir; bu filtre parametreli SQLAlchemy sorgusuna çevrilir.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.schemas import SearchFilter

_SYSTEM = """Sen bir BT envanter sisteminin arama yardımcısısın.
Kullanıcının doğal dildeki (Türkçe veya İngilizce) sorgusunu yapısal bir
arama filtresine çevir. Sadece verilen şemaya uygun alanları doldur; emin
olmadığın alanları boş bırak.

Bugünün tarihi: {today}

Sistemdeki mevcut değerler (eşleştirmeye yardımcı olması için):
- Kategoriler: {categories}
- Üreticiler: {manufacturers}
- Durumlar: {statuses}
- Lokasyonlar: {locations}

Kurallar:
- "boştaki", "zimmetsiz", "depoda" gibi ifadeler → only_unassigned = true
- "zimmetli", "kullanımda", "birine verilmiş" → only_assigned = true
- Marka adı (Dell, HP, Apple...) genelde 'manufacturer' alanıdır.
- Model/cihaz türü adı 'model' veya serbest metin olabilir.
- Göreli tarihleri ("geçen yıl", "2023'ten sonra") gerçek tarihe çevir.
- Demirbaş no, barkod, IMEI, MAC adresi, hostname, telefon numarası gibi
  tanımlayıcılar 'text' alanına yazılır (serbest metin araması bunları kapsar).
- "garantisi biten/bitecek", "garanti süresi dolan" → warranty_expiring_before
  alanına ilgili tarihi yaz (örn. "önümüzdeki ay bitenler" → bugünden 1 ay sonrası).
"""


def _context(db: Session) -> dict[str, str]:
    def names(model, limit: int = 40) -> str:
        rows = db.scalars(select(model.name).limit(limit)).all()
        return ", ".join(r for r in rows if r) or "(yok)"

    return {
        "today": dt.date.today().isoformat(),
        "categories": names(models.Category),
        "manufacturers": names(models.Manufacturer),
        "statuses": names(models.StatusLabel),
        "locations": names(models.Location),
    }


def build_filter(query: str, db: Session) -> tuple[SearchFilter, bool]:
    """Sorguyu filtreye çevirir. (filtre, ai_kullanıldı_mı) döner.

    API anahtarı yoksa veya AI çağrısı başarısızsa, sorguyu serbest metin
    filtresi olarak kullanan güvenli bir geri-dönüş uygulanır.
    """
    if not settings.anthropic_api_key:
        return SearchFilter(text=query), False

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system = _SYSTEM.format(**_context(db))
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": query}],
            output_format=SearchFilter,
        )
        parsed = response.parsed_output
        if parsed is None:
            return SearchFilter(text=query), False
        return parsed, True
    except Exception:
        # AI kullanılamıyorsa sistem çalışmaya devam etsin.
        return SearchFilter(text=query), False


def apply_filter(db: Session, f: SearchFilter):
    """`SearchFilter`'ı parametreli SQLAlchemy sorgusuna çevirip çalıştırır."""
    stmt = select(models.Asset)

    if f.text:
        like = f"%{f.text}%"
        stmt = stmt.where(
            models.Asset.asset_tag.ilike(like)
            | models.Asset.serial.ilike(like)
            | models.Asset.name.ilike(like)
            | models.Asset.notes.ilike(like)
            | models.Asset.demirbas_no.ilike(like)
            | models.Asset.barkod.ilike(like)
            | models.Asset.imei.ilike(like)
            | models.Asset.mac_address.ilike(like)
            | models.Asset.hostname.ilike(like)
            | models.Asset.telefon_no.ilike(like)
        )

    if f.warranty_expiring_before:
        stmt = stmt.where(
            models.Asset.warranty_end.is_not(None),
            models.Asset.warranty_end <= f.warranty_expiring_before,
        )

    if f.status:
        stmt = stmt.join(models.StatusLabel, models.Asset.status_id == models.StatusLabel.id).where(
            models.StatusLabel.name.ilike(f"%{f.status}%")
        )

    if f.location:
        stmt = stmt.join(
            models.Location, models.Asset.location_id == models.Location.id
        ).where(models.Location.name.ilike(f"%{f.location}%"))

    if f.category or f.manufacturer or f.model:
        stmt = stmt.join(models.AssetModel, models.Asset.model_id == models.AssetModel.id)
        if f.model:
            stmt = stmt.where(models.AssetModel.name.ilike(f"%{f.model}%"))
        if f.category:
            stmt = stmt.join(
                models.Category, models.AssetModel.category_id == models.Category.id
            ).where(models.Category.name.ilike(f"%{f.category}%"))
        if f.manufacturer:
            stmt = stmt.join(
                models.Manufacturer,
                models.AssetModel.manufacturer_id == models.Manufacturer.id,
            ).where(models.Manufacturer.name.ilike(f"%{f.manufacturer}%"))

    if f.assigned_to:
        like = f"%{f.assigned_to}%"
        full_name = models.User.first_name + " " + func_coalesce(models.User.last_name)
        stmt = stmt.join(models.User, models.Asset.assigned_user_id == models.User.id).where(
            models.User.first_name.ilike(like)
            | models.User.last_name.ilike(like)
            | models.User.email.ilike(like)
            | full_name.ilike(like)
        )

    if f.only_unassigned:
        stmt = stmt.where(models.Asset.assigned_type.is_(None))
    if f.only_assigned:
        stmt = stmt.where(models.Asset.assigned_type.is_not(None))

    if f.purchased_after:
        stmt = stmt.where(models.Asset.purchase_date >= f.purchased_after)
    if f.purchased_before:
        stmt = stmt.where(models.Asset.purchase_date <= f.purchased_before)

    stmt = stmt.limit(f.limit)
    return db.scalars(stmt).all()


def func_coalesce(column):
    """last_name NULL olabileceğinden boş string'e indirger."""
    from sqlalchemy import func

    return func.coalesce(column, "")
