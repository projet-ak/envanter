"""Cihaz teknik özelliklerini arayüzden ekleme/düzenleme/silme."""

import pytest


@pytest.fixture
def cihaz(client):
    return client.post("/assets", json={
        "asset_tag": "OZ-1", "name": "Dizüstü",
        "custom": {"İşlemci": {"İşlemci Markası": "Intel"}},
    }).json()


def _ozellikler(client, asset_id):
    return client.get(f"/detay/asset/{asset_id}").json()["ozellikler"]


def test_yeni_ozellik_eklenir(client, cihaz):
    r = client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "Bellek", "ad": "Ram Kapasitesi (mB)", "deger": "16 GB"})
    assert r.status_code == 200
    o = _ozellikler(client, cihaz["id"])
    assert o["Bellek"]["Ram Kapasitesi (mB)"] == "16 GB"
    assert o["İşlemci"]["İşlemci Markası"] == "Intel"   # mevcutlar korunmalı


def test_mevcut_ozellik_guncellenir(client, cihaz):
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "İşlemci", "ad": "İşlemci Markası", "deger": "AMD"})
    assert _ozellikler(client, cihaz["id"])["İşlemci"]["İşlemci Markası"] == "AMD"


def test_yeni_grup_acilir(client, cihaz):
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "Kendi Grubum", "ad": "Özel Alan", "deger": "değer"})
    assert _ozellikler(client, cihaz["id"])["Kendi Grubum"] == {"Özel Alan": "değer"}


def test_ozellik_silinir(client, cihaz):
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "İşlemci", "ad": "İşlemci Hızı (GHZ)", "deger": "2.5"})
    r = client.delete(f"/assets/{cihaz['id']}/ozellik",
                      params={"grup": "İşlemci", "ad": "İşlemci Hızı (GHZ)"})
    assert r.status_code == 200
    assert "İşlemci Hızı (GHZ)" not in _ozellikler(client, cihaz["id"])["İşlemci"]


def test_son_alan_silinince_grup_da_gider(client, cihaz):
    client.delete(f"/assets/{cihaz['id']}/ozellik",
                  params={"grup": "İşlemci", "ad": "İşlemci Markası"})
    assert _ozellikler(client, cihaz["id"]) == {}


def test_olmayan_ozellik_silinemez(client, cihaz):
    r = client.delete(f"/assets/{cihaz['id']}/ozellik",
                      params={"grup": "Yok", "ad": "Yok"})
    assert r.status_code == 404


def test_bos_deger_kaydedilir(client, cihaz):
    """Alanı bilerek boş bırakmak silmek demek değildir."""
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "İşlemci", "ad": "İşlemci Modeli", "deger": ""})
    assert _ozellikler(client, cihaz["id"])["İşlemci"]["İşlemci Modeli"] == ""


def test_degisiklik_gecmise_yazilir(client, cihaz):
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "İşlemci", "ad": "İşlemci Markası", "deger": "AMD"})
    gecmis = client.get(f"/detay/asset/{cihaz['id']}").json()["gecmis"]
    kayit = next(g for g in gecmis if g["not"] and "Özellik" in g["not"])
    assert kayit["degisiklikler"]["İşlemci Markası"] == {"eski": "Intel", "yeni": "AMD"}


def test_ozellik_kalici_olur(client, cihaz):
    """JSON sütunu yerinde değişiklikleri izlemez; kayıt gerçekten yazılmalı."""
    client.put(f"/assets/{cihaz['id']}/ozellik", json={
        "grup": "Depolama", "ad": "Harddisk Tipi", "deger": "SSD"})
    # Yeni bir istekle (yeni oturum) tekrar oku
    assert client.get(f"/assets/{cihaz['id']}").json()["custom"]["Depolama"] == {
        "Harddisk Tipi": "SSD"}


def test_ozellik_sablonu_gruplari_verir(client):
    sablon = client.get("/assets/ozellik-sablonu").json()
    gruplar = {s["grup"] for s in sablon}
    assert {"İşlemci", "Bellek", "Depolama", "Ekran"} <= gruplar
    islemci = next(s for s in sablon if s["grup"] == "İşlemci")
    assert "İşlemci Markası" in islemci["alanlar"]


def test_bos_grup_veya_ad_reddedilir(client, cihaz):
    r = client.put(f"/assets/{cihaz['id']}/ozellik",
                   json={"grup": "", "ad": "X", "deger": "1"})
    assert r.status_code == 422


def test_viewer_ozellik_yazamaz(viewer_client, client, cihaz):
    r = viewer_client.put(f"/assets/{cihaz['id']}/ozellik",
                          json={"grup": "İşlemci", "ad": "X", "deger": "1"})
    assert r.status_code == 403
    assert viewer_client.delete(
        f"/assets/{cihaz['id']}/ozellik",
        params={"grup": "İşlemci", "ad": "İşlemci Markası"}).status_code == 403


def test_olmayan_cihaz_404(client):
    assert client.put("/assets/999999/ozellik",
                      json={"grup": "A", "ad": "B", "deger": "c"}).status_code == 404
