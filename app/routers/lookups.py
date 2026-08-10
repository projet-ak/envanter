"""Referans tabloları için CRUD uçları (fabrikadan üretilir)."""

from app import models, schemas
from app.crud_factory import make_crud_router

companies = make_crud_router(
    model=models.Company,
    create_schema=schemas.CompanyCreate,
    update_schema=schemas.CompanyUpdate,
    read_schema=schemas.CompanyRead,
    prefix="/companies",
    essiz_ad=True,
    tag="Şirketler",
)

locations = make_crud_router(
    model=models.Location,
    create_schema=schemas.LocationCreate,
    update_schema=schemas.LocationUpdate,
    read_schema=schemas.LocationRead,
    prefix="/locations",
    essiz_ad=True,
    tag="Lokasyonlar",
)

manufacturers = make_crud_router(
    model=models.Manufacturer,
    create_schema=schemas.ManufacturerCreate,
    update_schema=schemas.ManufacturerUpdate,
    read_schema=schemas.ManufacturerRead,
    prefix="/manufacturers",
    essiz_ad=True,
    tag="Üreticiler",
)

suppliers = make_crud_router(
    model=models.Supplier,
    create_schema=schemas.SupplierCreate,
    update_schema=schemas.SupplierUpdate,
    read_schema=schemas.SupplierRead,
    prefix="/suppliers",
    essiz_ad=True,
    tag="Tedarikçiler",
)

categories = make_crud_router(
    model=models.Category,
    create_schema=schemas.CategoryCreate,
    update_schema=schemas.CategoryUpdate,
    read_schema=schemas.CategoryRead,
    prefix="/categories",
    essiz_ad=True,
    tag="Kategoriler",
)

status_labels = make_crud_router(
    model=models.StatusLabel,
    create_schema=schemas.StatusLabelCreate,
    update_schema=schemas.StatusLabelUpdate,
    read_schema=schemas.StatusLabelRead,
    prefix="/status-labels",
    tag="Durum Etiketleri",
)

asset_models = make_crud_router(
    model=models.AssetModel,
    create_schema=schemas.AssetModelCreate,
    update_schema=schemas.AssetModelUpdate,
    read_schema=schemas.AssetModelRead,
    prefix="/models",
    tag="Modeller",
)

users = make_crud_router(
    model=models.User,
    create_schema=schemas.UserCreate,
    update_schema=schemas.UserUpdate,
    read_schema=schemas.UserRead,
    prefix="/users",
    tag="Kullanıcılar",
)

custom_fields = make_crud_router(
    model=models.CustomField,
    create_schema=schemas.CustomFieldCreate,
    update_schema=schemas.CustomFieldUpdate,
    read_schema=schemas.CustomFieldRead,
    prefix="/custom-fields",
    tag="Özel Alanlar",
)

accessories = make_crud_router(
    model=models.Accessory,
    create_schema=schemas.StockBase,
    update_schema=schemas.StockUpdate,
    read_schema=schemas.StockRead,
    prefix="/accessories",
    tag="Aksesuarlar",
)

consumables = make_crud_router(
    model=models.Consumable,
    create_schema=schemas.StockBase,
    update_schema=schemas.StockUpdate,
    read_schema=schemas.StockRead,
    prefix="/consumables",
    tag="Sarf Malzemeleri",
)

components = make_crud_router(
    model=models.Component,
    create_schema=schemas.ComponentCreate,
    update_schema=schemas.ComponentUpdate,
    read_schema=schemas.ComponentRead,
    prefix="/components",
    tag="Bileşenler",
)

licenses = make_crud_router(
    model=models.License,
    create_schema=schemas.LicenseCreate,
    update_schema=schemas.LicenseUpdate,
    read_schema=schemas.LicenseRead,
    prefix="/licenses",
    tag="Lisanslar",
)

routers = [
    companies,
    locations,
    manufacturers,
    suppliers,
    categories,
    status_labels,
    asset_models,
    users,
    custom_fields,
    accessories,
    consumables,
    components,
    licenses,
]
