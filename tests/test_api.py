"""API uçları için uçtan uca testler."""


def _setup_basic(client):
    cat = client.post("/categories", json={"name": "Laptop"}).json()
    man = client.post("/manufacturers", json={"name": "Dell"}).json()
    loc = client.post("/locations", json={"name": "Depo"}).json()
    model = client.post(
        "/models",
        json={"name": "Latitude 5440", "category_id": cat["id"],
              "manufacturer_id": man["id"]},
    ).json()
    user = client.post(
        "/users", json={"first_name": "Ahmet", "last_name": "Yılmaz"}
    ).json()
    status = next(s for s in client.get("/status-labels").json()
                  if s["type"] == "deployable")
    return cat, man, loc, model, user, status


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_seed_default_statuses(client):
    statuses = client.get("/status-labels").json()
    assert len(statuses) == 4
    assert {s["type"] for s in statuses} == {
        "deployable", "pending", "archived", "undeployable"
    }


def test_asset_crud(client):
    *_, model, _user, status = _setup_basic(client)
    r = client.post("/assets", json={
        "asset_tag": "BT-0001", "name": "Laptop 1",
        "model_id": model["id"], "status_id": status["id"],
        "custom": {"CPU": "i7", "RAM": "16GB"},
    })
    assert r.status_code == 201
    asset = r.json()
    assert asset["custom"] == {"CPU": "i7", "RAM": "16GB"}

    # güncelle
    r = client.put(f"/assets/{asset['id']}", json={"name": "Yeni ad"})
    assert r.json()["name"] == "Yeni ad"

    # geçmiş: create + update
    actions = {h["action"] for h in client.get(f"/assets/{asset['id']}/history").json()}
    assert {"create", "update"} <= actions


def test_duplicate_tag_conflict(client):
    client.post("/assets", json={"asset_tag": "BT-DUP"})
    r = client.post("/assets", json={"asset_tag": "BT-DUP"})
    assert r.status_code == 409


def test_checkout_checkin_flow(client):
    *_, _model, user, _status = _setup_basic(client)
    asset = client.post("/assets", json={"asset_tag": "BT-CO"}).json()
    aid = asset["id"]

    r = client.post(f"/assets/{aid}/checkout",
                    json={"assigned_type": "user", "assigned_id": user["id"]})
    assert r.status_code == 200
    assert r.json()["assigned_user_id"] == user["id"]

    # zaten zimmetli -> 409
    assert client.post(f"/assets/{aid}/checkout",
                       json={"assigned_type": "user",
                             "assigned_id": user["id"]}).status_code == 409

    r = client.post(f"/assets/{aid}/checkin", json={})
    assert r.status_code == 200
    assert r.json()["assigned_type"] is None

    # zaten boşta -> 409
    assert client.post(f"/assets/{aid}/checkin", json={}).status_code == 409

    actions = [h["action"] for h in client.get(f"/assets/{aid}/history").json()]
    assert "checkout" in actions and "checkin" in actions


def test_checkout_invalid_target(client):
    asset = client.post("/assets", json={"asset_tag": "BT-X"}).json()
    r = client.post(f"/assets/{asset['id']}/checkout",
                    json={"assigned_type": "user", "assigned_id": 99999})
    assert r.status_code == 404


def test_assigned_filter(client):
    *_, _model, user, _status = _setup_basic(client)
    a1 = client.post("/assets", json={"asset_tag": "F-1"}).json()
    client.post("/assets", json={"asset_tag": "F-2"})
    client.post(f"/assets/{a1['id']}/checkout",
                json={"assigned_type": "user", "assigned_id": user["id"]})

    assert len(client.get("/assets", params={"assigned": "true"}).json()) == 1
    assert len(client.get("/assets", params={"assigned": "false"}).json()) == 1


def test_search_fallback_without_api_key(client):
    client.post("/assets", json={"asset_tag": "SEARCH-ME", "name": "bulunabilir"})
    r = client.post("/search", json={"q": "SEARCH-ME"})
    assert r.status_code == 200
    body = r.json()
    assert body["used_ai"] is False  # test ortamında API anahtarı yok
    assert body["count"] == 1
