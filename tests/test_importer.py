"""Snipe-IT içe aktarım testi — gerçek Snipe-IT olmadan, sahte API yanıtlarıyla.

Eşlemenin doğru olduğunu ve scriptin idempotent (tekrar çalıştırılabilir)
olduğunu doğrular.
"""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base

# Sahte Snipe-IT API yanıtları (gerçek API şekline yakın)
FAKE = {
    "/categories": [{"id": 1, "name": "Laptop", "category_type": "asset"}],
    "/manufacturers": [{"id": 5, "name": "Dell", "url": "https://dell.com"}],
    "/suppliers": [{"id": 8, "name": "Tedarikçi A", "address": "İstanbul"}],
    "/companies": [{"id": 2, "name": "Şirket A"}],
    "/statuslabels": [{"id": 3, "name": "Hazır", "type": "deployable"}],
    "/locations": [{"id": 4, "name": "Depo", "parent": None}],
    "/models": [
        {"id": 7, "name": "Latitude 5440", "model_number": "5440",
         "category": {"id": 1}, "manufacturer": {"id": 5}}
    ],
    "/users": [
        {"id": 9, "first_name": "Ahmet", "last_name": "Yılmaz",
         "email": "ahmet@ornek.com", "location": {"id": 4}, "activated": True}
    ],
    "/hardware": [
        {
            "id": 11, "asset_tag": "BT-1", "name": "laptop1", "serial": "S1",
            "model": {"id": 7}, "status_label": {"id": 3}, "rtd_location": {"id": 4},
            "company": {"id": 2}, "supplier": {"id": 8},
            "purchase_cost": "1234.56", "warranty_months": "24 ay",
            "custom_fields": {"CPU": {"field": "_x", "value": "i7"}},
            "assigned_to": {"id": 9, "type": "user"},
            "last_checkout": None, "expected_checkin": None,
        }
    ],
}


def test_snipeit_import(tmp_path, monkeypatch):
    import scripts.import_snipeit as imp

    # Geçici DB'ye yönlendir
    url = f"sqlite:///{tmp_path / 'imp.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(imp, "engine", engine)
    monkeypatch.setattr(imp, "SessionLocal", Session)
    monkeypatch.setattr(imp, "Base", Base)

    # Ağı taklit et
    class _DummyClient:
        def close(self):
            pass

    monkeypatch.setattr(imp, "_client", lambda: _DummyClient())
    monkeypatch.setattr(imp, "fetch_all", lambda client, path: FAKE.get(path, []))

    imp.run()

    with Session() as db:
        # Sayılar
        assert db.scalar(select(func.count()).select_from(models.Category)) == 1
        assert db.scalar(select(func.count()).select_from(models.Asset)) == 1

        # Model ilişkileri external_id üzerinden doğru kuruldu mu?
        model = db.scalar(select(models.AssetModel))
        cat = db.scalar(select(models.Category))
        man = db.scalar(select(models.Manufacturer))
        assert model.category_id == cat.id
        assert model.manufacturer_id == man.id

        # Varlık: temel alanlar + özel alanlar + parse'lar
        asset = db.scalar(select(models.Asset))
        assert asset.asset_tag == "BT-1"
        assert asset.custom == {"CPU": "i7"}
        assert float(asset.purchase_cost) == 1234.56
        assert asset.warranty_months == 24  # "24 ay" -> 24

        # Zimmet doğru kullanıcıya bağlandı mı?
        user = db.scalar(select(models.User))
        assert asset.assigned_type == models.AssignedType.user
        assert asset.assigned_user_id == user.id
        assert asset.location_id is not None

    # İdempotency: tekrar çalıştır, sayılar artmamalı
    imp.run()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(models.Asset)) == 1
        assert db.scalar(select(func.count()).select_from(models.Category)) == 1
