"""Integration tests for the HTTP API, including tenant isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth, new_project


def test_create_and_list_flags(client: TestClient) -> None:
    key = new_project(client, "Acme")
    resp = client.post(
        "/admin/flags",
        headers=auth(key),
        json={"key": "dark-mode", "flag_type": "boolean", "enabled": True},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key"] == "dark-mode"
    assert body["flag_type"] == "boolean"

    listing = client.get("/admin/flags", headers=auth(key))
    assert listing.status_code == 200
    assert [f["key"] for f in listing.json()] == ["dark-mode"]


def test_duplicate_flag_key_conflicts(client: TestClient) -> None:
    key = new_project(client)
    payload = {"key": "dupe", "flag_type": "boolean"}
    assert client.post("/admin/flags", headers=auth(key), json=payload).status_code == 201
    conflict = client.post("/admin/flags", headers=auth(key), json=payload)
    assert conflict.status_code == 409


def test_missing_api_key_is_unauthorized(client: TestClient) -> None:
    resp = client.get("/admin/flags")
    assert resp.status_code == 401


def test_invalid_api_key_is_unauthorized(client: TestClient) -> None:
    resp = client.get("/admin/flags", headers=auth("ff_not-a-real-key"))
    assert resp.status_code == 401


def test_update_flag(client: TestClient) -> None:
    key = new_project(client)
    client.post(
        "/admin/flags",
        headers=auth(key),
        json={"key": "rollout", "flag_type": "percentage", "percentage": 10},
    )
    resp = client.patch("/admin/flags/rollout", headers=auth(key), json={"percentage": 55})
    assert resp.status_code == 200
    assert resp.json()["percentage"] == 55


def test_delete_flag(client: TestClient) -> None:
    key = new_project(client)
    client.post("/admin/flags", headers=auth(key), json={"key": "temp", "flag_type": "boolean"})
    assert client.delete("/admin/flags/temp", headers=auth(key)).status_code == 204
    assert client.get("/admin/flags/temp", headers=auth(key)).status_code == 404


def test_evaluate_boolean(client: TestClient) -> None:
    key = new_project(client)
    client.post("/admin/flags", headers=auth(key), json={"key": "dark", "flag_type": "boolean"})
    resp = client.post("/evaluate", headers=auth(key), json={"flag_key": "dark", "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["reason"] == "boolean_enabled"


def test_evaluate_unknown_flag_returns_false_with_reason(client: TestClient) -> None:
    key = new_project(client)
    resp = client.post("/evaluate", headers=auth(key), json={"flag_key": "ghost", "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["reason"] == "flag_not_found"


def test_evaluate_percentage_is_deterministic(client: TestClient) -> None:
    key = new_project(client)
    client.post(
        "/admin/flags",
        headers=auth(key),
        json={"key": "pct", "flag_type": "percentage", "percentage": 50},
    )
    first = client.post(
        "/evaluate", headers=auth(key), json={"flag_key": "pct", "user_id": "stable"}
    ).json()
    second = client.post(
        "/evaluate", headers=auth(key), json={"flag_key": "pct", "user_id": "stable"}
    ).json()
    assert first == second
    assert first["bucket"] is not None


def test_batch_evaluate_returns_all_flags(client: TestClient) -> None:
    key = new_project(client)
    client.post("/admin/flags", headers=auth(key), json={"key": "a", "flag_type": "boolean"})
    client.post(
        "/admin/flags",
        headers=auth(key),
        json={"key": "b", "flag_type": "allowlist", "allowlist": ["u1"]},
    )
    resp = client.post("/evaluate/batch", headers=auth(key), json={"user_id": "u1"})
    assert resp.status_code == 200
    flags = resp.json()["flags"]
    assert set(flags) == {"a", "b"}
    assert flags["a"]["enabled"] is True
    assert flags["b"]["enabled"] is True  # u1 is allowlisted


def test_tenant_isolation_cannot_read_other_project_flag(client: TestClient) -> None:
    key_a = new_project(client, "Acme")
    key_b = new_project(client, "Globex")
    client.post(
        "/admin/flags",
        headers=auth(key_a),
        json={"key": "secret", "flag_type": "boolean"},
    )
    # B cannot see A's flag by key.
    assert client.get("/admin/flags/secret", headers=auth(key_b)).status_code == 404
    # B's flag listing is empty.
    assert client.get("/admin/flags", headers=auth(key_b)).json() == []


def test_tenant_isolation_evaluation_scoped(client: TestClient) -> None:
    key_a = new_project(client, "Acme")
    key_b = new_project(client, "Globex")
    client.post(
        "/admin/flags",
        headers=auth(key_a),
        json={"key": "shared-key", "flag_type": "boolean", "enabled": True},
    )
    client.post(
        "/admin/flags",
        headers=auth(key_b),
        json={"key": "shared-key", "flag_type": "boolean", "enabled": False},
    )
    a_eval = client.post(
        "/evaluate", headers=auth(key_a), json={"flag_key": "shared-key", "user_id": "x"}
    ).json()
    b_eval = client.post(
        "/evaluate", headers=auth(key_b), json={"flag_key": "shared-key", "user_id": "x"}
    ).json()
    assert a_eval["enabled"] is True
    assert b_eval["enabled"] is False  # same key, independent rules


def test_tenant_cannot_modify_other_project_flag(client: TestClient) -> None:
    key_a = new_project(client, "Acme")
    key_b = new_project(client, "Globex")
    client.post("/admin/flags", headers=auth(key_a), json={"key": "f", "flag_type": "boolean"})
    assert (
        client.patch("/admin/flags/f", headers=auth(key_b), json={"enabled": False}).status_code
        == 404
    )
    assert client.delete("/admin/flags/f", headers=auth(key_b)).status_code == 404
