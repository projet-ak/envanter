"""Arayüzden yedekleme: alma, listeleme, indirme, silme ve güvenlik."""

import datetime as dt
import os
import tarfile
from pathlib import Path

import pytest

from app import yedek
from app.config import settings


@pytest.fixture(autouse=True)
def gecici_klasorler(tmp_path, monkeypatch):
    """Testler gerçek yedek/yükleme klasörlerine dokunmasın."""
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "yedekler"))
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "yuklemeler"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Yedek alma
# --------------------------------------------------------------------------- #
def test_yedek_alinir_ve_listelenir(client):
    r = client.post("/yedek")
    assert r.status_code == 201, r.text
    ozet = r.json()
    assert ozet["veritabani"].startswith("envanter_")
    assert ozet["veritabani_boyut"] > 0

    liste = client.get("/yedek").json()["yedekler"]
    assert [y["ad"] for y in liste] == [ozet["veritabani"]]
    assert liste[0]["tur"] == "veritabani"


def test_yedek_gercekten_veri_iceriyor(client, db_session, monkeypatch):
    """Alınan yedek açılabilmeli ve kayıtları taşımalı.

    Yedekleme `settings.database_url`'i okur; testte bu, istemcinin kullandığı
    geçici veritabanına yönlendirilir (üretimde ikisi zaten aynıdır).
    """
    monkeypatch.setattr(settings, "database_url",
                        db_session.get_bind().url.render_as_string(
                            hide_password=False))
    client.post("/assets", json={"asset_tag": "YEDEK-1", "name": "Test Cihaz"})
    ad = client.post("/yedek").json()["veritabani"]

    import sqlite3
    yol = Path(settings.backup_dir) / ad
    with sqlite3.connect(yol) as db:
        etiketler = [r[0] for r in db.execute("SELECT asset_tag FROM assets")]
    assert "YEDEK-1" in etiketler


def test_yuklenen_dosyalar_da_arsivlenir(client, tmp_path):
    yukleme = Path(settings.upload_dir) / "gorseller" / "2026" / "08"
    yukleme.mkdir(parents=True)
    (yukleme / "ornek.png").write_bytes(b"GORSEL")

    ozet = client.post("/yedek").json()
    assert ozet["dosyalar"] is not None
    arsiv = Path(settings.backup_dir) / ozet["dosyalar"]
    with tarfile.open(arsiv) as t:
        icindekiler = t.getnames()
    assert any(a.endswith("gorseller/2026/08/ornek.png") for a in icindekiler)


def test_dosya_yoksa_arsiv_uretilmez(client):
    assert client.post("/yedek").json()["dosyalar"] is None


# --------------------------------------------------------------------------- #
# İndirme / silme
# --------------------------------------------------------------------------- #
def test_yedek_indirilir(client):
    ad = client.post("/yedek").json()["veritabani"]
    r = client.get(f"/yedek/{ad}")
    assert r.status_code == 200
    assert len(r.content) > 0
    assert ad in r.headers.get("content-disposition", "")


def test_yedek_silinir(client):
    ad = client.post("/yedek").json()["veritabani"]
    assert client.delete(f"/yedek/{ad}").status_code == 204
    assert client.get("/yedek").json()["yedekler"] == []


def test_olmayan_yedek_404(client):
    assert client.get("/yedek/envanter_2020-01-01_000000.dump").status_code == 404
    assert client.delete("/yedek/yok.sqlite").status_code == 404


# --------------------------------------------------------------------------- #
# Güvenlik
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ad", [
    "../../../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    ".gizli",
])
def test_yol_gecisi_engellenir(client, ad):
    r = client.get(f"/yedek/{ad}")
    assert r.status_code in (400, 404), f"{ad!r} kabul edildi"
    assert "root:" not in r.text


def test_klasor_disina_yazilamaz(tmp_path):
    """yedek_yolu() kök klasörün dışını asla döndürmemeli."""
    (tmp_path / "disarida.txt").write_text("gizli")
    with pytest.raises(yedek.YedekHatasi):
        yedek.yedek_yolu("../disarida.txt")


