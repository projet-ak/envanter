"""ORM modelleri — Snipe-IT'in çekirdek varlıklarını esnek biçimde modeller.

Tasarım notları:
- `external_id`: Snipe-IT'teki orijinal kayıt id'si. İçe aktarım bu sayede
  tekrarlanabilir (idempotent) olur ve ilişkiler doğru kurulur.
- `Asset.custom`: özel alanlar JSON olarak tutulur → şema değiştirmeden
  istediğin kadar alan ekleyebilirsin (Snipe-IT custom fields'in esnek hali).
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --------------------------------------------------------------------------- #
# Mixin'ler
# --------------------------------------------------------------------------- #
class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalMixin:
    """Snipe-IT'ten içe aktarımda orijinal id eşlemesi."""

    external_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)


# --------------------------------------------------------------------------- #
# Enum'lar
# --------------------------------------------------------------------------- #
class CategoryType(str, enum.Enum):
    asset = "asset"
    accessory = "accessory"
    consumable = "consumable"
    component = "component"
    license = "license"


class StatusType(str, enum.Enum):
    deployable = "deployable"      # Kullanıma hazır
    pending = "pending"            # Beklemede
    archived = "archived"          # Arşiv
    undeployable = "undeployable"  # Kullanılamaz (arızalı vb.)


class AssignedType(str, enum.Enum):
    user = "user"
    location = "location"
    asset = "asset"


class UserRole(str, enum.Enum):
    admin = "admin"    # Her şey + kullanıcı yönetimi
    editor = "editor"  # Okuma + yazma
    viewer = "viewer"  # Sadece okuma


class ActivityAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    checkout = "checkout"
    checkin = "checkin"
    audit = "audit"


# --------------------------------------------------------------------------- #
# Referans (lookup) tabloları
# --------------------------------------------------------------------------- #
class Company(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)


class Location(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))

    parent: Mapped[Location | None] = relationship(remote_side="Location.id")


class Manufacturer(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str | None] = mapped_column(String(255))
    support_phone: Mapped[str | None] = mapped_column(String(60))
    support_email: Mapped[str | None] = mapped_column(String(120))


class Supplier(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(120))


