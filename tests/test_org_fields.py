"""Kuruma özel alanların (demirbaş, barkod, IMEI, garanti vb.) testleri."""

import datetime as dt
import io


def test_asset_custom_org_fields(client):
    payload = {
        "asset_tag": "BT-100",
        "name": "Müdür Laptop",
        "demirbas_no": "DMR-2024-001",
        "muhasebe_kodu": "255.01",
        "fatura_no": "FTR-9988",
        "warranty_end": "2027-05-01",
        "barkod": "8690000000017",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "hostname": "IT-LAPTOP-01",
    }
    r = client.post("/assets", json=payload)
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["demirbas_no"] == "DMR-2024-001"
    assert asset["muhasebe_kodu"] == "255.01"
    assert asset["warranty_end"] == "2027-05-01"
    assert asset["hostname"] == "IT-LAPTOP-01"


def test_phone_fields(client):
    r = client.post("/assets", json={
        "asset_tag": "TEL-1", "name": "Şirket Telefonu",
        "imei": "356938035643809", "telefon_no": "05551112233",
        "sim_no": "8990011234567890123", "operator": "Turkcell",
    })
    assert r.status_code == 201
    a = r.json()
    assert a["imei"] == "356938035643809" and a["operator"] == "Turkcell"


def test_user_personnel_fields(client):
    r = client.post("/users", json={
        "first_name": "Ayşe", "last_name": "Demir", "employee_num": "P-042",
        "tckn": "12345678901", "sube": "Merkez", "telefon": "05001112233",
        "ise_giris": "2021-09-01", "department": "BT",
    })
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["tckn"] == "12345678901" and u["sube"] == "Merkez"
    assert u["ise_giris"] == "2021-09-01"
    assert u["role"] == "viewer"  # varsayılan rol


def test_search_finds_by_demirbas_and_barcode(client):
    client.post("/assets", json={"asset_tag": "BT-200", "demirbas_no": "DMR-777",
                                 "barkod": "1234567890128"})
    # demirbaş no ile
    r = client.post("/search", json={"q": "DMR-777"}).json()
    assert r["count"] == 1
    # barkod ile
    r2 = client.post("/search", json={"q": "1234567890128"}).json()
    assert r2["count"] == 1


def test_warranty_filter(client, db_session_factory):
    from app.ai.search import apply_filter
    from app.schemas import SearchFilter

    client.post("/assets", json={"asset_tag": "W-1", "warranty_end": "2025-01-01"})
    client.post("/assets", json={"asset_tag": "W-2", "warranty_end": "2030-01-01"})

    with db_session_factory() as db:
        res = apply_filter(db, SearchFilter(warranty_expiring_before=dt.date(2026, 1, 1)))
        assert [a.asset_tag for a in res] == ["W-1"]


def test_csv_roundtrip_with_custom_fields(client):
    client.post("/assets", json={"asset_tag": "CSV-X", "demirbas_no": "DMR-CSV",
                                 "barkod": "999", "hostname": "PC-9"})
    body = client.get("/io/assets.csv").text
    assert "demirbas_no" in body.splitlines()[0]
    assert "DMR-CSV" in body

    # İçe aktarımda da özel alanlar okunmalı
    csv_content = "asset_tag,demirbas_no,imei,warranty_end\nIMP-9,DMR-IMP,111222333,2028-03-15\n"
    files = {"file": ("a.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    assert client.post("/io/assets/import", files=files).json()["created"] == 1
    found = [a for a in client.get("/assets").json() if a["asset_tag"] == "IMP-9"][0]
    assert found["demirbas_no"] == "DMR-IMP"
    assert found["imei"] == "111222333"
    assert found["warranty_end"] == "2028-03-15"
