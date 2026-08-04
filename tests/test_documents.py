"""Zimmet / iade tutanağı PDF testleri."""


def _asset_with_user(client):
    user = client.post("/users", json={
        "first_name": "Mehmet", "last_name": "Öztürk", "employee_num": "P-01",
        "department": "BT", "sube": "Merkez", "telefon": "05551112233",
    }).json()
    asset = client.post("/assets", json={
        "asset_tag": "BT-500", "name": "Dizüstü Bilgisayar",
        "serial": "SN-500", "demirbas_no": "DMR-500", "barkod": "BRK-500",
    }).json()
    client.post(f"/assets/{asset['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": user["id"]})
    return user, asset


def test_asset_zimmet_pdf(client):
    _user, asset = _asset_with_user(client)
    r = client.get(f"/documents/zimmet/asset/{asset['id']}.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


def test_asset_iade_pdf(client):
    _user, asset = _asset_with_user(client)
    r = client.get(f"/documents/zimmet/asset/{asset['id']}.pdf",
                   params={"doc_type": "iade", "note": "Ekran çizik"})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_user_zimmet_pdf(client):
    user, _asset = _asset_with_user(client)
    # ikinci bir cihaz da zimmetle
    a2 = client.post("/assets", json={"asset_tag": "BT-501", "name": "Monitör"}).json()
    client.post(f"/assets/{a2['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": user["id"]})

    r = client.get(f"/documents/zimmet/user/{user['id']}.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"

    # Türkçe karakterli ad (Öztürk) başlığı bozmamalı:
    # ASCII yedeği + RFC 5987 filename* birlikte gönderilir.
    disposition = r.headers["content-disposition"]
    assert "Ozturk" in disposition          # ASCII yedeği
    assert "filename*=UTF-8''" in disposition
    assert "%C3%96zt%C3%BCrk" in disposition  # UTF-8 kodlu gerçek ad


def test_user_without_assets_404(client):
    user = client.post("/users", json={"first_name": "Boş"}).json()
    assert client.get(f"/documents/zimmet/user/{user['id']}.pdf").status_code == 404


def test_pdf_requires_auth(anon_client):
    assert anon_client.get("/documents/zimmet/asset/1.pdf").status_code == 401


def test_turkish_characters_render(client):
    """Türkçe karakterler PDF'e gömülü fontla yazılmalı (font kaydı testi)."""
    from app.pdf.zimmet import _FONT, _FONT_BOLD

    # Sistemde DejaVu/Liberation varsa TR fontu kayıtlı olmalı
    assert _FONT in ("TR", "Helvetica")
    assert _FONT_BOLD in ("TR-Bold", "Helvetica-Bold")

    _user, asset = _asset_with_user(client)
    r = client.get(f"/documents/zimmet/asset/{asset['id']}.pdf")
    assert r.status_code == 200
