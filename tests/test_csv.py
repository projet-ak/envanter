"""CSV içe/dışa aktarım testleri."""

import io


def test_export_assets_csv(client):
    client.post("/assets", json={"asset_tag": "CSV-1", "name": "Laptop"})
    r = client.get("/io/assets.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.text
    assert "asset_tag" in body.splitlines()[0]
    assert "CSV-1" in body


def test_import_assets_csv(client):
    csv_content = (
        "asset_tag,name,serial\n"
        "IMP-1,Laptop A,SN-A\n"
        "IMP-2,Laptop B,SN-B\n"
    )
    files = {"file": ("assets.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    r = client.post("/io/assets/import", files=files)
    assert r.status_code == 200
    result = r.json()
    assert result["created"] == 2
    assert len(client.get("/assets").json()) == 2

    # Tekrar içe aktar → güncelleme (yeni kayıt yok)
    files = {"file": ("assets.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    r2 = client.post("/io/assets/import", files=files).json()
    assert r2["created"] == 0 and r2["updated"] == 2


def test_import_requires_editor(viewer_client):
    files = {"file": ("a.csv", io.BytesIO(b"asset_tag\nX-1\n"), "text/csv")}
    assert viewer_client.post("/io/assets/import", files=files).status_code == 403


def test_import_bad_csv(client):
    files = {"file": ("bad.csv", io.BytesIO(b"name,serial\nfoo,bar\n"), "text/csv")}
    r = client.post("/io/assets/import", files=files)
    assert r.status_code == 400  # asset_tag sütunu yok
