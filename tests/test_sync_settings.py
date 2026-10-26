"""POS-owned sync scheduling: durable configuration, authorization and hot reload."""

import queue
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core import set_setting, setting
from app.db import rows
from app.services import sync, master
from tests.test_api_sync import local, login


def test_interval_is_persisted_per_terminal_and_survives_cloud_refresh(env, tmp_path):
    e = env
    app, client, headers = local(e, tmp_path)
    terminal2 = e.call(sync.register, dict(code="K02", outlet_id=e.outlet))
    _, second, _ = local(e, tmp_path, terminal2)
    assert client.get("/api/pos/sync-settings").json() == {"interval_seconds": 15}
    for interval in (15, 60, 600):
        r = client.put(
            "/api/pos/sync-settings",
            headers=headers,
            json={"interval_seconds": interval},
        )
        assert r.status_code == 200, r.text
        assert r.json()["interval_seconds"] == interval
    with e.db.write() as c:
        set_setting(c, e.actor, "pos_sync_policy", {"interval_seconds": 60})
        snap = sync.snapshot(c, e.terminal["terminal"])
    with app.state.db.write() as c:
        sync.install_snapshot(c, e.actor, snap)
        assert setting(c, "pos_sync_policy")["interval_seconds"] == 600
        history = rows(c, "settings", key="pos_sync_policy")
        assert len(history) == 3
        assert (
            len(
                [
                    a
                    for a in rows(c, "audit_logs", entity_name="settings")
                    if a["entity_id"] in {r["id"] for r in history}
                ]
            )
            == 3
        )
    restarted = TestClient(
        create_app(
            app.state.db.engine.url.render_as_string(hide_password=False),
            mode="pos",
            start_worker=False,
        )
    )
    login(restarted)
    assert restarted.get("/api/pos/sync-settings").json()["interval_seconds"] == 600
    assert second.get("/api/pos/sync-settings").json()["interval_seconds"] == 15


def test_interval_api_rejects_invalid_values_and_unauthorized_changes(env, tmp_path):
    e = env
    role = e.call(
        master.save, "roles", dict(code="CASH-SYNC", name="Kasir", permissions=["pos"])
    )
    e.call(
        master.user,
        dict(
            username="cashier",
            name="Kasir",
            password="correct-cashier-password",
            role_ids=[role["id"]],
        ),
    )
    app, client, headers = local(e, tmp_path)
    for value in (0, -1, 1.5, True, "15", 86401, None):
        assert (
            client.put(
                "/api/pos/sync-settings",
                headers=headers,
                json={"interval_seconds": value},
            ).status_code
            == 422
        )
    assert (
        client.put("/api/pos/sync-settings", json={"interval_seconds": 60}).status_code
        == 403
    )
    anonymous = TestClient(app)
    assert anonymous.get("/api/pos/sync-settings").status_code == 401
    cashier = TestClient(app)
    cashier_headers = login(cashier, "cashier", "correct-cashier-password")
    assert cashier.get("/api/pos/sync-settings").status_code == 200
    assert (
        cashier.put(
            "/api/pos/sync-settings",
            headers=cashier_headers,
            json={"interval_seconds": 60},
        ).status_code
        == 403
    )
    with app.state.db.read() as c:
        assert not rows(c, "settings", key="pos_sync_policy")
    cloud = TestClient(
        create_app(
            e.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    cloud_headers = login(cloud)
    assert (
        cloud.put(
            "/api/pos/sync-settings",
            headers=cloud_headers,
            json={"interval_seconds": 60},
        ).status_code
        == 403
    )


def test_live_interval_changes_reschedule_worker_and_manual_sync_remains_available(
    env, tmp_path, monkeypatch
):
    e = env
    local_app, _, _ = local(e, tmp_path)
    with local_app.state.db.write() as c:
        sync.configure_policy(c, e.actor, {"interval_seconds": 600})
    calls = queue.Queue()

    def offline_attempt(db):
        calls.put("attempt")
        raise httpx.ConnectError("cloud offline in test")

    monkeypatch.setattr(sync, "run", offline_attempt)
    app = create_app(
        local_app.state.db.engine.url.render_as_string(hide_password=False), mode="pos"
    )
    with TestClient(app) as client:
        headers = login(client)
        # Shorten a live 600-second wait through the actual application endpoint.
        r = client.put(
            "/api/pos/sync-settings", headers=headers, json={"interval_seconds": 1}
        )
        assert r.status_code == 200, r.text
        assert calls.get(timeout=5) == "attempt"
        assert (
            client.put(
                "/api/pos/sync-settings",
                headers=headers,
                json={"interval_seconds": 600},
            ).status_code
            == 200
        )
        with pytest.raises(queue.Empty):
            calls.get(timeout=1.2)
        # A long automatic interval never delays the cashier's manual request.
        result = client.post("/api/sync/run", headers=headers)
        assert result.status_code == 200 and result.json()["status"] == "offline"
        assert calls.get(timeout=1) == "attempt"
