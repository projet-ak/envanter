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


# --------------------------------------------------------------------------- #
# Kişi ekleri — imzalı zimmet formu tek cihaza değil KİŞİYE aittir
# --------------------------------------------------------------------------- #
@pytest.fixture
def kisi(client):
    return client.post("/users", json={"first_name": "Tülin",
                                       "last_name": "Akyazı"}).json()


def test_kisiye_imzali_form_yuklenir(client, kisi):
    r = client.post(f"/users/{kisi['id']}/dosyalar",
                    files={"file": ("form.pdf", io.BytesIO(PDF), "application/pdf")},
                    data={"tur": "zimmet_formu"})
    assert r.status_code == 201, r.text
    kayit = r.json()
    assert kayit["user_id"] == kisi["id"]
    assert kayit["tur"] == "zimmet_formu"
    assert kayit["dosya_adi"] == "form.pdf"
    # Diskte belgeler klasöründe, adı "k<kişi id>-" ile başlar
    yollar = [str(y) for y in _diskteki_dosyalar()]
    assert len(yollar) == 1 and "/belgeler/" in yollar[0]
    assert f"/k{kisi['id']}-" in yollar[0]


def test_kisi_dosyalari_listelenir_ve_indirilir(client, kisi):
    client.post(f"/users/{kisi['id']}/dosyalar",
                files={"file": ("zimmet.pdf", io.BytesIO(PDF), "application/pdf")},
                data={"tur": "zimmet_formu"})
    liste = client.get(f"/users/{kisi['id']}/dosyalar").json()
    assert [f["dosya_adi"] for f in liste] == ["zimmet.pdf"]

    r = client.get(f"/kisi-dosyalari/{liste[0]['id']}")
    assert r.status_code == 200
    assert r.content == PDF
    assert "attachment" in r.headers["content-disposition"]


def test_kisi_dosyasi_silinir(client, kisi):
    dosya = client.post(
        f"/users/{kisi['id']}/dosyalar",
        files={"file": ("a.pdf", io.BytesIO(PDF), "application/pdf")}).json()
    assert len(_diskteki_dosyalar()) == 1
    assert client.delete(f"/kisi-dosyalari/{dosya['id']}").status_code == 204
    assert client.get(f"/users/{kisi['id']}/dosyalar").json() == []
    assert _diskteki_dosyalar() == []


def test_kisi_silinince_dosyalari_da_gider(client, kisi):
    client.post(f"/users/{kisi['id']}/dosyalar",
                files={"file": ("a.pdf", io.BytesIO(PDF), "application/pdf")})
    client.delete(f"/users/{kisi['id']}")
    assert client.get(f"/users/{kisi['id']}/dosyalar").status_code == 404


def test_olmayan_kisiye_yuklenemez(client):
    r = client.post("/users/999999/dosyalar",
                    files={"file": ("a.pdf", io.BytesIO(PDF), "application/pdf")})
    assert r.status_code == 404


def test_kisi_dosyasinda_tehlikeli_uzanti_reddedilir(client, kisi):
    r = client.post(f"/users/{kisi['id']}/dosyalar",
                    files={"file": ("kotu.sh", io.BytesIO(b"#!/bin/sh"),
                                    "application/x-sh")})
    assert r.status_code == 415
    assert _diskteki_dosyalar() == []


def test_kisi_dosyasi_viewer_yukleyemez(viewer_client, client, kisi):
    r = viewer_client.post(f"/users/{kisi['id']}/dosyalar",
                           files={"file": ("a.pdf", io.BytesIO(PDF),
                                           "application/pdf")})
    assert r.status_code == 403


def test_cihaz_ve_kisi_ekleri_birbirine_karismaz(client, cihaz, kisi):
    client.post(f"/assets/{cihaz['id']}/dosyalar",
                files={"file": ("cihaz.pdf", io.BytesIO(PDF), "application/pdf")})
    client.post(f"/users/{kisi['id']}/dosyalar",
                files={"file": ("kisi.pdf", io.BytesIO(PDF), "application/pdf")})
    assert [f["dosya_adi"] for f in
            client.get(f"/assets/{cihaz['id']}/dosyalar").json()] == ["cihaz.pdf"]
    assert [f["dosya_adi"] for f in
            client.get(f"/users/{kisi['id']}/dosyalar").json()] == ["kisi.pdf"]
    # Kimlikler ayrı dizilerden gelir: aynı numara iki tabloda da olabilir.
    # Cihaz ucu kişi ekini, kişi ucu cihaz ekini ASLA vermemeli.
    kisi_dosya = client.get(f"/users/{kisi['id']}/dosyalar").json()[0]
    cihaz_dosya = client.get(f"/assets/{cihaz['id']}/dosyalar").json()[0]
    ad = lambda r: r.headers["content-disposition"].rsplit("''", 1)[-1]
    assert ad(client.get(f"/dosyalar/{cihaz_dosya['id']}")) == "cihaz.pdf"
    assert ad(client.get(f"/kisi-dosyalari/{kisi_dosya['id']}")) == "kisi.pdf"


