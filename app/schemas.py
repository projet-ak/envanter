"""Pydantic şemaları — API istek/yanıt modelleri."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    ActivityAction,
    AssignedType,
    CategoryType,
    DosyaTuru,
    StatusType,
    StokTuru,
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
    proje_kodu: str | None = None
    parent_id: int | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None


class LocationUpdate(BaseModel):
    name: str | None = None
    proje_kodu: str | None = None
    parent_id: int | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None


class LocationRead(ORMModel):
    id: int
    name: str
    proje_kodu: str | None = None
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
    tckn: str | None = None
    sube: str | None = None
    telefon: str | None = None
    ise_giris: dt.date | None = None
    isten_cikis: dt.date | None = None
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
    tckn: str | None = None
    sube: str | None = None
    telefon: str | None = None
    ise_giris: dt.date | None = None
    isten_cikis: dt.date | None = None
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
    tckn: str | None = None
    sube: str | None = None
    telefon: str | None = None
    ise_giris: dt.date | None = None
    isten_cikis: dt.date | None = None
    role: UserRole
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
    # Kuruma özel alanlar
    demirbas_no: str | None = None
    muhasebe_kodu: str | None = None
    fatura_no: str | None = None
    warranty_end: dt.date | None = None
    barkod: str | None = None
    imei: str | None = None
    mac_address: str | None = None
    ip_address: str | None = None
    hostname: str | None = None
    telefon_no: str | None = None
    sim_no: str | None = None
    operator: str | None = None
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
    # Kuruma özel alanlar
    demirbas_no: str | None = None
    muhasebe_kodu: str | None = None
    fatura_no: str | None = None
    warranty_end: dt.date | None = None
    barkod: str | None = None
    imei: str | None = None
    mac_address: str | None = None
    ip_address: str | None = None
    hostname: str | None = None
    telefon_no: str | None = None
    sim_no: str | None = None
    operator: str | None = None
    custom: dict | None = None


class AgUrunEkle(BaseModel):
    """Ağ ürünü ekleme — kategori/marka/model adla verilir, yoksa açılır."""

    tur: str = Field(description="switch, sfp, access_point, router, kabinet, diger")
    asset_tag: str | None = None
    serial: str | None = None
    marka: str | None = None
    model: str | None = None
    ad: str | None = None
    demirbas_no: str | None = None
    ip_address: str | None = None
    location_id: int | None = None
    status_id: int | None = None
    notes: str | None = None
    # SIM'li cihazlar (Superbox, Vinn, USB modem): hat künyesi teknik özellik
    # değil, varlığın kendi sütunlarıdır
    operator: str | None = None
    telefon_no: str | None = None
    sim_no: str | None = None
    imei: str | None = None
    ozellikler: dict[str, str] = Field(default_factory=dict)


class OzellikYaz(BaseModel):
    """Tek bir teknik özellik: hangi grupta, hangi alan, hangi değer."""

    grup: str = Field(min_length=1, max_length=80)
    ad: str = Field(min_length=1, max_length=120)
    deger: str = Field(default="", max_length=2000)


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
    # Kuruma özel alanlar
    demirbas_no: str | None = None
    muhasebe_kodu: str | None = None
    fatura_no: str | None = None
    warranty_end: dt.date | None = None
    barkod: str | None = None
    imei: str | None = None
    mac_address: str | None = None
    ip_address: str | None = None
    hostname: str | None = None
    telefon_no: str | None = None
    sim_no: str | None = None
    operator: str | None = None
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
# Cihaz dosya ekleri (görsel, imzalı zimmet formu, fatura…)
# --------------------------------------------------------------------------- #
class StockFileRead(ORMModel):
    """Aksesuar/sarf/bileşen/lisans kaydına bağlı dosya."""

    id: int
    kayit_turu: StokTuru
    kayit_id: int
    tur: DosyaTuru
    dosya_adi: str
    yol: str
    content_type: str | None = None
    boyut: int
    aciklama: str | None = None
    yukleyen: str | None = None
    created_at: dt.datetime


class UserFileRead(ORMModel):
    """Kişiye bağlı dosya (imzalı zimmet formu, tutanak…)."""

    id: int
    user_id: int
    tur: DosyaTuru
    dosya_adi: str
    yol: str
    content_type: str | None = None
    boyut: int
    aciklama: str | None = None
    yukleyen: str | None = None
    created_at: dt.datetime


class AssetFileRead(ORMModel):
    id: int
    asset_id: int
    tur: DosyaTuru
    dosya_adi: str
    yol: str
    content_type: str | None = None
    boyut: int
    aciklama: str | None = None
    yukleyen: str | None = None
    created_at: dt.datetime


# --------------------------------------------------------------------------- #
# Adet bazlı varlıklar: aksesuar / sarf malzeme / bileşen
# --------------------------------------------------------------------------- #
class StockBase(BaseModel):
    name: str
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    notes: str | None = None
    qty: int = 1
    min_qty: int = 0


class StockUpdate(BaseModel):
    name: str | None = None
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    notes: str | None = None
    qty: int | None = None
    min_qty: int | None = None


class StockRead(ORMModel):
    id: int
    name: str
    model_number: str | None = None
    category_id: int | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    company_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    notes: str | None = None
    qty: int
    min_qty: int


class ComponentCreate(StockBase):
    serial: str | None = None


class ComponentUpdate(StockUpdate):
    serial: str | None = None


class ComponentRead(StockRead):
    serial: str | None = None


class LicenseCreate(BaseModel):
    name: str
    seats: int = 1
    license_key: str | None = None
    licensed_to_name: str | None = None
    licensed_to_email: str | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    company_id: int | None = None
    category_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    expiration_date: dt.date | None = None
    maintained: bool = False
    notes: str | None = None


class LicenseUpdate(BaseModel):
    name: str | None = None
    seats: int | None = None
    license_key: str | None = None
    licensed_to_name: str | None = None
    licensed_to_email: str | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    company_id: int | None = None
    category_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    expiration_date: dt.date | None = None
    maintained: bool | None = None
    notes: str | None = None


class LicenseRead(ORMModel):
    id: int
    name: str
    seats: int
    license_key: str | None = None
    licensed_to_name: str | None = None
    licensed_to_email: str | None = None
    manufacturer_id: int | None = None
    supplier_id: int | None = None
    company_id: int | None = None
    category_id: int | None = None
    purchase_date: dt.date | None = None
    purchase_cost: float | None = None
    order_number: str | None = None
    expiration_date: dt.date | None = None
    maintained: bool
    notes: str | None = None


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
    warranty_expiring_before: dt.date | None = Field(
        None, description="Garantisi bu tarihten önce biten varlıklar"
    )
    limit: int = Field(50, ge=1, le=500)


class SearchRequest(BaseModel):
    q: str = Field(..., description="Doğal dil sorgusu, örn: 'boştaki Dell laptoplar'")
    limit: int = Field(50, ge=1, le=500)


# --------------------------------------------------------------------------- #
# Fatura / irsaliye okuma (Claude vision)
# --------------------------------------------------------------------------- #
class InvoiceLine(BaseModel):
    """Faturadan çıkarılan tek bir ürün kalemi."""

    ad: str = Field(..., description="Ürün/cihaz adı")
    marka: str | None = Field(None, description="Marka (Dell, HP, Apple...)")
    model: str | None = Field(None, description="Model adı veya numarası")
    adet: int = Field(1, ge=1, description="Kalem adedi")
    seri_no: str | None = Field(None, description="Varsa seri numarası")
    birim_fiyat: float | None = Field(None, description="KDV hariç birim fiyat")
    kategori: str | None = Field(
        None, description="Tahmini kategori: Dizüstü, Masaüstü, Monitör, Telefon vb."
    )


class InvoiceExtraction(BaseModel):
    """Faturanın tamamından çıkarılan bilgiler."""

    tedarikci: str | None = Field(None, description="Satıcı firma adı")
    fatura_no: str | None = Field(None, description="Fatura / irsaliye numarası")
    fatura_tarihi: dt.date | None = Field(None, description="Fatura tarihi")
    para_birimi: str | None = Field(None, description="TRY, USD, EUR")
    kalemler: list[InvoiceLine] = Field(default_factory=list)


class InvoiceImportLine(BaseModel):
    """Onaylanan kalemin envantere eklenme talebi."""

    ad: str
    adet: int = Field(1, ge=1, le=500)
    seri_no: str | None = None
    birim_fiyat: float | None = None
    asset_tag_prefix: str | None = Field(
        None, description="Etiket ön eki; boşsa otomatik üretilir"
    )


class InvoiceImportRequest(BaseModel):
    kalemler: list[InvoiceImportLine]
    fatura_no: str | None = None
    purchase_date: dt.date | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    status_id: int | None = None


class LabelRequest(BaseModel):
    """Toplu etiket üretimi isteği."""

    asset_ids: list[int] = Field(default_factory=list,
                                 description="Etiketi basılacak varlık id'leri")
    location_id: int | None = Field(None, description="Lokasyondaki tüm varlıklar")
    show_barcode: bool = Field(True, description="QR yanında Code128 barkod da bas")
    start_offset: int = Field(0, ge=0, lt=24,
                              description="Yarım kağıtta baştan atlanacak etiket sayısı")


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
    email: str | None = None
    department: str | None = None
    job_title: str | None = None
    telefon: str | None = None
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


# --------------------------------------------------------------------------- #
# Kullanıcı ayarları
# --------------------------------------------------------------------------- #
class ProfilGuncelle(BaseModel):
    """Kullanıcının kendi düzenleyebildiği alanlar (rol buraya dahil değil)."""

    first_name: str | None = Field(None, min_length=1, max_length=120)
    last_name: str | None = None
    email: str | None = None
    telefon: str | None = None


class ParolaDegistir(BaseModel):
    mevcut_parola: str
    yeni_parola: str = Field(min_length=8, max_length=200)


class HesapAyarla(BaseModel):
    """Yöneticinin bir personele giriş yetkisi vermesi / düzenlemesi."""

    username: str | None = Field(None, min_length=3, max_length=120)
    role: UserRole | None = None
    active: bool | None = None
    yeni_parola: str | None = Field(None, min_length=8, max_length=200)


class HesapRead(ORMModel):
    id: int
    username: str | None = None
    first_name: str
    last_name: str | None = None
    email: str | None = None
    department: str | None = None
    role: UserRole
    active: bool
    girebilir: bool = False        # parolası var mı (giriş yapabilir mi)
