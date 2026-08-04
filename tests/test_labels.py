"""Barkod / QR etiket ve okutma testleri."""


def _make_asset(client, tag="BT-900", **extra):
    return client.post("/assets", json={"asset_tag": tag, "name": "Test Cihaz", **extra}).json()


def test_qr_png(client):
    a = _make_asset(client)
    r = client.get(f"/documents/etiket/asset/{a['id']}.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_single_label_pdf(client):
    a = _make_asset(client, demirbas_no="DMR-900")
    r = client.get(f"/documents/etiket/asset/{a['id']}.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_bulk_labels_pdf(client):
    ids = [_make_asset(client, tag=f"BT-{i}")["id"] for i in range(910, 915)]
    r = client.post("/documents/etiketler.pdf", json={"asset_ids": ids})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 2000


def test_bulk_labels_by_location(client):
    loc = client.post("/locations", json={"name": "Depo A"}).json()
    _make_asset(client, tag="LOC-1", location_id=loc["id"])
    _make_asset(client, tag="LOC-2", location_id=loc["id"])
    _make_asset(client, tag="OTHER")  # başka lokasyon

    r = client.post("/documents/etiketler.pdf", json={"location_id": loc["id"]})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_bulk_labels_empty_404(client):
    assert client.post("/documents/etiketler.pdf",
                       json={"asset_ids": [99999]}).status_code == 404


def test_scan_by_various_codes(client):
    a = _make_asset(client, tag="SCAN-1", demirbas_no="DMR-SCAN",
                    barkod="8690000000031", serial="SN-SCAN", imei="356938035643809")
    for kod in ["SCAN-1", "DMR-SCAN", "8690000000031", "SN-SCAN", "356938035643809"]:
        r = client.get("/documents/tara", params={"kod": kod})
        assert r.status_code == 200, kod
        assert r.json()["id"] == a["id"]


def test_scan_not_found(client):
    r = client.get("/documents/tara", params={"kod": "YOK-123"})
    assert r.status_code == 404
    assert "YOK-123" in r.json()["detail"]


def test_scan_trims_whitespace(client):
    """Barkod okuyucular sonuna boşluk/enter ekleyebilir."""
    a = _make_asset(client, tag="TRIM-1")
    r = client.get("/documents/tara", params={"kod": "  TRIM-1  "})
    assert r.status_code == 200
    assert r.json()["id"] == a["id"]


def test_labels_require_auth(anon_client):
    assert anon_client.get("/documents/tara", params={"kod": "x"}).status_code == 401
    assert anon_client.post("/documents/etiketler.pdf", json={}).status_code == 401
