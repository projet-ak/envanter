"""Fatura okuma ve envantere aktarma testleri (AI çağrısı taklit edilir)."""

import datetime as dt
import io

import pytest

from app.schemas import InvoiceExtraction, InvoiceLine

FAKE_EXTRACTION = InvoiceExtraction(
    tedarikci="ABC Bilgisayar Ltd.",
    fatura_no="FTR-2026-0042",
    fatura_tarihi=dt.date(2026, 3, 15),
    para_birimi="TRY",
    kalemler=[
        InvoiceLine(ad="Dell Latitude 5440 Dizüstü", marka="Dell", model="Latitude 5440",
                    adet=3, birim_fiyat=28500.0, kategori="Dizüstü"),
        InvoiceLine(ad="Dell P2422H Monitör", marka="Dell", model="P2422H",
                    adet=2, birim_fiyat=4200.0, kategori="Monitör"),
    ],
)


@pytest.fixture
def fake_ai(monkeypatch):
    """extract_invoice'u sahte çıktıyla değiştirir."""
    import app.routers.invoices as inv
    monkeypatch.setattr(inv, "extract_invoice", lambda data, media: FAKE_EXTRACTION)


def _upload(client, content=b"fake-image-bytes", ctype="image/png"):
    return client.post("/invoices/oku",
                       files={"file": ("fatura.png", io.BytesIO(content), ctype)})


def test_read_invoice(client, fake_ai):
    r = _upload(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fatura_no"] == "FTR-2026-0042"
    assert body["tedarikci"] == "ABC Bilgisayar Ltd."
    assert len(body["kalemler"]) == 2
    assert body["kalemler"][0]["adet"] == 3


def test_unsupported_type_rejected(client, fake_ai):
    r = client.post("/invoices/oku",
                    files={"file": ("a.txt", io.BytesIO(b"metin"), "text/plain")})
    assert r.status_code == 400


def test_empty_file_rejected(client, fake_ai):
    r = _upload(client, content=b"")
    assert r.status_code == 400


def test_ai_unavailable_returns_503(client, monkeypatch):
    import app.routers.invoices as inv
    from app.ai.fatura import AIUnavailable

    def boom(data, media):
        raise AIUnavailable("ANTHROPIC_API_KEY ayarlanmalı")

    monkeypatch.setattr(inv, "extract_invoice", boom)
    r = _upload(client)
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_import_creates_assets(client):
    """Onaylanan kalemler adet kadar ayrı varlık oluşturur."""
    payload = {
        "fatura_no": "FTR-2026-0042",
        "purchase_date": "2026-03-15",
        "kalemler": [
            {"ad": "Dell Latitude 5440", "adet": 3, "birim_fiyat": 28500.0,
             "asset_tag_prefix": "NB"},
            {"ad": "Dell P2422H Monitör", "adet": 2, "birim_fiyat": 4200.0,
             "asset_tag_prefix": "MON"},
        ],
    }
    r = client.post("/invoices/aktar", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eklenen"] == 5

    etiketler = [v["asset_tag"] for v in body["varliklar"]]
    assert etiketler[:3] == ["NB-0001", "NB-0002", "NB-0003"]
    assert etiketler[3:] == ["MON-0001", "MON-0002"]

    assets = client.get("/assets").json()
    assert len(assets) == 5
    nb = next(a for a in assets if a["asset_tag"] == "NB-0001")
    assert nb["fatura_no"] == "FTR-2026-0042"
    assert nb["purchase_cost"] == 28500.0
    assert nb["purchase_date"] == "2026-03-15"


def test_import_serial_only_for_single_qty(client):
    payload = {"kalemler": [
        {"ad": "Tek Cihaz", "adet": 1, "seri_no": "SN-TEK"},
        {"ad": "Çoklu Cihaz", "adet": 2, "seri_no": "SN-COKLU"},
    ]}
    client.post("/invoices/aktar", json=payload)
    assets = {a["name"]: a for a in client.get("/assets").json()}
    assert assets["Tek Cihaz"]["serial"] == "SN-TEK"
    # adet > 1 ise aynı seri numarası tekrarlanmamalı
    coklu = [a for a in client.get("/assets").json() if a["name"] == "Çoklu Cihaz"]
    assert all(a["serial"] is None for a in coklu)


def test_import_avoids_tag_collision(client):
    client.post("/assets", json={"asset_tag": "NB-0001"})
    r = client.post("/invoices/aktar",
                    json={"kalemler": [{"ad": "Yeni", "adet": 1,
                                        "asset_tag_prefix": "NB"}]})
    assert r.status_code == 200
    assert r.json()["varliklar"][0]["asset_tag"] != "NB-0001"


def test_import_logs_activity(client):
    r = client.post("/invoices/aktar",
                    json={"fatura_no": "F-1", "kalemler": [{"ad": "X", "adet": 1}]})
    asset_id = r.json()["varliklar"][0]["id"]
    hist = client.get(f"/assets/{asset_id}/history").json()
    assert any("Faturadan aktarıldı" in (h["note"] or "") for h in hist)


def test_invoice_requires_editor(viewer_client):
    r = viewer_client.post("/invoices/aktar", json={"kalemler": [{"ad": "X", "adet": 1}]})
    assert r.status_code == 403


def test_invoice_requires_auth(anon_client):
    assert anon_client.post("/invoices/aktar", json={"kalemler": []}).status_code == 401
