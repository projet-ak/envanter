"""Yazdıkça arama — isim, cihaz no, seri no.

Türkçe büyük/küçük harf eşlemesi SQL'de doğru çalışmaz; bu testler aramanın
"ertekin" yazınca "ERTEKİN"i, "santiye" yazınca "ŞANTİYE"yi bulmasını
güvenceye alır.
"""

import pytest


@pytest.fixture
def veri(client):
    """Türkçe karakter tuzaklarını içeren küçük bir veri kümesi."""
    kisi = client.post("/users", json={
        "first_name": "FATMA NUR", "last_name": "ERTEKİN",
        "employee_num": "1031199", "department": "Bilgi İşlem"}).json()
    digeri = client.post("/users", json={
        "first_name": "Süleyman", "last_name": "Ateşoğlu",
        "employee_num": "2044"}).json()
    lok = client.post("/locations", json={"name": "ŞANTİYE U023",
                                          "proje_kodu": "U023"}).json()

    a1 = client.post("/assets", json={
        "asset_tag": "N411", "name": "Dizüstü Bilgisayar", "serial": "PF2XDDZL",
        "demirbas_no": "DMR-77", "location_id": lok["id"]}).json()
    a2 = client.post("/assets", json={
        "asset_tag": "M028", "name": "Monitör", "serial": "ALMA9JA000182",
        "ip_address": "10.0.0.5"}).json()
    client.post(f"/assets/{a1['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": kisi["id"]})
    return {"kisi": kisi, "digeri": digeri, "a1": a1, "a2": a2, "lok": lok}


def _etiketler(client, q):
    return {a["asset_tag"] for a in client.get("/assets", params={"q": q}).json()}


# --------------------------------------------------------------------------- #
# Cihaz no / seri no / demirbaş
# --------------------------------------------------------------------------- #
def test_cihaz_no_ile_bulunur(client, veri):
    assert _etiketler(client, "N411") == {"N411"}


def test_seri_no_ile_bulunur(client, veri):
    assert _etiketler(client, "PF2XDDZL") == {"N411"}


def test_seri_no_parcasi_yeter(client, veri):
    """Yazmaya başlar başlamaz sonuç gelsin: parça eşleşmesi çalışmalı."""
    assert _etiketler(client, "ALMA") == {"M028"}
    assert _etiketler(client, "9JA") == {"M028"}


def test_kucuk_harf_yazinca_da_bulunur(client, veri):
    assert _etiketler(client, "pf2xddzl") == {"N411"}
    assert _etiketler(client, "n411") == {"N411"}


def test_demirbas_ve_ip_ile_bulunur(client, veri):
    assert _etiketler(client, "DMR-77") == {"N411"}
    assert _etiketler(client, "10.0.0.5") == {"M028"}


# --------------------------------------------------------------------------- #
# İsim — Türkçe harf tuzağı
# --------------------------------------------------------------------------- #
def test_zimmetli_personel_adiyla_cihaz_bulunur(client, veri):
    assert _etiketler(client, "FATMA") == {"N411"}


def test_turkce_i_harfi_takilmaz(client, veri):
    """'ertekin' -> 'ERTEKİN'. SQL LOWER() bunu beceremez."""
    assert _etiketler(client, "ertekin") == {"N411"}
    assert _etiketler(client, "ERTEKIN") == {"N411"}


def test_turkce_s_g_o_harfleri_takilmaz(client, veri):
    """'atesoglu' -> 'Ateşoğlu', 'monitor' -> 'Monitör'."""
    sonuc = client.get("/assets/ara", params={"q": "atesoglu"}).json()
    assert [k["ad"] for k in sonuc["personel"]] == ["Süleyman Ateşoğlu"]
    assert _etiketler(client, "monitor") == {"M028"}


def test_cihaz_adiyla_bulunur(client, veri):
    assert _etiketler(client, "dizüstü") == {"N411"}
    assert _etiketler(client, "dizustu") == {"N411"}


def test_eslesmeyen_terim_bos_doner(client, veri):
    assert _etiketler(client, "böyle-bir-şey-yok") == set()


# --------------------------------------------------------------------------- #
# Sayı ucu filtreyle tutarlı olmalı
# --------------------------------------------------------------------------- #
def test_sayi_ucu_ayni_sonucu_verir(client, veri):
    for q in ["ertekin", "N411", "monitor", "yok-böyle"]:
        liste = len(client.get("/assets", params={"q": q}).json())
        sayi = client.get("/assets/sayi", params={"q": q}).json()["toplam"]
        assert liste == sayi, f"'{q}' için liste={liste} sayi={sayi}"


def test_arama_diger_filtrelerle_birlesir(client, veri):
    r = client.get("/assets", params={"q": "ertekin", "assigned": "true"}).json()
    assert {a["asset_tag"] for a in r} == {"N411"}
    r2 = client.get("/assets", params={"q": "ertekin", "assigned": "false"}).json()
    assert r2 == []


# --------------------------------------------------------------------------- #
# Hızlı arama ucu (/assets/ara)
# --------------------------------------------------------------------------- #
def test_hizli_arama_cihaz_ve_personeli_birlikte_getirir(client, veri):
    r = client.get("/assets/ara", params={"q": "fatma"}).json()
    assert [k["ad"] for k in r["personel"]] == ["FATMA NUR ERTEKİN"]
    assert [c["asset_tag"] for c in r["cihazlar"]] == ["N411"]


def test_hizli_arama_sicil_ile_personel_bulur(client, veri):
    r = client.get("/assets/ara", params={"q": "1031199"}).json()
    assert [k["employee_num"] for k in r["personel"]] == ["1031199"]


def test_hizli_arama_cihaz_satirinda_zimmetli_gorunur(client, veri):
    c = client.get("/assets/ara", params={"q": "N411"}).json()["cihazlar"][0]
    assert c["zimmetli"] == "FATMA NUR ERTEKİN"
    assert c["lokasyon"] == "ŞANTİYE U023"


def test_hizli_arama_bos_terim_bos_doner(client, veri):
    r = client.get("/assets/ara", params={"q": ""}).json()
    assert r == {"cihazlar": [], "personel": [], "cihaz_toplam": 0,
                 "personel_toplam": 0}
    assert client.get("/assets/ara").json()["cihaz_toplam"] == 0


def test_hizli_arama_limit_uygulanir(client, veri):
    for i in range(15):
        client.post("/assets", json={"asset_tag": f"COK-{i:02d}",
                                     "name": "Toplu Cihaz"})
    r = client.get("/assets/ara", params={"q": "Toplu", "limit": 5}).json()
    assert len(r["cihazlar"]) == 5
    assert r["cihaz_toplam"] == 15      # toplam gerçek sayıyı bildirmeli


def test_hizli_arama_viewer_icin_de_calisir(viewer_client):
    assert viewer_client.get("/assets/ara", params={"q": "a"}).status_code == 200


def test_hizli_arama_giris_ister(anon_client):
    assert anon_client.get("/assets/ara", params={"q": "a"}).status_code == 401


def test_ara_ucu_kimlikle_karismaz(client, veri):
    """/assets/ara, /assets/{id} yoluna düşmemeli."""
    assert client.get("/assets/ara", params={"q": "x"}).status_code == 200
    assert client.get("/assets/proje-kodlari").status_code == 200
