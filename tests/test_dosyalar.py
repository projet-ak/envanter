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


def _diskteki_dosyalar():
    """Yükleme klasörü altındaki tüm dosyalar (alt klasörler dahil)."""
    from pathlib import Path
    return sorted(y for y in Path(settings.upload_dir).rglob("*") if y.is_file())


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
    assert len(_diskteki_dosyalar()) == 1

    assert client.delete(f"/dosyalar/{d['id']}").status_code == 204
    assert client.get(f"/assets/{cihaz['id']}/dosyalar").json() == []
    assert _diskteki_dosyalar() == []


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
    """'../' içeren ad yükleme klasörünün dışına yazmamalı."""
    r = _yukle(client, cihaz["id"], "../../../../etc/kotu.png", PNG, "gorsel",
               "image/png")
    assert r.status_code == 201
    yazilanlar = _diskteki_dosyalar()
    assert len(yazilanlar) == 1
    # Diskteki yol sunucu üretimi: klasör/yıl/ay/<id>-<rastgele>
    assert ".." not in r.json()["yol"]
    assert yazilanlar[0].name.startswith(f"{cihaz['id']}-")
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


# --------------------------------------------------------------------------- #
# Klasör düzeni — görseller ve belgeler ayrı, veritabanında yalnızca yol
# --------------------------------------------------------------------------- #
import datetime as _dt  # noqa: E402


def _bugun_alt() -> str:
    return f"{_dt.date.today():%Y/%m}"


def test_gorseller_ayri_klasore_yazilir(client, cihaz):
    d = _yukle(client, cihaz["id"], "on.png", PNG, "gorsel", "image/png").json()
    assert d["yol"].startswith(f"gorseller/{_bugun_alt()}/")
    from pathlib import Path
    assert (Path(settings.upload_dir) / d["yol"]).is_file()


def test_belgeler_ayri_klasore_yazilir(client, cihaz):
    imza = _yukle(client, cihaz["id"], "imzali.pdf", PDF, "zimmet_formu").json()
    diger = _yukle(client, cihaz["id"], "not.txt", b"metin", "diger").json()
    assert imza["yol"].startswith(f"belgeler/{_bugun_alt()}/")
    assert diger["yol"].startswith(f"belgeler/{_bugun_alt()}/")


def test_faturalar_ayri_klasore_yazilir(client, cihaz):
    d = _yukle(client, cihaz["id"], "fat.pdf", PDF, "fatura").json()
    assert d["yol"].startswith(f"faturalar/{_bugun_alt()}/")


def test_gorsel_ve_belge_ayni_klasorde_degil(client, cihaz):
    g = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    b = _yukle(client, cihaz["id"], "b.pdf", PDF, "zimmet_formu").json()
    from pathlib import Path
    assert Path(g["yol"]).parent != Path(b["yol"]).parent


def test_veritabaninda_yalnizca_goreli_yol_durur(client, cihaz):
    """Mutlak yol tutulmamalı: sunucu/klasör değişince kayıtlar geçersiz olmasın."""
    d = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    assert not d["yol"].startswith("/")
    assert settings.upload_dir not in d["yol"]


def test_kayit_yolu_kurcalanirsa_disari_cikilamaz(client, cihaz, db_session):
    """Veritabanındaki yol elle bozulsa bile kök klasörün dışı okunamamalı."""
    from app import models

    d = _yukle(client, cihaz["id"], "a.png", PNG, "gorsel", "image/png").json()
    kayit = db_session.get(models.AssetFile, d["id"])
    kayit.yol = "../../../../etc/passwd"
    db_session.commit()

    r = client.get(f"/dosyalar/{d['id']}")
    assert r.status_code == 400
    assert "passwd" not in r.text


def test_ayni_ay_icinde_cakisma_olmaz(client, cihaz):
    yollar = {_yukle(client, cihaz["id"], "ayni.png", PNG, "gorsel",
                     "image/png").json()["yol"] for _ in range(5)}
    assert len(yollar) == 5