def test_viewer_yedek_alamaz_goremez(viewer_client):
    assert viewer_client.get("/yedek").status_code == 403
    assert viewer_client.post("/yedek").status_code == 403
    assert viewer_client.delete("/yedek/x.sqlite").status_code == 403


def test_giris_sart(anon_client):
    assert anon_client.get("/yedek").status_code == 401
    assert anon_client.post("/yedek").status_code == 401


def test_hata_mesajinda_parola_sizmaz(monkeypatch):
    """Dış aracın hata çıktısı bağlantı dizesi içerebilir; maskelenmeli."""
    monkeypatch.setattr(
        settings, "database_url",
        "postgresql+psycopg2://envanter:CokGizliParola@localhost:5432/envanter")

    # pg_dump'ı, bağlantı dizesini stderr'e yazan sahte bir komutla değiştir
    import subprocess
    gercek = subprocess.run

    def sahte(komut, *a, **kw):
        if komut[0] == "pg_dump":
            return subprocess.CompletedProcess(
                komut, 1, b"",
                b"connection to postgresql://envanter:CokGizliParola@localhost "
                b"failed")
        return gercek(komut, *a, **kw)

    monkeypatch.setattr(subprocess, "run", sahte)
    with pytest.raises(yedek.YedekHatasi) as hata:
        yedek.veritabani_yedegi()
    assert "CokGizliParola" not in str(hata.value)
    assert "***" in str(hata.value)


def test_parola_komut_satirina_yazilmaz(monkeypatch):
    """`ps` çıktısı herkese açık; parola argüman olarak geçmemeli."""
    monkeypatch.setattr(
        settings, "database_url",
        "postgresql+psycopg2://envanter:CokGizliParola@localhost:5432/envanter")

    gorulen = {}
    import subprocess
    def sahte(komut, *a, **kw):
        gorulen["komut"] = komut
        gorulen["ortam"] = kw.get("env") or {}
        return subprocess.CompletedProcess(komut, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", sahte)
    yedek.veritabani_yedegi()
    assert "CokGizliParola" not in " ".join(gorulen["komut"])
    # Parola ortam değişkeniyle geçirilmeli
    assert gorulen["ortam"].get("PGPASSWORD") == "CokGizliParola"


# --------------------------------------------------------------------------- #
# Eski yedeklerin temizliği
# --------------------------------------------------------------------------- #
def test_eski_yedekler_silinir(monkeypatch):
    monkeypatch.setattr(settings, "backup_keep_days", 7)
    dizin = yedek.yedek_dizini()
    eski = dizin / "envanter_2020-01-01_000000.sqlite"
    yeni = dizin / "envanter_2026-08-07_120000.sqlite"
    for y in (eski, yeni):
        y.write_bytes(b"x")
    eski_zaman = (dt.datetime.now() - dt.timedelta(days=30)).timestamp()
    os.utime(eski, (eski_zaman, eski_zaman))

    assert yedek.eskileri_sil() == 1
    assert not eski.exists() and yeni.exists()


def test_saklama_kapaliysa_silinmez(monkeypatch):
    monkeypatch.setattr(settings, "backup_keep_days", 0)
    y = yedek.yedek_dizini() / "envanter_2020-01-01_000000.sqlite"
    y.write_bytes(b"x")
    os.utime(y, (0, 0))
    assert yedek.eskileri_sil() == 0
    assert y.exists()


def test_ilgisiz_dosyalar_listelenmez_silinmez(monkeypatch, client):
    monkeypatch.setattr(settings, "backup_keep_days", 1)
    baska = yedek.yedek_dizini() / "onemli-not.txt"
    baska.write_text("bunu silme")
    os.utime(baska, (0, 0))

    assert client.get("/yedek").json()["yedekler"] == []
    yedek.eskileri_sil()
    assert baska.exists(), "yedek olmayan dosya silindi"


def test_desteklenmeyen_veritabani_anlasilir_hata(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "oracle://a:b@localhost/x")
    with pytest.raises(yedek.YedekHatasi, match="Desteklenmeyen"):
        yedek.veritabani_yedegi()
