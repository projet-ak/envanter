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
    ("Güvenlik Duvarı", "firewall"),   # artık ayrı tür
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


@pytest.mark.parametrize("kategori,beklenen", [
    # Gerçek veride görülen yazım varyantları
    ("Swich", "switch"),
    ("POE Swtich 16 Port", "switch"),
    ("Wi-Fi Access Point", "access_point"),
    ("AccessPoint", "access_point"),
    ("Kablosuz Erişim Noktası", "access_point"),
    ("Fiber Modül", "sfp"),
    ("QSFP+ Modül", "sfp"),
    ("Patch Panel 24 Port", "kabinet"),
    ("Media Converter", "diger"),
    # Ağ olmayan ama benzer harf içerenler yanlış eşleşmemeli
    ("Klavye", None),
    ("Yazıcı", None),
    ("Kablo Kanalı", None),
])
def test_yazim_varyantlari_da_yakalanir(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


@pytest.mark.parametrize("kategori,beklenen", [
    # Dongle ve bridge erişim noktası değil — "diğer ağ ürünü"
    ("Wi-Fi Dongle", "diger"),
    ("Wireless Bridge", "diger"),
    ("Wireless Adapter", "diger"),
    # Gerçek erişim noktaları access_point kalmalı
    ("Access Point", "access_point"),
    ("Kablosuz Erişim Noktası", "access_point"),
    # Ağ ile ilgisi olmayan dongle eşleşmemeli
    ("Bluetooth Dongle", None),
])
def test_dongle_ve_bridge_dogru_siniflanir(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


# --------------------------------------------------------------------------- #
# NVR / kayıt cihazı
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kategori,beklenen", [
    ("NVR", "nvr"),
    ("NVR Kayıt Cihazı", "nvr"),
    ("DVR", "nvr"),
    ("Kamera Kayıt Cihazı", "nvr"),
    # Ağ cihazının yedek parçası ağ ürünü sayılmaz
    ("NVR Diski", None),
    ("Switch Fanı", None),
    ("Access Point Adaptörü", None),
    # SFP'nin kendisi bir modül; parça denetimi onu elemez
    ("SFP / Modül", "sfp"),
    ("Fiber Modül", "sfp"),
])
def test_nvr_ve_yedek_parca_ayrimi(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_nvr_alanlari_kanal_ve_disk_icerir(client):
    s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "nvr")
    alanlar = {a["ad"] for a in s["alanlar"]}
    assert {"Kanal Sayısı", "Disk Yuvası", "PoE Portu", "RAID"} <= alanlar


def test_nvr_urunu_eklenir_ve_listelenir(client):
    r = client.post("/ag/urunler", json={
        "tur": "nvr", "asset_tag": "NVR-01", "marka": "HIKVISION",
        "model": "DS-7616NI-K2/16P",
        "ozellikler": {"Kanal Sayısı": "16", "PoE Portu": "16",
                       "Disk Yuvası": "2", "Çözünürlük": "8 MP (4K)"}})
    assert r.status_code == 201
    u = client.get("/ag/urunler", params={"tur": "nvr"}).json()[0]
    assert u["asset_tag"] == "NVR-01"
    assert u["ozellikler"]["Kanal Sayısı"] == "16"


def test_nvr_ozette_ayri_tur_olarak_sayilir(client):
    client.post("/ag/urunler", json={"tur": "nvr", "asset_tag": "NVR-A"})
    client.post("/ag/urunler", json={"tur": "nvr", "asset_tag": "NVR-B"})
    turler = {d["tur"]: d["adet"] for d in client.get("/ag/ozet").json()["tur_dagilimi"]}
    assert turler["nvr"] == 2


