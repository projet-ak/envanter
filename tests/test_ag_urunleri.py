"""Ağ / network ürünleri: türler, teknik alanlar, listeleme, özet, transfer."""

import pytest

from app import ag


@pytest.fixture
def sahne(client):
    """İki şantiye, birkaç switch ve SFP modülü."""
    u25 = client.post("/locations", json={"name": "ŞANTİYE U025",
                                          "proje_kodu": "U025"}).json()
    u30 = client.post("/locations", json={"name": "ŞANTİYE U030-U031",
                                          "proje_kodu": "U030"}).json()
    sw = client.post("/ag/urunler", json={
        "tur": "switch", "asset_tag": "SW-01", "marka": "HUAWEI",
        "model": "S5735-L24T4S-A", "location_id": u30["id"],
        "ozellikler": {"Port Sayısı": "24", "PoE": "PoE+ (802.3at)",
                       "Katman": "Erişim (Access)", "Port Hızı": "1 Gbps"}}).json()
    core = client.post("/ag/urunler", json={
        "tur": "switch", "asset_tag": "SW-CORE", "marka": "Cisco",
        "model": "C9300-48P", "location_id": u30["id"],
        "ozellikler": {"Port Sayısı": "48", "PoE": "PoE++ (802.3bt)",
                       "Katman": "Omurga (Core)"}}).json()
    sfp = client.post("/ag/urunler", json={
        "tur": "sfp", "serial": "30004735548", "marka": "HIKVISION",
        "model": "HK-SFP-1.25G-1310-DF-MM", "location_id": u25["id"],
        "ozellikler": {"Hız": "1.25G", "Dalga Boyu": "1310nm",
                       "Mod": "Multi-Mode"}}).json()
    return {"u25": u25, "u30": u30, "sw": sw, "core": core, "sfp": sfp}


# --------------------------------------------------------------------------- #
# Şablon
# --------------------------------------------------------------------------- #
def test_sablon_turleri_verir(client):
    s = client.get("/ag/sablon").json()
    turler = {x["tur"] for x in s}
    assert {"switch", "sfp", "access_point", "router", "kabinet"} <= turler


def test_switch_alanlari_beklenenleri_icerir(client):
    s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "switch")
    alanlar = {a["ad"] for a in s["alanlar"]}
    assert {"Port Sayısı", "PoE", "Katman", "Port Hızı", "Uplink"} <= alanlar
    poe = next(a for a in s["alanlar"] if a["ad"] == "PoE")
    assert poe["tip"] == "secim" and "PoE+ (802.3at)" in poe["secenekler"]
    katman = next(a for a in s["alanlar"] if a["ad"] == "Katman")
    assert any("Omurga" in o for o in katman["secenekler"])


def test_sfp_alanlari_hiz_mesafe_mod_icerir(client):
    s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "sfp")
    alanlar = {a["ad"] for a in s["alanlar"]}
    assert {"Hız", "Dalga Boyu", "Mesafe", "Mod", "Konnektör"} <= alanlar


# --------------------------------------------------------------------------- #
# Ekleme
# --------------------------------------------------------------------------- #
def test_urun_eklenir_ve_kategorisi_acilir(client, sahne):
    kategoriler = {k["name"] for k in client.get("/categories").json()}
    assert {"Switch", "SFP / Modül"} <= kategoriler
    markalar = {m["name"] for m in client.get("/manufacturers").json()}
    assert {"HUAWEI", "Cisco", "HIKVISION"} <= markalar


def test_seri_no_etiket_olarak_kullanilir(client, sahne):
    """Cihaz no verilmezse seri no etiket olur (SFP'lerde tipik)."""
    urun = client.get("/ag/urunler", params={"q": "30004735548"}).json()[0]
    assert urun["asset_tag"] == "30004735548"
    assert urun["serial"] == "30004735548"


def test_etiket_ve_seri_yoksa_reddedilir(client):
    r = client.post("/ag/urunler", json={"tur": "switch", "marka": "X"})
    assert r.status_code == 400


def test_ayni_etiket_iki_kez_eklenemez(client, sahne):
    r = client.post("/ag/urunler", json={"tur": "switch", "asset_tag": "SW-01"})
    assert r.status_code == 409


