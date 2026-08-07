"""Cihaz dosya ekleri: görsel ve imzalı zimmet formu yükleme."""

import io

import pytest

from app.config import settings

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)      # geçerli imzalı minik içerik
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 40


@pytest.fixture(autouse=True)
def gecici_yukleme_dizini(tmp_path, monkeypatch):
    """Testler gerçek yükleme klasörünü kirletmesin."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "yuklemeler"))
    return tmp_path


@pytest.fixture
def cihaz(client):
    return client.post("/assets", json={"asset_tag": "DSY-1", "name": "Laptop"}).json()


def _yukle(client, asset_id, ad, icerik, tur, ct="application/octet-stream"):
    return client.post(
        f"/assets/{asset_id}/dosyalar",
        files={"file": (ad, io.BytesIO(icerik), ct)},
        data={"tur": tur},
    )


# --------------------------------------------------------------------------- #
# Yükleme
# --------------------------------------------------------------------------- #
def test_cihaz_gorseli_yuklenir(client, cihaz):
    r = _yukle(client, cihaz["id"], "on-yuz.png", PNG, "gorsel", "image/png")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["tur"] == "gorsel"
    assert d["dosya_adi"] == "on-yuz.png"
    assert d["boyut"] == len(PNG)
    assert d["asset_id"] == cihaz["id"]


def test_imzali_zimmet_formu_yuklenir(client, cihaz):
    r = _yukle(client, cihaz["id"], "imzali.pdf", PDF, "zimmet_formu", "application/pdf")
    assert r.status_code == 201
    assert r.json()["tur"] == "zimmet_formu"


def test_yuklenen_dosya_indirilir(client, cihaz):
    d = _yukle(client, cihaz["id"], "imzali.pdf", PDF, "zimmet_formu").json()
    r = client.get(f"/dosyalar/{d['id']}")
    assert r.status_code == 200
    assert r.content == PDF
    assert "imzali.pdf" in r.headers["content-disposition"]


def test_gorsel_tarayicida_gosterilir_belge_indirilir(client, cihaz):
    g = _yukle(client, cihaz["id"], "foto.png", PNG, "gorsel", "image/png").json()
    b = _yukle(client, cihaz["id"], "form.pdf", PDF, "zimmet_formu").json()
    assert client.get(f"/dosyalar/{g['id']}").headers["content-disposition"] \
        .startswith("inline")
    assert client.get(f"/dosyalar/{b['id']}").headers["content-disposition"] \
        .startswith("attachment")


def test_cihazin_dosyalari_listelenir(client, cihaz):
    _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png")
    _yukle(client, cihaz["id"], "b.pdf", PDF, "zimmet_formu")
    liste = client.get(f"/assets/{cihaz['id']}/dosyalar").json()
    assert {d["dosya_adi"] for d in liste} == {"a.png", "b.pdf"}


def test_dosya_silinir_ve_diskten_kalkar(client, cihaz):
    d = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    from pathlib import Path
    diskte = list(Path(settings.upload_dir).iterdir())
    assert len(diskte) == 1

    assert client.delete(f"/dosyalar/{d['id']}").status_code == 204
    assert client.get(f"/assets/{cihaz['id']}/dosyalar").json() == []
    assert list(Path(settings.upload_dir).iterdir()) == []


def test_turkce_dosya_adi_korunur(client, cihaz):
    d = _yukle(client, cihaz["id"], "şantiye görseli.png", PNG, "gorsel",
               "image/png").json()
    assert d["dosya_adi"] == "şantiye görseli.png"
    assert client.get(f"/dosyalar/{d['id']}").status_code == 200


# --------------------------------------------------------------------------- #
# Güvenlik ve doğrulama
# --------------------------------------------------------------------------- #
def test_tehlikeli_uzanti_reddedilir(client, cihaz):
    for ad in ["kotu.exe", "betik.sh", "kabuk.php", "uzantisiz"]:
        r = _yukle(client, cihaz["id"], ad, b"zararli", "diger")
        assert r.status_code == 415, f"{ad} kabul edilmemeli"


def test_yol_gecisi_dosya_adi_zarar_vermez(client, cihaz, tmp_path):
    """'../' içeren ad diskte dizin dışına yazmamalı."""
    r = _yukle(client, cihaz["id"], "../../../../etc/kotu.png", PNG, "gorsel",
               "image/png")
    assert r.status_code == 201
    from pathlib import Path
    yazilanlar = list(Path(settings.upload_dir).iterdir())
    assert len(yazilanlar) == 1
    # Diskteki ad sunucu üretimi: cihaz kimliği + rastgele
    assert yazilanlar[0].name.startswith(f"{cihaz['id']}-")
    assert ".." not in yazilanlar[0].name
    # Görünen ad da dizin bileşeni taşımamalı
    assert r.json()["dosya_adi"] == "kotu.png"


def test_gorsel_turu_icin_resim_sart(client, cihaz):
    r = _yukle(client, cihaz["id"], "form.pdf", PDF, "gorsel")
    assert r.status_code == 415


def test_buyuk_dosya_reddedilir(client, cihaz, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    buyuk = PNG + b"0" * (2 * 1024 * 1024)
    r = _yukle(client, cihaz["id"], "buyuk.png", buyuk, "gorsel", "image/png")
    assert r.status_code == 413


def test_bos_dosya_reddedilir(client, cihaz):
    r = _yukle(client, cihaz["id"], "bos.png", b"", "gorsel", "image/png")
    assert r.status_code == 400


def test_olmayan_cihaza_yukleme_404(client):
    r = _yukle(client, 999999, "a.png", PNG, "gorsel", "image/png")
    assert r.status_code == 404


def test_ayni_ad_birbirini_ezmez(client, cihaz):
    a = _yukle(client, cihaz["id"], "foto.png", PNG, "gorsel", "image/png").json()
    b = _yukle(client, cihaz["id"], "foto.png", PNG + b"x", "gorsel",
               "image/png").json()
    assert a["id"] != b["id"]
    assert client.get(f"/dosyalar/{a['id']}").content != \
        client.get(f"/dosyalar/{b['id']}").content


def test_viewer_yukleyemez_ama_gorebilir(client, viewer_client, cihaz):
    d = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    assert viewer_client.get(f"/assets/{cihaz['id']}/dosyalar").status_code == 200
    assert viewer_client.get(f"/dosyalar/{d['id']}").status_code == 200
    assert _yukle(viewer_client, cihaz["id"], "b.png", PNG, "gorsel",
                  "image/png").status_code == 403
    assert viewer_client.delete(f"/dosyalar/{d['id']}").status_code == 403


def test_giris_yapmadan_erisilemez(anon_client, client, cihaz):
    d = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    assert anon_client.get(f"/dosyalar/{d['id']}").status_code == 401
    assert anon_client.get(f"/assets/{cihaz['id']}/dosyalar").status_code == 401


def test_cihaz_silinince_dosya_kaydi_da_gider(client, cihaz):
    _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png")
    assert client.delete(f"/assets/{cihaz['id']}").status_code == 204
    assert client.get(f"/assets/{cihaz['id']}/dosyalar").status_code == 404


def test_detay_ucu_dosyalari_icerir(client, cihaz):
    """Arayüz cihaz detayında görselleri ve belgeleri buradan okur."""
    _yukle(client, cihaz["id"], "on.png", PNG, "gorsel", "image/png")
    _yukle(client, cihaz["id"], "imzali.pdf", PDF, "zimmet_formu")

    d = client.get(f"/detay/asset/{cihaz['id']}").json()
    turler = {f["tur"] for f in d["dosyalar"]}
    assert turler == {"gorsel", "zimmet_formu"}
    assert all(f["id"] and f["dosya_adi"] and f["tarih"] for f in d["dosyalar"])


def test_dosyasiz_cihazda_liste_bos(client, cihaz):
    assert client.get(f"/detay/asset/{cihaz['id']}").json()["dosyalar"] == []