@pytest.mark.parametrize("kategori,beklenen", [
    # Tamlamanın başı sonda: konu kablo/disk ise parça, değilse cihaz
    ("Switch Kablosu", None),
    ("Kablosuz Erişim Noktası", "access_point"),
    ("Kablosuz Access Point", "access_point"),
    ("NVR Güç Adaptörü", None),
    ("Switch Rafı", None),
])
def test_tamlama_basi_sonda_kuralı(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


# --------------------------------------------------------------------------- #
# Aileler: ağ ürünleri / yangın sistemleri
# --------------------------------------------------------------------------- #
def test_aileler_listelenir(client):
    a = {x["aile"] for x in client.get("/ag/aileler").json()}
    assert a == {"ag", "yangin"}


def test_sablon_aileye_gore_filtrelenir(client):
    ag_turler = {x["tur"] for x in client.get("/ag/sablon",
                                              params={"aile": "ag"}).json()}
    yangin_turler = {x["tur"] for x in client.get("/ag/sablon",
                                                  params={"aile": "yangin"}).json()}
    assert {"switch", "sfp", "firewall", "ptp"} <= ag_turler
    assert {"yangin_panel", "dedektor", "yangin_buton", "beam"} <= yangin_turler
    assert not (ag_turler & yangin_turler), "türler iki aileye birden giremez"


def test_her_turun_ailesi_var(client):
    for s in client.get("/ag/sablon").json():
        assert s["aile"] in ("ag", "yangin"), f"{s['tur']} ailesiz"


def test_bilinmeyen_aile_reddedilir(client):
    for yol, par in [("/ag/sablon", {"aile": "yok"}),
                     ("/ag/urunler", {"aile": "yok"}),
                     ("/ag/ozet", {"aile": "yok"})]:
        assert client.get(yol, params=par).status_code == 400


@pytest.fixture
def yangin_sahne(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE U040",
                                          "proje_kodu": "U040"}).json()
    client.post("/ag/urunler", json={
        "tur": "yangin_panel", "asset_tag": "YP-1", "marka": "Mavigard",
        "model": "MGA-2000-2", "location_id": lok["id"],
        "ozellikler": {"Sistem Tipi": "Adresli", "Çevrim Sayısı": "2",
                       "Adres Kapasitesi": "127"}})
    client.post("/ag/urunler", json={
        "tur": "dedektor", "asset_tag": "DD-1", "location_id": lok["id"],
        "ozellikler": {"Algılama Tipi": "Optik Duman", "Kapsama Alanı": "60"}})
    client.post("/ag/urunler", json={
        "tur": "yangin_buton", "asset_tag": "YB-1", "location_id": lok["id"],
        "ozellikler": {"Cihaz Tipi": "Yangın İhbar Butonu"}})
    client.post("/ag/urunler", json={
        "tur": "beam", "asset_tag": "YN-1", "location_id": lok["id"],
        "ozellikler": {"Parça Tipi": "Yansıtıcı (prizma)", "Yansıtıcı Sayısı": "4"}})
    return {"lok": lok}


def test_yangin_urunleri_ag_ekraninda_gorunmez(client, sahne, yangin_sahne):
    ag_liste = {u["asset_tag"] for u in
                client.get("/ag/urunler", params={"aile": "ag"}).json()}
    yangin_liste = {u["asset_tag"] for u in
                    client.get("/ag/urunler", params={"aile": "yangin"}).json()}
    assert {"SW-01", "SW-CORE"} <= ag_liste
    assert not ({"YP-1", "DD-1", "YB-1", "YN-1"} & ag_liste)
    assert {"YP-1", "DD-1", "YB-1", "YN-1"} == yangin_liste


def test_ailesiz_sorgu_hepsini_getirir(client, sahne, yangin_sahne):
    hepsi = {u["asset_tag"] for u in client.get("/ag/urunler").json()}
    assert {"SW-01", "YP-1"} <= hepsi


def test_yangin_ozeti_ayri_hesaplanir(client, sahne, yangin_sahne):
    o = client.get("/ag/ozet", params={"aile": "yangin"}).json()
    assert o["toplam"] == 4
    turler = {d["tur"] for d in o["tur_dagilimi"]}
    assert turler == {"yangin_panel", "dedektor", "yangin_buton", "beam"}
    assert o["lokasyon_dagilimi"] == [{"lokasyon": "ŞANTİYE U040", "adet": 4}]


