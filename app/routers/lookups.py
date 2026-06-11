"""Referans tabloları için CRUD uçları (fabrikadan üretilir)."""

from app import models, schemas
from app.crud_factory import make_crud_router

companies = make_crud_router(
    model=models.Company,
    create_schema=schemas.CompanyCreate,
    update_schema=schemas.CompanyUpdate,
    read_schema=schemas.CompanyRead,
    prefix="/companies",
    tag="Şirketler",
)

locations = make_crud_router(
    model=models.Location,
    create_schema=schemas.LocationCreate,
    update_schema=schemas.LocationUpdate,
    read_schema=schemas.LocationRead,
    prefix="/locations",
    tag="Lokasyonlar",
)

manufacturers = make_crud_router(
    model=models.Manufacturer,
    create_schema=schemas.ManufacturerCreate,
    update_schema=schemas.ManufacturerUpdate,
    read_schema=schemas.ManufacturerRead,
    prefix="/manufacturers",
    tag="Üreticiler",
)

suppliers = make_crud_router(
    model=models.Supplier,
    create_schema=schemas.SupplierCreate,
    update_schema=schemas.SupplierUpdate,
    read_schema=schemas.SupplierRead,
    prefix="/suppliers",
    tag="Tedarikçiler",
)

categories = make_crud_router(
    model=models.Category,
    create_schema=schemas.CategoryCreate,
    update_schema=schemas.CategoryUpdate,
    read_schema=schemas.CategoryRead,
    prefix="/categories",
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
]
