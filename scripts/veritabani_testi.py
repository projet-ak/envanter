#!/usr/bin/env python3
"""Veritabanı uyumluluk testi — geçişten ÖNCE çalıştır.

Verilen veritabanında geçici bir test veritabanı oluşturur, tüm göçleri
uygular, gerçek işlemleri dener (Türkçe karakterler, JSON özel alanlar,
enum'lar, zimmet, PDF), sonra temizler. Mevcut verine dokunmaz.

Kullanım:
    ./.venv/bin/python scripts/veritabani_testi.py \\
        "mysql+pymysql://kullanici:parola@localhost:3306/envanter?charset=utf8mb4"

    # veya .env içindeki DATABASE_URL ile:
    ./.venv/bin/python scripts/veritabani_testi.py
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

GECTI, KALDI = [], []


def kontrol(ad: str, fn):
    try:
        fn()
        GECTI.append(ad)
        print(f"  \033[32m✓\033[0m {ad}")
    except Exception as exc:
        KALDI.append((ad, exc))
        print(f"  \033[31m✗\033[0m {ad}\n      {type(exc).__name__}: {exc}")


def main() -> int:
    from app.config import settings

    ham_url = sys.argv[1] if len(sys.argv) > 1 else settings.database_url
    url = make_url(ham_url)
    lehce = url.get_backend_name()

    print(f"\n\033[1;36m→ Veritabanı: {lehce}  ({url.host or 'yerel dosya'})\033[0m")

    if lehce == "sqlite":
        print("\033[33m⚠ SQLite ile test anlamlı değil; üretim veritabanı URL'i ver.\033[0m")
        return 1

    # ---- Geçici test veritabanı ----
    test_db = f"envanter_test_{uuid.uuid4().hex[:8]}"
    yonetim_url = url.set(database="mysql" if lehce == "mysql" else "postgres")
    yonetim = create_engine(yonetim_url, isolation_level="AUTOCOMMIT")

    print(f"→ Geçici test veritabanı oluşturuluyor: {test_db}")
    try:
        with yonetim.connect() as conn:
            if lehce == "mysql":
                conn.execute(text(
                    f"CREATE DATABASE `{test_db}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
            else:
                conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    except Exception as exc:
        print(f"\033[31m✗ Test veritabanı oluşturulamadı: {exc}\033[0m")
        print("  Kullanıcının CREATE DATABASE yetkisi var mı?")
        return 1

    # DİKKAT: str(URL) parolayı '***' olarak maskeler; gerçek URL için
    # render_as_string(hide_password=False) kullanılmalı.
    test_url = url.set(database=test_db).render_as_string(hide_password=False)
    try:
        _testleri_calistir(test_url, lehce)
    finally:
        print(f"\n→ Temizlik: {test_db} siliniyor")
        with yonetim.connect() as conn:
            tirnak = "`" if lehce == "mysql" else '"'
            conn.execute(text(f"DROP DATABASE {tirnak}{test_db}{tirnak}"))
        yonetim.dispose()

    # ---- Özet ----
    print("\n" + "═" * 60)
    if KALDI:
        print(f"\033[1;31m✗ {len(KALDI)} test BAŞARISIZ, {len(GECTI)} geçti\033[0m")
        print("\nBu veritabanına geçmek GÜVENLİ DEĞİL. Başarısız testler:")
        for ad, exc in KALDI:
            print(f"  • {ad}: {type(exc).__name__}")
        return 1
    print(f"\033[1;32m✓ {len(GECTI)} testin tamamı geçti — bu veritabanı kullanılabilir\033[0m")
    return 0


def _testleri_calistir(test_url: str, lehce: str) -> None:
    import os
    os.environ["DATABASE_URL"] = test_url

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))

    print("\n\033[1m1) Göçler\033[0m")
    kontrol("Tüm göçler uygulanıyor (upgrade head)",
            lambda: command.upgrade(cfg, "head"))
    kontrol("Geri alma çalışıyor (downgrade base)",
            lambda: command.downgrade(cfg, "base"))
    kontrol("Geri alma sonrası tekrar kurulum",
            lambda: command.upgrade(cfg, "head"))

    engine = create_engine(test_url)

    def tablolar_var():
        from sqlalchemy import inspect
        mevcut = set(inspect(engine).get_table_names())
        gerekli = {"assets", "users", "categories", "licenses", "activity_logs"}
        eksik = gerekli - mevcut
        assert not eksik, f"eksik tablolar: {eksik}"

    kontrol("Beklenen tablolar oluştu", tablolar_var)

    print("\n\033[1m2) Veri işlemleri\033[0m")
    from sqlalchemy.orm import sessionmaker

    from app import models
    from app.auth import hash_password
    from app.seed import seed_defaults

    Session = sessionmaker(bind=engine)

    def turkce_ve_json():
        with Session() as db:
            seed_defaults(db)
            u = models.User(first_name="Şükrü", last_name="Öztürkoğlu",
                            username="test_kullanici", department="Bilgi İşlem",
                            sube="Kadıköy Şubesi", tckn="12345678901",
                            password_hash=hash_password("x"),
                            role=models.UserRole.admin)
            a = models.Asset(asset_tag="TEST-0001", name='Monitör 27" Çığır',
                             serial="SN-ĞŞİÇÖÜ-1", demirbas_no="DMR-2026-001",
                             custom={"CPU": "i7", "Açıklama": "Türkçe değer ĞŞİÇÖÜ"},
                             purchase_cost=28500.75,
                             warranty_end=dt.date(2028, 5, 1))
            db.add_all([u, a])
            db.commit()

            # Geri okuma — karakterler ve JSON bozulmamalı
            okunan = db.query(models.Asset).filter_by(asset_tag="TEST-0001").one()
            assert okunan.name == 'Monitör 27" Çığır', f"ad bozuldu: {okunan.name}"
            assert okunan.serial == "SN-ĞŞİÇÖÜ-1", f"seri bozuldu: {okunan.serial}"
            assert okunan.custom["Açıklama"] == "Türkçe değer ĞŞİÇÖÜ", \
                f"JSON bozuldu: {okunan.custom}"
            assert float(okunan.purchase_cost) == 28500.75
            assert okunan.warranty_end == dt.date(2028, 5, 1)
            kisi = db.query(models.User).filter_by(username="test_kullanici").one()
            assert kisi.last_name == "Öztürkoğlu"
            assert kisi.role == models.UserRole.admin, "enum bozuldu"

    kontrol("Türkçe karakterler, JSON özel alanlar ve enum'lar", turkce_ve_json)

    def zimmet_akisi():
        with Session() as db:
            a = db.query(models.Asset).filter_by(asset_tag="TEST-0001").one()
            u = db.query(models.User).filter_by(username="test_kullanici").one()
            a.assigned_type = models.AssignedType.user
            a.assigned_user_id = u.id
            a.last_checkout = dt.datetime.now(dt.timezone.utc)
            db.add(models.ActivityLog(action=models.ActivityAction.checkout,
                                      item_type="asset", item_id=a.id,
                                      note="Test zimmet",
                                      changes={"eski": None, "yeni": "zimmetli"}))
            db.commit()
            kayit = db.query(models.ActivityLog).filter_by(item_id=a.id).one()
            assert kayit.action == models.ActivityAction.checkout
            assert kayit.changes["yeni"] == "zimmetli", "log JSON bozuldu"

    kontrol("Zimmet akışı ve geçmiş kaydı", zimmet_akisi)

    def benzersiz_etiket():
        from sqlalchemy.exc import IntegrityError
        with Session() as db:
            db.add(models.Asset(asset_tag="TEST-0001"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return
            raise AssertionError("Aynı etiket ikinci kez eklenebildi (UNIQUE çalışmıyor)")

    kontrol("Benzersiz etiket kısıtı", benzersiz_etiket)

    print("\n\033[1m3) Uygulama katmanı\033[0m")

    def api_calisiyor():
        from fastapi.testclient import TestClient

        from app.auth import create_access_token
        from app.database import get_db
        from app.main import app

        def override():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        try:
            with Session() as db:
                kisi = db.query(models.User).filter_by(username="test_kullanici").one()
                jeton = create_access_token(kisi)
            c = TestClient(app)
            h = {"Authorization": f"Bearer {jeton}"}
            assert c.get("/assets", headers=h).status_code == 200
            ozet = c.get("/reports/ozet", headers=h)
            assert ozet.status_code == 200, ozet.text
            assert ozet.json()["varlik_toplam"] >= 1
            arama = c.post("/search", json={"q": "TEST-0001"}, headers=h)
            assert arama.status_code == 200 and arama.json()["count"] == 1
        finally:
            app.dependency_overrides.clear()

    kontrol("API: listeleme, raporlar, arama", api_calisiyor)

    def pdf_uretimi():
        with Session() as db:
            a = db.query(models.Asset).filter_by(asset_tag="TEST-0001").one()
            u = db.query(models.User).filter_by(username="test_kullanici").one()
            from app.pdf.zimmet import build_zimmet_pdf
            pdf = build_zimmet_pdf(assets=[a], user=u, doc_type="zimmet")
            assert pdf[:4] == b"%PDF" and len(pdf) > 1000

    kontrol("Zimmet tutanağı PDF üretimi", pdf_uretimi)

    engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