def test_bilinmeyen_tur_reddedilir(client):
    assert client.post("/ag/urunler",
                       json={"tur": "uzay_gemisi", "asset_tag": "X"}).status_code == 400
    assert client.get("/ag/urunler", params={"tur": "yok"}).status_code == 400


def test_viewer_ekleyemez(viewer_client):
    assert viewer_client.post("/ag/urunler",
                              json={"tur": "switch", "asset_tag": "V-1"}).status_code == 403


# --------------------------------------------------------------------------- #
# Listeleme ve filtreler
# --------------------------------------------------------------------------- #
def test_ture_gore_filtrelenir(client, sahne):
    switchler = client.get("/ag/urunler", params={"tur": "switch"}).json()
    assert {u["asset_tag"] for u in switchler} == {"SW-01", "SW-CORE"}
    sfpler = client.get("/ag/urunler", params={"tur": "sfp"}).json()
    assert [u["asset_tag"] for u in sfpler] == ["30004735548"]


def test_lokasyona_gore_filtrelenir(client, sahne):
    r = client.get("/ag/urunler", params={"location_id": sahne["u25"]["id"]}).json()
    assert [u["asset_tag"] for u in r] == ["30004735548"]


def test_proje_koduna_gore_filtrelenir(client, sahne):
    r = client.get("/ag/urunler", params={"proje_kodu": "U030"}).json()
    assert {u["asset_tag"] for u in r} == {"SW-01", "SW-CORE"}


def test_ozelliklerde_aranir(client, sahne):
    """Teknik özellik değerleri de aramaya girmeli."""
    assert {u["asset_tag"] for u in
            client.get("/ag/urunler", params={"q": "1310nm"}).json()} == {"30004735548"}
    assert {u["asset_tag"] for u in
            client.get("/ag/urunler", params={"q": "omurga"}).json()} == {"SW-CORE"}


def test_arama_turkce_duyarli(client, sahne):
    assert client.get("/ag/urunler", params={"q": "erisim"}).json()


def test_liste_ozellikleri_ve_lokasyonu_getirir(client, sahne):
    u = client.get("/ag/urunler", params={"q": "SW-01"}).json()[0]
    assert u["tur"] == "switch"
    assert u["marka"] == "HUAWEI" and u["model"] == "S5735-L24T4S-A"
    assert u["ozellikler"]["Port Sayısı"] == "24"
    assert u["lokasyon"] == "ŞANTİYE U030-U031" and u["proje_kodu"] == "U030"


def test_ag_disi_cihazlar_listede_yok(client, sahne):
    client.post("/assets", json={"asset_tag": "LAPTOP-1", "name": "Dizüstü"})
    assert "LAPTOP-1" not in {u["asset_tag"]
                              for u in client.get("/ag/urunler").json()}


# --------------------------------------------------------------------------- #
# Özet
# --------------------------------------------------------------------------- #
def test_ozet_tur_ve_port_sayilarini_verir(client, sahne):
    o = client.get("/ag/ozet").json()
    assert o["toplam"] == 3
    assert o["toplam_port"] == 72          # 24 + 48
    assert o["poe_cihaz"] == 2
    turler = {d["tur"]: d["adet"] for d in o["tur_dagilimi"]}
    assert turler == {"switch": 2, "sfp": 1}


def test_ozet_lokasyon_dagilimi(client, sahne):
    o = client.get("/ag/ozet").json()
    dagilim = {d["lokasyon"]: d["adet"] for d in o["lokasyon_dagilimi"]}
    assert dagilim == {"ŞANTİYE U030-U031": 2, "ŞANTİYE U025": 1}


def test_poe_yok_sayilmaz(client, sahne):
    client.post("/ag/urunler", json={
        "tur": "switch", "asset_tag": "SW-NOPOE", "ozellikler": {"PoE": "Yok"}})
    assert client.get("/ag/ozet").json()["poe_cihaz"] == 2   # değişmemeli


def test_bozuk_port_sayisi_ozeti_dusurmez(client, sahne):
    """Elle girilmiş '24 port' gibi değerler hata vermemeli."""
    client.post("/ag/urunler", json={
        "tur": "switch", "asset_tag": "SW-BOZUK",
        "ozellikler": {"Port Sayısı": "yirmi dört"}})
    assert client.get("/ag/ozet").json()["toplam_port"] == 72


