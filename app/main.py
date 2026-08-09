"""Envanter API — uygulama giriş noktası."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import (
    ag_urunleri, assets, auth, csv_io, detay, documents, dosyalar, excel_io,
    invoices, lookups, personel, reports, search, stok_dosyalari,
    stok_hareket, yedekleme,
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

@app.middleware("http")
async def arayuz_onbellegi(request: Request, call_next):
    """Arayüz dosyaları her istekte sunucuyla doğrulansın.

    `no-cache` "önbellekleme yapma" demek değildir: tarayıcı dosyayı saklar ama
    kullanmadan önce sorar; değişmediyse 304 döner (StaticFiles Last-Modified
    gönderiyor), değiştiyse yenisi gelir. Böylece her güncellemeden sonra
    kullanıcılardan Ctrl+F5 istemek gerekmez.
    """
    response = await call_next(request)
    yol = request.url.path
    if yol.startswith("/ui") or yol in ("/login", "/stil", "/betik"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


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
app.include_router(stok_dosyalari.router)
app.include_router(stok_hareket.router)
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


@app.get("/stil", include_in_schema=False)
def stil():
    """Arayüz stili — bilerek UZANTISIZ adres.

    aaPanel gibi paneller site ayarına `location ~ .*\\.(js|css)$` türü regex
    bloklar koyar; bunlar alt klasör vekilinden önce eşleşir ve
    /envanter/ui/stil.css isteğini PHP kökünde arayıp 404 döndürür (sayfa
    çıplak açılır). Uzantı olmayınca o bloklar hiç eşleşemez — istek her
    koşulda uygulamaya ulaşır. `media_type` elle verilir; tarayıcılar yanlış
    MIME'lı stil dosyasını reddeder.
    """
    return FileResponse(STATIC_DIR / "stil.css", media_type="text/css")


@app.get("/betik", include_in_schema=False)
def betik():
    """Arayüz betiği — uzantısız adres (gerekçe için /stil'e bakın)."""
    return FileResponse(STATIC_DIR / "uygulama.js",
                        media_type="application/javascript")


@app.get("/logo", include_in_schema=False)
def logo():
    """Kurum logosu. Dosya yoksa 204 döner — 404 gibi konsola hata düşmez.

    Logoyu etkinleştirmek için `app/static/logo.png` (ya da .jpg/.svg/.webp)
    koymak yeterlidir;
    arayüz bu ucu yoklar, 200 gelirse emoji yerine logoyu gösterir.
    """
    for ad, tip in (("logo.png", "image/png"), ("logo.jpg", "image/jpeg"),
                    ("logo.jpeg", "image/jpeg"), ("logo.svg", "image/svg+xml"),
                    ("logo.webp", "image/webp")):
        yol = STATIC_DIR / ad
        if yol.exists():
            return FileResponse(yol, media_type=tip)
    return Response(status_code=204)


@app.get("/logo2", include_in_schema=False)
def logo2():
    """İkinci kurum logosu (Taahhüt) — giriş ekranındaki ikinci rozet.

    scripts/logo-kur.py üretir; dosya yoksa 204 döner ve rozet hiç görünmez.
    """
    yol = STATIC_DIR / "logo2.png"
    if yol.exists():
        return FileResponse(yol, media_type="image/png")
    return Response(status_code=204)


@app.get("/health", tags=["Sistem"])
def health():
    return {"status": "ok", "surum": __version__}


# Basit web arayüzü (statik). /ui/ adresinde sunulur.
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