# --------------------------------------------------------------------------- #
# Stok ekleri — aksesuar / sarf / bileşen / lisans
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("uc,kayit_turu,on_ek", [
    ("/accessories", "accessory", "a"),
    ("/consumables", "consumable", "s"),
    ("/components", "component", "b"),
    ("/licenses", "license", "l"),
])
def test_stok_kaydina_dosya_eklenir(client, uc, kayit_turu, on_ek):
    kayit = client.post(uc, json={"name": "Test"}).json()
    r = client.post(f"/stok/{kayit_turu}/{kayit['id']}/dosyalar",
                    files={"file": ("urun.png", io.BytesIO(PNG), "image/png")},
                    data={"tur": "gorsel"})
    assert r.status_code == 201, r.text
    assert r.json()["kayit_turu"] == kayit_turu
    assert r.json()["kayit_id"] == kayit["id"]

    yollar = [str(y) for y in _diskteki_dosyalar()]
    assert len(yollar) == 1 and "/gorseller/" in yollar[0]
    assert f"/{on_ek}{kayit['id']}-" in yollar[0], "kayıt türü ön eki yok"

    liste = client.get(f"/stok/{kayit_turu}/{kayit['id']}/dosyalar").json()
    assert [f["dosya_adi"] for f in liste] == ["urun.png"]
    indir = client.get(f"/stok/dosyalari/{liste[0]['id']}")
    assert indir.status_code == 200 and indir.content == PNG
    assert "inline" in indir.headers["content-disposition"]   # görsel gösterilir


def test_stok_dosyasi_silinir(client):
    a = client.post("/accessories", json={"name": "Klavye"}).json()
    d = client.post(f"/stok/accessory/{a['id']}/dosyalar",
                    files={"file": ("f.pdf", io.BytesIO(PDF),
                                    "application/pdf")}).json()
    assert client.delete(f"/stok/dosyalari/{d['id']}").status_code == 204
    assert client.get(f"/stok/accessory/{a['id']}/dosyalar").json() == []
    assert _diskteki_dosyalar() == []


def test_stok_kaydi_silinince_ekleri_de_gider(client):
    """Yabancı anahtar yok; temizliği olay dinleyicisi yapıyor."""
    a = client.post("/accessories", json={"name": "Mouse"}).json()
    client.post(f"/stok/accessory/{a['id']}/dosyalar",
                files={"file": ("f.pdf", io.BytesIO(PDF), "application/pdf")})
    b = client.post("/consumables", json={"name": "Toner"}).json()
    client.post(f"/stok/consumable/{b['id']}/dosyalar",
                files={"file": ("g.pdf", io.BytesIO(PDF), "application/pdf")})

    assert client.delete(f"/accessories/{a['id']}").status_code in (200, 204)
    assert client.get(f"/stok/accessory/{a['id']}/dosyalar").status_code == 404
    # Diğer türün eki etkilenmemeli
    assert len(client.get(f"/stok/consumable/{b['id']}/dosyalar").json()) == 1


def test_ayni_kimlik_farkli_turde_karismaz(client):
    """accessory #1 ile consumable #1 aynı numarayı taşır; ekler ayrı durmalı."""
    a = client.post("/accessories", json={"name": "A"}).json()
    c = client.post("/consumables", json={"name": "C"}).json()
    client.post(f"/stok/accessory/{a['id']}/dosyalar",
                files={"file": ("aksesuar.pdf", io.BytesIO(PDF), "application/pdf")})
    client.post(f"/stok/consumable/{c['id']}/dosyalar",
                files={"file": ("sarf.pdf", io.BytesIO(PDF), "application/pdf")})
    assert [f["dosya_adi"] for f in
            client.get(f"/stok/accessory/{a['id']}/dosyalar").json()] == \
        ["aksesuar.pdf"]
    assert [f["dosya_adi"] for f in
            client.get(f"/stok/consumable/{c['id']}/dosyalar").json()] == \
        ["sarf.pdf"]


def test_olmayan_stok_kaydina_yuklenemez(client):
    r = client.post("/stok/accessory/999999/dosyalar",
                    files={"file": ("f.pdf", io.BytesIO(PDF), "application/pdf")})
    assert r.status_code == 404


def test_bilinmeyen_kayit_turu_reddedilir(client):
    r = client.get("/stok/uzay_gemisi/1/dosyalar")
    assert r.status_code == 422


def test_stok_dosyasi_viewer_yukleyemez(client, viewer_client):
    a = client.post("/accessories", json={"name": "K"}).json()
    r = viewer_client.post(f"/stok/accessory/{a['id']}/dosyalar",
                           files={"file": ("f.pdf", io.BytesIO(PDF),
                                           "application/pdf")})
    assert r.status_code == 403