def test_yangin_ozellikleri_aranabilir(client, yangin_sahne):
    r = client.get("/ag/urunler", params={"aile": "yangin", "q": "optik duman"}).json()
    assert [u["asset_tag"] for u in r] == ["DD-1"]
    r2 = client.get("/ag/urunler", params={"q": "prizma"}).json()
    assert [u["asset_tag"] for u in r2] == ["YN-1"]


# --------------------------------------------------------------------------- #
# Güvenlik duvarı router'dan ayrı
# --------------------------------------------------------------------------- #
def test_guvenlik_duvari_ayri_tur(client):
    client.post("/ag/urunler", json={
        "tur": "firewall", "asset_tag": "FW-1", "marka": "Fortinet",
        "model": "FortiGate 60F",
        "ozellikler": {"Throughput": "10 Gbps", "VPN": "IPSec + SSL-VPN"}})
    client.post("/ag/urunler", json={"tur": "router", "asset_tag": "RT-1"})

    fw = client.get("/ag/urunler", params={"tur": "firewall"}).json()
    rt = client.get("/ag/urunler", params={"tur": "router"}).json()
    assert [u["asset_tag"] for u in fw] == ["FW-1"]
    assert [u["asset_tag"] for u in rt] == ["RT-1"]


def test_firewall_alanlari_router_dan_farkli(client):
    fw = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "firewall")
    rt = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "router")
    fw_alan = {a["ad"] for a in fw["alanlar"]}
    assert {"VPN Throughput", "Eşzamanlı Oturum", "HA", "Lisans Bitiş"} <= fw_alan
    assert "Bağlantı Tipi" in {a["ad"] for a in rt["alanlar"]}


# --------------------------------------------------------------------------- #
# Noktadan noktaya link
# --------------------------------------------------------------------------- #
def test_ptp_alanlari(client):
    s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "ptp")
    alanlar = {a["ad"] for a in s["alanlar"]}
    assert {"Frekans", "Menzil", "Anten Kazancı", "Mod", "Rol", "Karşı Uç"} <= alanlar


def test_ptp_urunu_karsi_ucuyla_kaydedilir(client):
    client.post("/ag/urunler", json={
        "tur": "ptp", "asset_tag": "PTP-1", "marka": "Ubiquiti",
        "ozellikler": {"Frekans": "5 GHz", "Menzil": "5 km",
                       "Rol": "Master (AP)", "Karşı Uç": "ŞANTİYE U026"}})
    u = client.get("/ag/urunler", params={"tur": "ptp"}).json()[0]
    assert u["ozellikler"]["Karşı Uç"] == "ŞANTİYE U026"


# --------------------------------------------------------------------------- #
# Kategori eşleştirme
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kategori,beklenen", [
    ("Yangın Alarm Paneli", "yangin_panel"),
    ("Yangın Santrali", "yangin_panel"),
    ("Adresli Duman Dedektörü", "dedektor"),
    ("Isı Sensörü", "dedektor"),
    ("Yangın İhbar Butonu", "yangin_buton"),
    ("Siren", "yangin_buton"),
    ("Flaşör", "yangin_buton"),
    ("Beam Dedektör", "beam"),
    ("Yansıtıcı Prizma", "beam"),
    ("Yangın Dolabı", "yangin_diger"),
    ("Yangın Tüpü", "yangin_diger"),
    ("Güvenlik Duvarı", "firewall"),
    ("Firewall", "firewall"),
    ("UTM Cihazı", "firewall"),
    ("Noktadan Noktaya Link", "ptp"),
    ("NanoStation", "ptp"),
    ("Router", "router"),
    ("Modem", "router"),
])
def test_yangin_ve_yeni_turler_kategoriden_bulunur(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_yangin_kategorileri_dogru_aileye_duser():
    for kategori in ("Yangın Alarm Paneli", "Duman Dedektörü", "Siren",
                     "Beam Dedektör", "Yangın Tüpü"):
        tur = ag.tur_bul(kategori)
        assert ag.TURLER[tur]["aile"] == "yangin", f"{kategori} yanlış ailede"
