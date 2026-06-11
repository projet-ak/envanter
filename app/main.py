"""Envanter API — uygulama giriş noktası."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.database import Base, SessionLocal, engine
from app.routers import assets, lookups, search
from app.seed import seed_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Geliştirme kolaylığı: tabloları oluştur + varsayılanları ekle.
    # Üretimde şema değişiklikleri için Alembic göçleri kullanılmalı.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    yield


app = FastAPI(
    title="Envanter API",
    description="Esnek, stabil BT envanter yönetim sistemi (Snipe-IT alternatifi).",
    version=__version__,
    lifespan=lifespan,
)

for router in lookups.routers:
    app.include_router(router)
app.include_router(assets.router)
app.include_router(search.router)


@app.get("/", tags=["Sistem"])
def root():
    return {
        "ad": "Envanter API",
        "surum": __version__,
        "dokuman": "/docs",
    }


@app.get("/health", tags=["Sistem"])
def health():
    return {"status": "ok"}
