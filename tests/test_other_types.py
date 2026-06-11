"""Aksesuar / sarf / bileşen / lisans CRUD testleri."""


def test_accessory_crud(client):
    r = client.post("/accessories", json={"name": "USB Mouse", "qty": 25, "min_qty": 5})
    assert r.status_code == 201
    acc = r.json()
    assert acc["qty"] == 25
    assert client.get(f"/accessories/{acc['id']}").json()["name"] == "USB Mouse"
    assert client.put(f"/accessories/{acc['id']}", json={"qty": 10}).json()["qty"] == 10


def test_consumable_and_component(client):
    assert client.post("/consumables", json={"name": "Toner", "qty": 12}).status_code == 201
    comp = client.post("/components", json={"name": "RAM", "serial": "R-9", "qty": 4})
    assert comp.status_code == 201
    assert comp.json()["serial"] == "R-9"


def test_license_crud(client):
    r = client.post("/licenses", json={"name": "Office 365", "seats": 100,
                                       "license_key": "ABC-123"})
    assert r.status_code == 201
    lic = r.json()
    assert lic["seats"] == 100 and lic["license_key"] == "ABC-123"


def test_other_types_need_editor(viewer_client):
    assert viewer_client.get("/accessories").status_code == 200
    assert viewer_client.post("/accessories", json={"name": "X"}).status_code == 403
