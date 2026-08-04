"""Envanter API — uygulama giriş noktası."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import (
    assets, auth, csv_io, documents, invoices, lookups, reports, search,
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


app = FastAPI(
    title="Envanter API",
    description="Esnek, stabil BT envanter yönetim sistemi (Snipe-IT alternatifi).",
    version=__version__,
    lifespan=lifespan,
    # Alt klasörde yayın (örn. /envanet) için; uvicorn --root-path ile de verilebilir.
    root_path=settings.root_path.rstrip("/"),
)

app.include_router(auth.router)
for router in lookups.routers:
    app.include_router(router)
app.include_router(assets.router)
app.include_router(search.router)
app.include_router(csv_io.router)
app.include_router(documents.router)
app.include_router(reports.router)
app.include_router(invoices.router)


@app.get("/", include_in_schema=False)
def root(request: Request):
    # Alt klasörde yayınlanırken doğru hedefe yönlendir (örn. /envanet/ui/)
    prefix = request.scope.get("root_path", "").rstrip("/")
    return RedirectResponse(url=f"{prefix}/ui/")


@app.get("/health", tags=["Sistem"])
def health():
    return {"status": "ok", "surum": __version__}


# Basit web arayüzü (statik). /ui/ adresinde sunulur.
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