# --------------------------------------------------------------------------- #
# Özellik güncelleme
# --------------------------------------------------------------------------- #
def test_ozellikler_guncellenir(client, sahne):
    r = client.put(f"/ag/urunler/{sahne['sw']['id']}/ozellikler",
                   json={"Port Sayısı": "48", "PoE": "Yok"})
    assert r.status_code == 200
    u = client.get("/ag/urunler", params={"q": "SW-01"}).json()[0]
    assert u["ozellikler"] == {"Port Sayısı": "48", "PoE": "Yok"}


def test_bos_deger_ozelligi_siler(client, sahne):
    client.put(f"/ag/urunler/{sahne['sw']['id']}/ozellikler",
               json={"Port Sayısı": "24", "PoE": ""})
    u = client.get("/ag/urunler", params={"q": "SW-01"}).json()[0]
    assert "PoE" not in u["ozellikler"]


def test_ozellik_guncelleme_kalici(client, sahne):
    """JSON sütunu yerinde değişikliği izlemez; kayıt gerçekten yazılmalı."""
    client.put(f"/ag/urunler/{sahne['core']['id']}/ozellikler",
               json={"Katman": "Dağıtım (Distribution)"})
    a = client.get(f"/assets/{sahne['core']['id']}").json()
    assert a["custom"]["Ağ"]["Katman"] == "Dağıtım (Distribution)"


def test_olmayan_urunun_ozelligi_404(client):
    assert client.put("/ag/urunler/999999/ozellikler",
                      json={"PoE": "Yok"}).status_code == 404


# --------------------------------------------------------------------------- #
# Transferler
# --------------------------------------------------------------------------- #
def test_lokasyon_degisimi_transfer_olarak_gorunur(client, sahne):
    client.put(f"/assets/{sahne['sfp']['id']}",
               json={"location_id": sahne["u30"]["id"]})
    t = client.get("/ag/transferler").json()
    assert len(t) == 1
    assert t[0]["asset_tag"] == "30004735548"
    assert "U025" in t[0]["nereden"] and "U030" in t[0]["nereye"]


def test_lokasyon_disi_degisiklik_transfer_sayilmaz(client, sahne):
    client.put(f"/assets/{sahne['sw']['id']}", json={"name": "Yeni ad"})
    assert client.get("/ag/transferler").json() == []


def test_ayni_lokasyona_guncelleme_transfer_degil(client, sahne):
    client.put(f"/assets/{sahne['sw']['id']}",
               json={"location_id": sahne["u30"]["id"]})
    assert client.get("/ag/transferler").json() == []


# --------------------------------------------------------------------------- #
# Kategori adından tür çıkarımı (içe aktarılmış kayıtlar için)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kategori,beklenen", [
    ("Switch", "switch"),
    ("POE Switch 24 Port", "switch"),
    ("Access Point", "access_point"),
    ("SFP Modül", "sfp"),
    ("Transceiver", "sfp"),
    ("Router", "router"),
    ("Güvenlik Duvarı", "router"),
    ("Rack Kabinet", "kabinet"),
    ("Dizüstü Bilgisayar", None),
    ("Monitör", None),
    (None, None),
])
def test_kategori_adindan_tur_bulunur(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_excelden_gelen_switchler_de_listelenir(client):
    """İçe aktarımla gelmiş 'POE Switch 8 Port' kategorisi ağ ürünü sayılmalı."""
    kat = client.post("/categories", json={"name": "POE Switch 8 Port"}).json()
    mdl = client.post("/models", json={"name": "TL-SF1009P",
                                       "category_id": kat["id"]}).json()
    client.post("/assets", json={"asset_tag": "ESKI-SW", "model_id": mdl["id"]})

    liste = client.get("/ag/urunler", params={"tur": "switch"}).json()
    assert "ESKI-SW" in {u["asset_tag"] for u in liste}


def test_giris_sart(anon_client):
    assert anon_client.get("/ag/urunler").status_code == 401
    assert anon_client.get("/ag/ozet").status_code == 401