class Category(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[CategoryType] = mapped_column(
        Enum(CategoryType), default=CategoryType.asset
    )


class StatusLabel(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "status_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[StatusType] = mapped_column(
        Enum(StatusType), default=StatusType.deployable
    )
    notes: Mapped[str | None] = mapped_column(Text)


class AssetModel(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "asset_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    model_number: Mapped[str | None] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("manufacturers.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    category: Mapped[Category | None] = relationship()
    manufacturer: Mapped[Manufacturer | None] = relationship()


# --------------------------------------------------------------------------- #
# Kullanıcılar (çalışanlar)
# --------------------------------------------------------------------------- #
class User(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    username: Mapped[str | None] = mapped_column(String(120), index=True)
    email: Mapped[str | None] = mapped_column(String(180), index=True)
    employee_num: Mapped[str | None] = mapped_column(String(60), index=True)
    job_title: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- Kuruma özel personel alanları ---
    tckn: Mapped[str | None] = mapped_column(String(11), index=True)
    sube: Mapped[str | None] = mapped_column(String(120))
    telefon: Mapped[str | None] = mapped_column(String(40))
    ise_giris: Mapped[dt.date | None] = mapped_column(Date)

    # Kimlik doğrulama (giriş yapabilen kullanıcılar için)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer)

    location: Mapped[Location | None] = relationship()
    manager: Mapped[User | None] = relationship(remote_side="User.id")

    @property
    def full_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))


# --------------------------------------------------------------------------- #
# Özel alan tanımları (kayıt defteri) — doğrulama/UI için
# --------------------------------------------------------------------------- #
class CustomField(Base, TimestampMixin):
    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    element: Mapped[str] = mapped_column(String(40), default="text")
    # text | textarea | number | date | checkbox | select
    options: Mapped[dict | None] = mapped_column(JSON)  # select için seçenekler
    help_text: Mapped[str | None] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- #
# Donanım varlıkları (assets)
# --------------------------------------------------------------------------- #
class Asset(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    serial: Mapped[str | None] = mapped_column(String(255), index=True)

    model_id: Mapped[int | None] = mapped_column(ForeignKey("asset_models.id"))
    status_id: Mapped[int | None] = mapped_column(ForeignKey("status_labels.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))

    purchase_date: Mapped[dt.date | None] = mapped_column(Date)
    purchase_cost: Mapped[float | None] = mapped_column(Numeric(15, 2))
    order_number: Mapped[str | None] = mapped_column(String(120))
    warranty_months: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))

    # --- Kuruma özel: demirbaş / muhasebe ---
    demirbas_no: Mapped[str | None] = mapped_column(String(120), index=True)
    muhasebe_kodu: Mapped[str | None] = mapped_column(String(120))
    fatura_no: Mapped[str | None] = mapped_column(String(120))
    warranty_end: Mapped[dt.date | None] = mapped_column(Date, index=True)

    # --- Etiketleme / teknik tanımlayıcılar ---
    barkod: Mapped[str | None] = mapped_column(String(120), index=True)
    imei: Mapped[str | None] = mapped_column(String(60), index=True)
    mac_address: Mapped[str | None] = mapped_column(String(60), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(60))
    hostname: Mapped[str | None] = mapped_column(String(120))

    # --- Telefon / hat ---
    telefon_no: Mapped[str | None] = mapped_column(String(40))
    sim_no: Mapped[str | None] = mapped_column(String(60))
    operator: Mapped[str | None] = mapped_column(String(60))

    # Esnek özel alanlar (şema değiştirmeden alan ekle)
    custom: Mapped[dict] = mapped_column(JSON, default=dict)

    # Zimmet (checkout) — kullanıcı / lokasyon / başka varlık
    assigned_type: Mapped[AssignedType | None] = mapped_column(Enum(AssignedType))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    assigned_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    last_checkout: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expected_checkin: Mapped[dt.date | None] = mapped_column(Date)

    model: Mapped[AssetModel | None] = relationship()
    status: Mapped[StatusLabel | None] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    location: Mapped[Location | None] = relationship(foreign_keys=[location_id])
    company: Mapped[Company | None] = relationship()
    assigned_user: Mapped[User | None] = relationship()
    assigned_location: Mapped[Location | None] = relationship(
        foreign_keys=[assigned_location_id]
    )

    @property
    def is_assigned(self) -> bool:
        return self.assigned_type is not None


# --------------------------------------------------------------------------- #
# Etkinlik / geçmiş kaydı (checkout/checkin/düzenleme audit'i)
# --------------------------------------------------------------------------- #
class StockMixin:
    """Adet bazlı varlıklar için ortak alanlar (aksesuar/sarf/bileşen)."""

    name: Mapped[str] = mapped_column(String(255), index=True)
    model_number: Mapped[str | None] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("manufacturers.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    purchase_date: Mapped[dt.date | None] = mapped_column(Date)
    purchase_cost: Mapped[float | None] = mapped_column(Numeric(15, 2))
    order_number: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    min_qty: Mapped[int] = mapped_column(Integer, default=0)


class Accessory(Base, StockMixin, TimestampMixin, ExternalMixin):
    __tablename__ = "accessories"
    id: Mapped[int] = mapped_column(primary_key=True)


class Consumable(Base, StockMixin, TimestampMixin, ExternalMixin):
    __tablename__ = "consumables"
    id: Mapped[int] = mapped_column(primary_key=True)


class Component(Base, StockMixin, TimestampMixin, ExternalMixin):
    __tablename__ = "components"
    id: Mapped[int] = mapped_column(primary_key=True)
    serial: Mapped[str | None] = mapped_column(String(255), index=True)


class License(Base, TimestampMixin, ExternalMixin):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    seats: Mapped[int] = mapped_column(Integer, default=1)
    license_key: Mapped[str | None] = mapped_column(String(255))
    licensed_to_name: Mapped[str | None] = mapped_column(String(255))
    licensed_to_email: Mapped[str | None] = mapped_column(String(180))
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("manufacturers.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    purchase_date: Mapped[dt.date | None] = mapped_column(Date)
    purchase_cost: Mapped[float | None] = mapped_column(Numeric(15, 2))
    order_number: Mapped[str | None] = mapped_column(String(120))
    expiration_date: Mapped[dt.date | None] = mapped_column(Date)
    maintained: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[ActivityAction] = mapped_column(Enum(ActivityAction))
    item_type: Mapped[str] = mapped_column(String(40))   # örn. "asset"
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSON)
    actor: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
