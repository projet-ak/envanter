"""Pydantic şemaları — API istek/yanıt modelleri."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    ActivityAction,
    AssignedType,
    CategoryType,
    StatusType,
    UserRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Referans tabloları
# --------------------------------------------------------------------------- #
class CompanyCreate(BaseModel):
    name: str


class CompanyUpdate(BaseModel):
    name: str | None = None


class CompanyRead(ORMModel):
    id: int
    name: str


class LocationCreate(BaseModel):
    name: str
    parent_id: int | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None


class LocationUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None


class LocationRead(ORMModel):
    id: int
    name: str
    parent_id: int | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None


class ManufacturerCreate(BaseModel):
    name: str
    url: str | None = None
    support_phone: str | None = None
    support_email: str | None = None


class ManufacturerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    support_phone: str | None = None
    support_email: str | None = None


class ManufacturerRead(ORMModel):
    id: int
    name: str
    url: str | None = None
    support_phone: str | None = None
    support_email: str | None = None


class SupplierCreate(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class SupplierRead(ORMModel):
    id: int
    name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class CategoryCreate(BaseModel):
    name: str
    type: CategoryType = CategoryType.asset


class CategoryUpdate(BaseModel):
    name: str | None = None
    type: CategoryType | None = None


class CategoryRead(ORMModel):
    id: int
    name: str
    type: CategoryType


class StatusLabelCreate(BaseModel):
    name: str
    type: StatusType = StatusType.deployable
    notes: str | None = None


class StatusLabelUpdate(BaseModel):
    name: str | None = None
    type: StatusType | None = None
    notes: str | None = None


class StatusLabelRead(ORMModel):
    id: int
    name: str
    type: StatusType
    notes: str | None = None


class AssetModelCreate(BaseModel):
    name: str
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    notes: str | None = None


class AssetModelUpdate(BaseModel):
    name: str | None = None
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    notes: str | None = None


class AssetModelRead(ORMModel):
    id: int
    name: str
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Kullanıcılar
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    first_name: str
    last_name: str | None = None
    username: str | None = None
    email: str | None = None
    employee_num: str | None = None
    job_title: str | None = None
    department: str | None = None
    location_id: int | None = None
    manager_id: int | None = None
    notes: str | None = None
    active: bool = True


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    email: str | None = None
    employee_num: str | None = None
    job_title: str | None = None
    department: str | None = None
    location_id: int | None = None
    manager_id: int | None = None
    notes: str | None = None
    active: bool | None = None


class UserRead(ORMModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    email: str | None = None
    employee_num: str | None = None
    job_title: str | None = None
    department: str | None = None
    location_id: int | None = None
    active: bool


# --------------------------------------------------------------------------- #
# Özel alan tanımları
# --------------------------------------------------------------------------- #
class CustomFieldCreate(BaseModel):
    name: str
    element: str = "text"
    options: dict | None = None
    help_text: str | None = None
    required: bool = False


class CustomFieldUpdate(BaseModel):
    name: str | None = None
    element: str | None = None
    options: dict | None = None
    help_text: str | None = None
    required: bool | None = None


class CustomFieldRead(ORMModel):
    id: int
    name: str
    element: str
    options: dict | None = None
    help_text: str | None = None
    required: bool


# --------------------------------------------------------------------------- #
# Varlıklar (assets)
# --------------------------------------------------------------------------- #
class AssetBase(BaseModel):
    asset_tag: str
    name: str | None = None
    serial: str | None = None
    model_id: int | None = None
    status_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    warranty_months: int | None = None
    notes: str | None = None
    image_url: str | None = None
    custom: dict = Field(default_factory=dict)


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    asset_tag: str | None = None
    name: str | None = None
    serial: str | None = None
    model_id: int | None = None
    status_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    warranty_months: int | None = None
    notes: str | None = None
    image_url: str | None = None
    custom: dict | None = None


class AssetRead(ORMModel):
    id: int
    asset_tag: str
    name: str | None = None
    serial: str | None = None
    model_id: int | None = None
    status_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    warranty_months: int | None = None
    notes: str | None = None
    image_url: str | None = None
    custom: dict = Field(default_factory=dict)
    assigned_type: AssignedType | None = None
    assigned_user_id: int | None = None
    assigned_location_id: int | None = None
    assigned_asset_id: int | None = None
    last_checkout: dt.datetime | None = None
    expected_checkin: dt.date | None = None


class CheckoutRequest(BaseModel):
    assigned_type: AssignedType = AssignedType.user
    assigned_id: int = Field(..., description="Hedefin id'si (kullanıcı/lokasyon/varlık)")
    expected_checkin: dt.date | None = None
    note: str | None = None
    actor: str | None = None


class CheckinRequest(BaseModel):
    location_id: int | None = Field(None, description="İade sonrası gideceği lokasyon")
    note: str | None = None
    actor: str | None = None


class ActivityLogRead(ORMModel):
    id: int
    action: ActivityAction
    item_type: str
    item_id: int
    target_type: str | None = None
    target_id: int | None = None
    note: str | None = None
    changes: dict | None = None
    actor: str | None = None
    created_at: dt.datetime


# --------------------------------------------------------------------------- #
# Doğal dil arama
# --------------------------------------------------------------------------- #
class SearchFilter(BaseModel):
    """Claude'un doğal dil sorgusunu çevirdiği yapısal filtre."""

    text: str | None = Field(
        None, description="Ad/etiket/seri no/not içinde geçen serbest metin"
    )
    category: str | None = Field(None, description="Kategori adı")
    manufacturer: str | None = Field(None, description="Üretici adı")
    model: str | None = Field(None, description="Model adı")
    status: str | None = Field(None, description="Durum etiketi adı")
    location: str | None = Field(None, description="Lokasyon adı")
    assigned_to: str | None = Field(
        None, description="Zimmetli kullanıcının adı/e-postası"
    )
    only_unassigned: bool | None = Field(
        None, description="Sadece zimmetsiz (boştaki) varlıklar"
    )
    only_assigned: bool | None = Field(None, description="Sadece zimmetli varlıklar")
    purchased_after: dt.date | None = None
    purchased_before: dt.date | None = None
    limit: int = Field(50, ge=1, le=500)


class SearchRequest(BaseModel):
    q: str = Field(..., description="Doğal dil sorgusu, örn: 'boştaki Dell laptoplar'")
    limit: int = Field(50, ge=1, le=500)


class SearchResponse(BaseModel):
    query: str
    interpreted_filter: SearchFilter
    count: int
    results: list[AssetRead]
    used_ai: bool


# --------------------------------------------------------------------------- #
# Kimlik doğrulama
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(ORMModel):
    id: int
    username: str | None = None
    first_name: str
    last_name: str | None = None
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser
