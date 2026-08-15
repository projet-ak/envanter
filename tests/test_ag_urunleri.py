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
    assert a == {"ag", "yangin", "alarm", "gecis", "kantar"}


def test_sablon_aileye_gore_filtrelenir(client):
    ag_turler = {x["tur"] for x in client.get("/ag/sablon",
                                              params={"aile": "ag"}).json()}
    yangin_turler = {x["tur"] for x in client.get("/ag/sablon",
                                                  params={"aile": "yangin"}).json()}
    alarm_turler = {x["tur"] for x in client.get("/ag/sablon",
                                                 params={"aile": "alarm"}).json()}
    assert {"switch", "sfp", "firewall", "ptp"} <= ag_turler
    assert {"yangin_panel", "dedektor", "yangin_buton", "beam"} <= yangin_turler
    assert {"alarm_panel", "alarm_dedektor", "alarm_keypad", "alarm_siren",
            "alarm_modul"} <= alarm_turler
    assert not (ag_turler & yangin_turler), "türler iki aileye birden giremez"
    assert not (alarm_turler & (ag_turler | yangin_turler))


def test_her_tur_tek_bir_ailede():
    """Aileler kesişmemeli: bir tür yalnızca tek ekranda görünür."""
    esleme = {}
    for tur, bilgi in ag.TURLER.items():
        esleme.setdefault(bilgi["aile"], set()).add(tur)
    tumu = [t for kume in esleme.values() for t in kume]
    assert len(tumu) == len(set(tumu)) == len(ag.TURLER)
    assert set(esleme) == set(ag.AILELER), "ailesi olmayan/boş aile var"


def test_her_turun_ailesi_var(client):
    for s in client.get("/ag/sablon").json():
        assert s["aile"] in ag.AILELER, f"{s['tur']} ailesiz"


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
    ("LigoWave LigoDLB 5-15", "ptp"),
    ("LigoDLB PRO 5-20n", "ptp"),
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


# --------------------------------------------------------------------------- #
# Alarm sistemleri (kablolu / kablosuz)
# --------------------------------------------------------------------------- #
@pytest.fixture
def alarm_sahne(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE U050",
                                          "proje_kodu": "U050"}).json()
    client.post("/ag/urunler", json={
        "tur": "alarm_panel", "asset_tag": "AP-1", "marka": "Paradox",
        "model": "SP6000", "location_id": lok["id"],
        "ozellikler": {"Bağlantı Tipi": "Hibrit (kablolu + kablosuz)",
                       "Zon Sayısı": "8", "Kablosuz Zon": "32",
                       "Frekans": "433 MHz", "Haberleşme": "GSM + IP",
                       "Bölme": "2"}})
    client.post("/ag/urunler", json={
        "tur": "alarm_dedektor", "asset_tag": "AD-1", "marka": "Paradox",
        "model": "NV5", "location_id": lok["id"],
        "ozellikler": {"Algılama Tipi": "PIR (Hareket)",
                       "Bağlantı Tipi": "Kablolu", "Menzil": "12",
                       "Algılama Açısı": "110",
                       "Evcil Hayvan": "Var (25 kg'a kadar)"}})
    client.post("/ag/urunler", json={
        "tur": "alarm_dedektor", "asset_tag": "AD-2", "location_id": lok["id"],
        "ozellikler": {"Algılama Tipi": "Manyetik Kontak",
                       "Bağlantı Tipi": "Kablosuz", "Frekans": "868 MHz",
                       "Pil Tipi": "CR123A", "Pil Ömrü": "2 yıl"}})
    client.post("/ag/urunler", json={
        "tur": "alarm_keypad", "asset_tag": "AK-1", "location_id": lok["id"],
        "ozellikler": {"Cihaz Tipi": "Tuş Takımı (LCD)",
                       "Bağlantı Tipi": "Kablolu"}})
    client.post("/ag/urunler", json={
        "tur": "alarm_siren", "asset_tag": "AS-1", "location_id": lok["id"],
        "ozellikler": {"Cihaz Tipi": "Dış Mekan Siren", "Ses Seviyesi": "110",
                       "IP Sınıfı": "IP65"}})
    client.post("/ag/urunler", json={
        "tur": "alarm_modul", "asset_tag": "AM-1", "location_id": lok["id"],
        "ozellikler": {"Modül Tipi": "Kablosuz Alıcı (receiver)",
                       "Frekans": "433 MHz", "Kanal Sayısı": "32",
                       "Uyumlu Panel": "Paradox SP serisi"}})
    return {"lok": lok}


def test_alarm_urunleri_diger_ailelerde_gorunmez(client, sahne, yangin_sahne,
                                                 alarm_sahne):
    alarm = {u["asset_tag"] for u in
             client.get("/ag/urunler", params={"aile": "alarm"}).json()}
    agl = {u["asset_tag"] for u in
           client.get("/ag/urunler", params={"aile": "ag"}).json()}
    yng = {u["asset_tag"] for u in
           client.get("/ag/urunler", params={"aile": "yangin"}).json()}
    assert alarm == {"AP-1", "AD-1", "AD-2", "AK-1", "AS-1", "AM-1"}
    assert not (alarm & agl) and not (alarm & yng)
    assert not ({"YP-1", "DD-1"} & alarm), "yangın ürünü alarm ekranına düşmemeli"


def test_alarm_ozeti(client, alarm_sahne):
    o = client.get("/ag/ozet", params={"aile": "alarm"}).json()
    assert o["toplam"] == 6
    turler = {d["tur"]: d["adet"] for d in o["tur_dagilimi"]}
    assert turler == {"alarm_panel": 1, "alarm_dedektor": 2, "alarm_keypad": 1,
                      "alarm_siren": 1, "alarm_modul": 1}
    assert o["lokasyon_dagilimi"] == [{"lokasyon": "ŞANTİYE U050", "adet": 6}]


def test_kablosuz_alarm_alanlari(client):
    """Kablosuz cihazlarda frekans, pil ve menzil sorulabilmeli."""
    for tur in ("alarm_panel", "alarm_dedektor", "alarm_keypad", "alarm_siren",
                "alarm_modul"):
        s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == tur)
        adlar = {a["ad"] for a in s["alanlar"]}
        assert "Bağlantı Tipi" in adlar, f"{tur}: kablolu/kablosuz ayrımı yok"
        assert "Frekans" in adlar, f"{tur}: kablosuz frekans alanı yok"
    ded = next(x for x in client.get("/ag/sablon").json()
               if x["tur"] == "alarm_dedektor")
    adlar = {a["ad"] for a in ded["alanlar"]}
    assert {"Pil Tipi", "Pil Ömrü", "Menzil", "Algılama Açısı",
            "Evcil Hayvan", "Tamper"} <= adlar


def test_alarm_ozellikleri_aranabilir(client, alarm_sahne):
    r = client.get("/ag/urunler", params={"aile": "alarm",
                                          "q": "manyetik kontak"}).json()
    assert [u["asset_tag"] for u in r] == ["AD-2"]
    r2 = client.get("/ag/urunler", params={"q": "868 MHz"}).json()
    assert [u["asset_tag"] for u in r2] == ["AD-2"]


def test_alarm_dedektoru_kablosuz_kaydedilir(client, alarm_sahne):
    u = next(x for x in client.get("/ag/urunler",
                                   params={"tur": "alarm_dedektor"}).json()
             if x["asset_tag"] == "AD-2")
    assert u["ozellikler"]["Bağlantı Tipi"] == "Kablosuz"
    assert u["ozellikler"]["Frekans"] == "868 MHz"
    assert u["ozellikler"]["Pil Tipi"] == "CR123A"


@pytest.mark.parametrize("kategori,beklenen", [
    # Alarm tarafı
    ("Alarm Paneli", "alarm_panel"),
    ("Kablosuz Alarm Paneli", "alarm_panel"),
    ("Hırsız Alarm Paneli", "alarm_panel"),
    ("Alarm Santrali", "alarm_panel"),
    ("PIR", "alarm_dedektor"),
    ("PIR Dedektörü", "alarm_dedektor"),
    ("Hareket Dedektörü", "alarm_dedektor"),
    ("Kablosuz Manyetik Kontak", "alarm_dedektor"),
    ("Cam Kırılma Dedektörü", "alarm_dedektor"),
    ("Perde Tipi Dedektör", "alarm_dedektor"),
    ("Tuş Takımı", "alarm_keypad"),
    ("Uzaktan Kumanda", "alarm_keypad"),
    ("Panik Butonu", "alarm_keypad"),
    ("Alarm Sireni", "alarm_siren"),
    ("Dış Mekan Siren", "alarm_siren"),
    ("Zon Genişletme Modülü", "alarm_modul"),
    ("Kablosuz Alıcı", "alarm_modul"),
    ("GSM Modülü", "alarm_modul"),
    # Yangın tarafı alarm kurallarına kapılmamalı
    ("Yangın Alarm Paneli", "yangin_panel"),
    ("Yangın Alarm Sireni", "yangin_buton"),
    ("Siren", "yangin_buton"),
    ("Duman Dedektörü", "dedektor"),
    ("Isı Dedektörü", "dedektor"),
    # Ağ tarafı da bozulmamalı
    ("Kablosuz Erişim Noktası", "access_point"),
    ("Kablosuz Link", "ptp"),
    ("Wi-Fi Dongle", "diger"),
    # Yedek parçalar hiçbir aileye girmez
    ("Alarm Paneli Bataryası", None),
    ("Dedektör Pili", None),
])
def test_alarm_kategorileri_dogru_ture_duser(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_alarm_kategorileri_dogru_aileye_duser():
    for kategori in ("Alarm Paneli", "PIR Dedektörü", "Tuş Takımı",
                     "Alarm Sireni", "GSM Modülü"):
        tur = ag.tur_bul(kategori)
        assert ag.TURLER[tur]["aile"] == "alarm", f"{kategori} yanlış ailede"


def test_her_turun_kendi_kategori_adi_kendine_doner():
    """Ürün eklenince kategori `kategori_adi(tur)` ile açılır; o ad geri
    okununca aynı türü vermezse ürün yanlış ailede listelenir."""
    for tur in ag.TURLER:
        assert ag.tur_bul(ag.kategori_adi(tur)) == tur, \
            f"{tur}: '{ag.kategori_adi(tur)}' → {ag.tur_bul(ag.kategori_adi(tur))}"


# --------------------------------------------------------------------------- #
# Geçiş sistemleri: kart, bariyer, plaka tanıma
# --------------------------------------------------------------------------- #
@pytest.fixture
def gecis_sahne(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE U060",
                                          "proje_kodu": "U060"}).json()
    client.post("/ag/urunler", json={
        "tur": "kart_okuyucu", "asset_tag": "KO-1", "marka": "ZKTeco",
        "model": "SF200", "location_id": lok["id"],
        "ozellikler": {"Cihaz Tipi": "Kart + Parmak İzi",
                       "Kart Teknolojisi": "Mifare 13.56 MHz",
                       "Haberleşme": "Wiegand 26", "Kullanım": "PDKS (personel devam)",
                       "Kullanıcı Kapasitesi": "3000"}})
    client.post("/ag/urunler", json={
        "tur": "kart_yazici", "asset_tag": "KY-1", "marka": "Evolis",
        "model": "Primacy 2", "location_id": lok["id"],
        "ozellikler": {"Baskı Tipi": "Çift Yüz", "Baskı Rengi": "Renkli (YMCKO)",
                       "Çözünürlük": "300 dpi", "Kodlama": "Mifare / RFID",
                       "Bağlantı": "USB + Ethernet", "Hız": "180 kart/saat"}})
    client.post("/ag/urunler", json={
        "tur": "bariyer", "asset_tag": "BR-1", "marka": "CAME",
        "model": "Gard 4040", "location_id": lok["id"],
        "ozellikler": {"Kol Tipi": "Düz Kol", "Kol Uzunluğu": "4",
                       "Motor Tipi": "Elektromekanik", "Kontrol": "Plaka Tanıma",
                       "Güvenlik": "Fotosel + Loop Dedektör", "Yön": "Giriş"}})
    client.post("/ag/urunler", json={
        "tur": "bariyer_parca", "asset_tag": "BP-1", "location_id": lok["id"],
        "ozellikler": {"Parça Tipi": "Bariyer Kolu", "Uyumlu Model": "CAME Gard 4040",
                       "Ölçü": "4 m alüminyum kol", "Adet": "2"}})
    client.post("/ag/urunler", json={
        "tur": "plaka_kamera", "asset_tag": "PK-1", "marka": "Hikvision",
        "model": "iDS-2CD7A46G0", "location_id": lok["id"],
        "ozellikler": {"Çözünürlük": "4 MP", "Okuma Mesafesi": "15",
                       "Azami Hız": "60", "Aydınlatma": "IR + Beyaz Işık",
                       "Yön": "Giriş", "Besleme": "PoE"}})
    client.post("/ag/urunler", json={
        "tur": "plaka_tanima", "asset_tag": "PT-1", "location_id": lok["id"],
        "ozellikler": {"Bileşen Tipi": "Sunucu / Yazılım", "Kanal Sayısı": "4",
                       "Entegrasyon": "Bariyer + Kantar",
                       "Plaka Formatı": "TR (Türkiye)"}})
    return {"lok": lok}


@pytest.fixture
def kantar_sahne(client, gecis_sahne):
    lok = gecis_sahne["lok"]
    client.post("/ag/urunler", json={
        "tur": "kantar_platform", "asset_tag": "KN-1", "marka": "Baykon",
        "location_id": lok["id"],
        "ozellikler": {"Kantar Tipi": "Araç Kantarı (köprü)", "Kapasite": "60",
                       "Platform Ölçüsü": "18 x 3 m", "Yük Hücresi Sayısı": "8",
                       "Bölüntü": "20", "Yapı": "Çelik + Beton",
                       "Damga Bitiş": "31.12.2027"}})
    for i in (1, 2):
        client.post("/ag/urunler", json={
            "tur": "loadcell", "asset_tag": f"LC-{i}", "marka": "Zemic",
            "model": "HM9B", "location_id": lok["id"],
            "ozellikler": {"Kapasite": "30", "Hücre Tipi": "Kolon (column)",
                           "Malzeme": "Paslanmaz Çelik", "Çıkış": "2.0 mV/V",
                           "Konum": f"{i} no'lu hücre", "IP Sınıfı": "IP67"}})
    client.post("/ag/urunler", json={
        "tur": "kantar_terminal", "asset_tag": "KT-1", "marka": "Baykon",
        "model": "BX24", "location_id": lok["id"],
        "ozellikler": {"Cihaz Tipi": "Tartım Terminali", "Ekran": "LCD",
                       "Kanal Sayısı": "8", "Haberleşme": "RS232 + TCP/IP",
                       "Onay": "OIML R76"}})
    client.post("/ag/urunler", json={
        "tur": "kantar_diger", "asset_tag": "KD-1", "location_id": lok["id"],
        "ozellikler": {"Ekipman Tipi": "Bağlantı Kutusu (junction box)",
                       "Kapasite": "8 kanal", "Bağlı Kantar": "Giriş kantarı"}})
    return {"lok": lok}


def test_gecis_urunleri_kendi_ailesinde(client, sahne, gecis_sahne):
    gecis = {u["asset_tag"] for u in
             client.get("/ag/urunler", params={"aile": "gecis"}).json()}
    agl = {u["asset_tag"] for u in
           client.get("/ag/urunler", params={"aile": "ag"}).json()}
    assert gecis == {"KO-1", "KY-1", "BR-1", "BP-1", "PK-1", "PT-1"}
    assert not (gecis & agl)


def test_kantar_ozeti(client, kantar_sahne):
    o = client.get("/ag/ozet", params={"aile": "kantar"}).json()
    assert o["toplam"] == 5
    turler = {d["tur"]: d["adet"] for d in o["tur_dagilimi"]}
    assert turler == {"kantar_platform": 1, "loadcell": 2,
                      "kantar_terminal": 1, "kantar_diger": 1}


def test_gecis_ozeti_kantari_saymaz(client, kantar_sahne):
    o = client.get("/ag/ozet", params={"aile": "gecis"}).json()
    assert o["toplam"] == 6
    assert "loadcell" not in {d["tur"] for d in o["tur_dagilimi"]}


def test_kart_okuyucu_alanlari(client):
    s = next(x for x in client.get("/ag/sablon").json()
             if x["tur"] == "kart_okuyucu")
    adlar = {a["ad"] for a in s["alanlar"]}
    assert {"Cihaz Tipi", "Kart Teknolojisi", "Haberleşme", "Okuma Mesafesi",
            "Kullanıcı Kapasitesi", "Bağlı Panel"} <= adlar
    tek = next(a for a in s["alanlar"] if a["ad"] == "Kart Teknolojisi")
    assert "Mifare 13.56 MHz" in tek["secenekler"]
    hab = next(a for a in s["alanlar"] if a["ad"] == "Haberleşme")
    assert {"Wiegand 26", "OSDP", "RS485"} <= set(hab["secenekler"])


def test_kart_yazici_alanlari(client):
    s = next(x for x in client.get("/ag/sablon").json()
             if x["tur"] == "kart_yazici")
    adlar = {a["ad"] for a in s["alanlar"]}
    assert {"Baskı Tipi", "Baskı Rengi", "Çözünürlük", "Kodlama", "Laminasyon",
            "Ribbon"} <= adlar
    kod = next(a for a in s["alanlar"] if a["ad"] == "Kodlama")
    assert "Manyetik Şerit" in kod["secenekler"]


def test_bariyer_ve_parcasi_ayri_turler(client, gecis_sahne):
    br = client.get("/ag/urunler", params={"tur": "bariyer"}).json()
    bp = client.get("/ag/urunler", params={"tur": "bariyer_parca"}).json()
    assert [u["asset_tag"] for u in br] == ["BR-1"]
    assert [u["asset_tag"] for u in bp] == ["BP-1"]
    assert bp[0]["ozellikler"]["Parça Tipi"] == "Bariyer Kolu"


def test_plaka_sistemi_kamera_ve_unite(client, gecis_sahne):
    kam = client.get("/ag/urunler", params={"tur": "plaka_kamera"}).json()
    uni = client.get("/ag/urunler", params={"tur": "plaka_tanima"}).json()
    assert kam[0]["ozellikler"]["Azami Hız"] == "60"
    assert uni[0]["ozellikler"]["Entegrasyon"] == "Bariyer + Kantar"


def test_kantar_kalibrasyon_ve_hucreler(client, kantar_sahne):
    kn = client.get("/ag/urunler", params={"tur": "kantar_platform"}).json()[0]
    assert kn["ozellikler"]["Kapasite"] == "60"
    assert kn["ozellikler"]["Damga Bitiş"] == "31.12.2027"
    hucreler = client.get("/ag/urunler", params={"tur": "loadcell"}).json()
    assert {u["ozellikler"]["Konum"] for u in hucreler} == {"1 no'lu hücre",
                                                            "2 no'lu hücre"}


def test_gecis_ve_kantar_aranabilir(client, kantar_sahne):
    r = client.get("/ag/urunler", params={"q": "wiegand"}).json()
    assert [u["asset_tag"] for u in r] == ["KO-1"]
    r2 = client.get("/ag/urunler", params={"aile": "kantar", "q": "oiml"}).json()
    assert [u["asset_tag"] for u in r2] == ["KT-1"]


@pytest.mark.parametrize("kategori,beklenen", [
    ("Kart Okuyucu", "kart_okuyucu"),
    ("Proximity Kart Okuyucu", "kart_okuyucu"),
    ("Parmak İzi Okuyucu", "kart_okuyucu"),
    ("PDKS Terminali", "kart_okuyucu"),
    ("Turnike Okuyucusu", "kart_okuyucu"),
    ("Kart Yazıcı", "kart_yazici"),
    ("Kimlik Kartı Yazıcısı", "kart_yazici"),
    ("Kart Kodlayıcı", "kart_yazici"),
    # Normal ofis yazıcısı geçiş sistemi değildir
    ("Yazıcı", None),
    ("Lazer Yazıcı", None),
    ("Kart Yazıcı Ribbonu", None),
    # Bariyer ve parçaları
    ("Bariyer", "bariyer"),
    ("Kollu Bariyer", "bariyer"),
    ("Otopark Bariyeri", "bariyer"),
    ("Bariyer Kolu", "bariyer_parca"),
    ("Bariyer Motoru", "bariyer_parca"),
    ("Bariyer Kontrol Kartı", "bariyer_parca"),
    ("Loop Dedektör", "bariyer_parca"),
    ("Fotosel", "bariyer_parca"),
    # Plaka okuma
    ("Plaka Tanıma Kamerası", "plaka_kamera"),
    ("ANPR Kamera", "plaka_kamera"),
    ("Plaka Tanıma Sistemi", "plaka_tanima"),
    ("Plaka Okuma Ünitesi", "plaka_tanima"),
    # Kantar
    ("Kantar", "kantar_platform"),
    ("Araç Kantarı", "kantar_platform"),
    ("Köprü Kantarı", "kantar_platform"),
    ("Yük Hücresi", "loadcell"),
    ("Loadcell", "loadcell"),
    ("Kantar Terminali", "kantar_terminal"),
    ("İndikatör", "kantar_terminal"),
    ("Kantar Bağlantı Kutusu", "kantar_diger"),
    ("Kantar Kablosu", "kantar_diger"),
    # Kart benzeri ama ürün olmayanlar
    ("Ekran Kartı", None),
    ("Hafıza Kartı", None),
])
def test_gecis_kantar_kategorileri_dogru_ture_duser(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_bariyer_parcasi_yedek_parca_elemesine_takilmaz():
    """`_parca_mi` kablo/kart biten adları eler; parça türleri bundan muaf."""
    assert ag.tur_bul("Bariyer Kolu") == "bariyer_parca"
    assert ag.tur_bul("Kantar Kablosu") == "kantar_diger"
    assert ag.tur_bul("Switch Kablosu") is None      # eski davranış korunur


# --------------------------------------------------------------------------- #
# Mobil internet: Superbox, Vinn, USB modem
# --------------------------------------------------------------------------- #
def test_mobil_internet_hat_kunyesi_kaydedilir(client):
    """Operatör/hat/SIM/IMEI teknik özellik değil, varlığın kendi sütunları."""
    client.post("/ag/urunler", json={
        "tur": "mobil_internet", "asset_tag": "SB-1", "marka": "Turkcell",
        "model": "Superbox 5G", "operator": "Turkcell",
        "telefon_no": "0532 111 22 33", "sim_no": "8990011122233344",
        "imei": "356938035643809",
        "ozellikler": {"Cihaz Tipi": "Sabit Kablosuz (Superbox)", "Nesil": "5G",
                       "Paket": "250 GB/ay", "Taahhüt Bitiş": "31.12.2026"}})
    u = client.get("/ag/urunler", params={"tur": "mobil_internet"}).json()[0]
    assert u["operator"] == "Turkcell"
    assert u["telefon_no"] == "0532 111 22 33"
    assert u["sim_no"] == "8990011122233344"
    assert u["imei"] == "356938035643809"
    # Varlık kaydında da aynı sütunlarda durmalı (arama/dışa aktarım için)
    varlik = client.get(f"/assets/{u['id']}").json()
    assert varlik["telefon_no"] == "0532 111 22 33"
    assert varlik["imei"] == "356938035643809"


def test_hat_no_ile_aranabilir(client):
    client.post("/ag/urunler", json={
        "tur": "mobil_internet", "asset_tag": "VN-1", "marka": "Vodafone",
        "model": "Vinn", "operator": "Vodafone", "telefon_no": "0542 999 88 77"})
    r = client.get("/ag/urunler", params={"q": "0542 999"}).json()
    assert [u["asset_tag"] for u in r] == ["VN-1"]
    assert [u["asset_tag"] for u in
            client.get("/ag/urunler", params={"q": "vodafone"}).json()] == ["VN-1"]


def test_hat_bayragi_yalniz_mobil_internette(client):
    for s in client.get("/ag/sablon").json():
        assert s["hat"] is (s["tur"] == "mobil_internet"), f"{s['tur']} hat bayrağı"


@pytest.mark.parametrize("kategori,beklenen", [
    ("Superbox", "mobil_internet"),
    ("Turkcell Superbox", "mobil_internet"),
    ("Vinn", "mobil_internet"),
    ("VİN", "mobil_internet"),
    ("Mobil İnternet", "mobil_internet"),
    ("USB Modem", "mobil_internet"),
    ("4G Modem", "mobil_internet"),
    ("Mifi Cihazı", "mobil_internet"),
    # Sabit hat modemi eskisi gibi router kalır
    ("Modem", "router"),
    ("VDSL Modem", "router"),
    ("Router", "router"),
    # "Vinç" içindeki "vin" yanlış eşleşmemeli
    ("Vinç Kantarı", "kantar_platform"),
])
def test_mobil_internet_kategorileri(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


# --------------------------------------------------------------------------- #
# Sistem ürünleri genel Varlıklar listesinde görünmesin
# --------------------------------------------------------------------------- #
def test_sistem_urunleri_varlik_listesinden_gizlenebilir(client):
    kat = client.post("/categories", json={"name": "Switch"}).json()
    mdl = client.post("/models", json={"name": "SW-2960",
                                       "category_id": kat["id"]}).json()
    client.post("/assets", json={"asset_tag": "SW-1", "model_id": mdl["id"]})
    client.post("/assets", json={"asset_tag": "PC-1"})          # modelsiz
    pcKat = client.post("/categories", json={"name": "Dizüstü"}).json()
    pcMdl = client.post("/models", json={"name": "ProBook",
                                         "category_id": pcKat["id"]}).json()
    client.post("/assets", json={"asset_tag": "PC-2", "model_id": pcMdl["id"]})

    hepsi = {a["asset_tag"] for a in client.get("/assets").json()}
    assert hepsi == {"SW-1", "PC-1", "PC-2"}

    # sistem=false: switch düşer, modelsiz ve normal cihaz kalır
    genel = {a["asset_tag"] for a in
             client.get("/assets", params={"sistem": "false"}).json()}
    assert genel == {"PC-1", "PC-2"}

    # sistem=true: yalnız sistem ürünleri
    sistem = {a["asset_tag"] for a in
              client.get("/assets", params={"sistem": "true"}).json()}
    assert sistem == {"SW-1"}

    # Sayı ucu da aynı ayrımı yapar
    assert client.get("/assets/sayi",
                      params={"sistem": "false"}).json()["toplam"] == 2
    assert client.get("/assets/sayi",
                      params={"sistem": "true"}).json()["toplam"] == 1

    # Ağ ürünleri ekranı etkilenmez
    assert {u["asset_tag"] for u in
            client.get("/ag/urunler", params={"tur": "switch"}).json()} == {"SW-1"}


def test_sistem_suzgeci_diger_filtrelerle_birlikte(client):
    lok = client.post("/locations", json={"name": "ŞANTİYE X"}).json()
    kat = client.post("/categories", json={"name": "Access Point"}).json()
    mdl = client.post("/models", json={"name": "AP-1",
                                       "category_id": kat["id"]}).json()
    client.post("/assets", json={"asset_tag": "AP-A", "model_id": mdl["id"],
                                 "location_id": lok["id"]})
    client.post("/assets", json={"asset_tag": "NB-A", "location_id": lok["id"]})

    etiketler = {a["asset_tag"] for a in client.get(
        "/assets", params={"sistem": "false",
                           "location_id": lok["id"]}).json()}
    assert etiketler == {"NB-A"}


# --------------------------------------------------------------------------- #
# IP kameralar (ağ ailesi)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kategori,beklenen", [
    ("IP Kamera", "kamera"),
    ("Güvenlik Kamerası", "kamera"),
    ("Dome Kamera", "kamera"),
    ("Bullet Kamera", "kamera"),
    ("PTZ Kamera", "kamera"),
    ("CCTV Kamera", "kamera"),
    # Karışmaması gerekenler
    ("NVR / Kayıt Cihazı", "nvr"),
    ("Kamera Kayıt Cihazı", "nvr"),
    ("Plaka Tanıma Kamerası", "plaka_kamera"),
    ("Kamera Kablosu", None),          # parça
    ("Kamera Adaptörü", None),
])
def test_kamera_kategorileri(kategori, beklenen):
    assert ag.tur_bul(kategori) == beklenen


def test_kamera_sablonu_ve_ekleme(client):
    s = next(x for x in client.get("/ag/sablon").json() if x["tur"] == "kamera")
    assert s["aile"] == "ag" and s["ad"] == "IP Kamera"
    alanlar = {a["ad"] for a in s["alanlar"]}
    assert {"Kamera Tipi", "Çözünürlük", "IR Mesafesi", "Bağlı NVR",
            "Kanal No", "IP Sınıfı"} <= alanlar
    tip = next(a for a in s["alanlar"] if a["ad"] == "Kamera Tipi")
    assert tip["tip"] == "secim" and "PTZ (hareketli)" in tip["secenekler"]

    lok = client.post("/locations", json={"name": "ŞANTİYE KAM"}).json()
    r = client.post("/ag/urunler", json={
        "tur": "kamera", "asset_tag": "KAM-01", "marka": "Hikvision",
        "model": "DS-2CD2143G2", "location_id": lok["id"],
        "ozellikler": {"Kamera Tipi": "Dome", "Çözünürlük": "4 MP",
                       "Bağlı NVR": "NVR-01", "Kanal No": "7"}})
    assert r.status_code == 201, r.text

    urun = client.get("/ag/urunler", params={"tur": "kamera"}).json()[0]
    assert urun["asset_tag"] == "KAM-01" and urun["marka"] == "Hikvision"
    assert urun["ozellikler"]["Bağlı NVR"] == "NVR-01"
    # Ağ ailesinin özetinde ve Varlıklar dışında görünür
    assert "kamera" in {d["tur"] for d in
                        client.get("/ag/ozet", params={"aile": "ag"}).json()["tur_dagilimi"]}
    assert "KAM-01" not in {a["asset_tag"] for a in
                            client.get("/assets", params={"sistem": "false"}).json()}
