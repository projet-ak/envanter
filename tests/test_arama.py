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

    # İkinci şantiye + kodsuz bir lokasyon (filtreleme ayrımı için)
    lok2 = client.post("/locations", json={"name": "ŞANTİYE U026",
                                           "proje_kodu": "U026"}).json()
    merkez = client.post("/locations", json={"name": "Merkez Depo"}).json()
    a3 = client.post("/assets", json={"asset_tag": "K101",
                                      "location_id": lok2["id"]}).json()
    a4 = client.post("/assets", json={"asset_tag": "D501",
                                      "location_id": merkez["id"]}).json()
    return {"kisi": kisi, "digeri": digeri, "a1": a1, "a2": a2, "a3": a3,
            "a4": a4, "lok": lok, "lok2": lok2, "merkez": merkez}


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
    assert r == {"cihazlar": [], "personel": [], "lokasyonlar": [],
                 "cihaz_toplam": 0, "personel_toplam": 0, "lokasyon_toplam": 0}
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


# --------------------------------------------------------------------------- #
# Lokasyon ve proje kodu
# --------------------------------------------------------------------------- #
def test_lokasyon_adiyla_cihaz_bulunur(client, veri):
    """'santiye' yazınca o lokasyondaki cihazlar gelsin (Türkçe harf dahil)."""
    assert _etiketler(client, "santiye") == {"N411", "K101"}
    assert _etiketler(client, "ŞANTİYE") == {"N411", "K101"}


def test_proje_koduyla_cihaz_bulunur(client, veri):
    assert _etiketler(client, "U023") == {"N411"}
    assert _etiketler(client, "u026") == {"K101"}


def test_kodsuz_lokasyon_adiyla_da_bulunur(client, veri):
    assert _etiketler(client, "merkez depo") == {"D501"}
    assert _etiketler(client, "depo") == {"D501"}


def test_lokasyon_aramasi_sayi_ucuyla_tutarli(client, veri):
    for q in ["santiye", "U023", "depo"]:
        liste = len(client.get("/assets", params={"q": q}).json())
        sayi = client.get("/assets/sayi", params={"q": q}).json()["toplam"]
        assert liste == sayi, f"'{q}' için liste={liste} sayi={sayi}"


def test_lokasyonsuz_cihaz_lokasyon_aramasinda_cikmaz(client, veri):
    assert "M028" not in _etiketler(client, "santiye")   # M028'in lokasyonu yok


def test_hizli_aramada_lokasyon_bolumu(client, veri):
    r = client.get("/assets/ara", params={"q": "santiye"}).json()
    adlar = {l["ad"] for l in r["lokasyonlar"]}
    assert adlar == {"ŞANTİYE U023", "ŞANTİYE U026"}
    assert r["lokasyon_toplam"] == 2


def test_hizli_aramada_lokasyon_cihaz_sayisi_dogru(client, veri):
    r = client.get("/assets/ara", params={"q": "U023"}).json()
    lok = next(x for x in r["lokasyonlar"] if x["proje_kodu"] == "U023")
    assert lok["cihaz_sayisi"] == 1
    assert lok["ad"] == "ŞANTİYE U023"


def test_lokasyonlar_cihaz_sayisina_gore_siralanir(client, veri):
    """Çok cihazlı şantiye listede üstte olsun."""
    for i in range(3):
        client.post("/assets", json={"asset_tag": f"EK-{i}",
                                     "location_id": veri["lok2"]["id"]})
    r = client.get("/assets/ara", params={"q": "santiye"}).json()
    assert [l["ad"] for l in r["lokasyonlar"]] == ["ŞANTİYE U026", "ŞANTİYE U023"]


def test_bos_lokasyon_da_listelenir(client, veri):
    """Henüz cihazı olmayan şantiye de bulunabilmeli."""
    client.post("/locations", json={"name": "ŞANTİYE U099", "proje_kodu": "U099"})
    r = client.get("/assets/ara", params={"q": "U099"}).json()
    assert r["lokasyonlar"][0]["cihaz_sayisi"] == 0
    assert r["cihaz_toplam"] == 0


def test_bos_terimde_lokasyon_da_bos(client, veri):
    r = client.get("/assets/ara", params={"q": ""}).json()
    assert r["lokasyonlar"] == [] and r["lokasyon_toplam"] == 0


def test_lokasyon_filtresi_proje_filtresiyle_ayni_sonucu_verir(client, veri):
    """Arayüz proje kodlu lokasyonu seçince proje filtresine geçiyor."""
    proje = client.get("/assets", params={"proje_kodu": "U023"}).json()
    lokasyon = client.get("/assets",
                          params={"location_id": veri["lok"]["id"]}).json()
    assert {a["asset_tag"] for a in proje} == {a["asset_tag"] for a in lokasyon}
