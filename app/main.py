"""Envanter API — uygulama giriş noktası."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import (
    ag_urunleri, assets, auth, csv_io, detay, documents, dosyalar, excel_io,
    invoices, lookups, personel, reports, search, yedekleme,
)
from app.seed import seed_defaults

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Geliştirme kolaylığı: sqlite'ta tabloları otomatik oluştur.
    # Üretimde (PostgreSQL) şema, Alembic göçleriyle yönetilir:
    #   alembic upgrade head
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            seed_defaults(db)
    except Exception:
        # Tablolar henüz yoksa (göç çalıştırılmadıysa) sessizce geç.
        pass
    yield


_ONEK = settings.root_path.rstrip("/")

app = FastAPI(
    title="Envanter API",
    description="Esnek, stabil BT envanter yönetim sistemi (Snipe-IT alternatifi).",
    version=__version__,
    lifespan=lifespan,
    # Alt klasörde yayın (örn. /envanter): ön ek YALNIZCA üretilen adreslerde
    # (OpenAPI) kullanılır, yönlendirmeye karıştırılmaz.
    #
    # NEDEN root_path= DEĞİL: Nginx ön eki kırpar, yani uygulamaya "/ui/" gelir.
    # Kurucuya root_path verildiğinde StaticFiles bağlaması yolu ön ekle
    # bekliyor ve "/ui/" 404 dönüyor (uvicorn'a --root-path da verilmediyse).
    # servers= ile ön ek dokümana yansır, yönlendirme bozulmaz.
    # Üretimde uvicorn zaten --root-path alıyor; o da yalnızca scope'u ayarlar.
    servers=[{"url": _ONEK}] if _ONEK else None,
)

app.include_router(auth.router)
# /users/ara, lookups'ın /users/{item_id} yolundan ÖNCE kayıtlanmalı
app.include_router(personel.router)
for router in lookups.routers:
    app.include_router(router)
app.include_router(assets.router)
app.include_router(search.router)
app.include_router(csv_io.router)
app.include_router(documents.router)
app.include_router(reports.router)
app.include_router(invoices.router)
app.include_router(excel_io.router)
app.include_router(detay.router)
app.include_router(dosyalar.router)
app.include_router(yedekleme.router)
app.include_router(ag_urunleri.router)


@app.get("/", include_in_schema=False)
def root(request: Request):
    # Alt klasörde yayınlanırken doğru hedefe yönlendir (örn. /envanter/ui/)
    prefix = request.scope.get("root_path", "").rstrip("/")
    return RedirectResponse(url=f"{prefix}/ui/")


@app.get("/login", include_in_schema=False)
def login_sayfasi():
    """Ayrı giriş sayfası. `?redirect=/yol` ile giriş sonrası hedef verilebilir."""
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/health", tags=["Sistem"])
def health():
    return {"status": "ok", "surum": __version__}


# Basit web arayüzü (statik). /ui/ adresinde sunulur.
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
