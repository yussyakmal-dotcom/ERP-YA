from pathlib import Path
import copy
import datetime as dt
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import Database, rows, clean, get, update, insert, uid
from app.core import now, digest, setting, set_setting, BusinessError, document
from app.services import sync, inventory, pos, master


def login(client, username="admin", password="correct-admin-password"):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf"]}


def cmd(client, h, command, p, key=None):
    return client.post(
        "/api/commands/" + command,
        json=p,
        headers={**h, "Idempotency-Key": key or uid()},
    )


def local(e, tmp_path, terminal=None):
    terminal = terminal or e.terminal
    app = create_app(
        "sqlite:///" + str(tmp_path / (terminal["terminal"]["code"] + ".db")),
        mode="pos",
        start_worker=False,
    )
    with e.db.read() as c:
        snap = sync.snapshot(c, terminal["terminal"])
    with app.state.db.write() as c:
        sync.install_snapshot(c, e.actor, snap)
        set_setting(
            c,
            e.actor,
            "pos_connection",
            dict(
                cloud_url="http://testserver",
                token=terminal["token"],
                terminal_id=terminal["terminal"]["id"],
            ),
        )
    client = TestClient(app)
    h = login(client)
    return app, client, h


def push_all(e, app):
    with app.state.db.read() as c:
        events = sorted(rows(c, "sync_outbox"), key=lambda r: r["local_sequence"])
    result = []
    for event in events:
        with e.db.write() as c:
            result.append(sync.apply_event(c, e.terminal["terminal"], clean(event)))
    return events, result


def test_api_session_csrf_and_restricted_posted_tables(env):
    e = env
    app = create_app(
        e.db.engine.url.render_as_string(hide_password=False), start_worker=False
    )
    c = TestClient(app)
    assert c.get("/api/dashboard").status_code == 401
    h = login(c)
    assert c.get("/api/dashboard").status_code == 200
    assert c.post("/api/master/products", json={}).status_code == 403
    assert c.post("/api/master/stock_movements", headers=h, json={}).status_code == 403
    assert "password_hash" not in c.get("/api/tables/users").text
    assert c.get("/healthz").json()["mode"] == "backoffice"


def test_api_idempotency_same_body_and_conflicting_body(env, tmp_path):
    e = env
    app, c, h = local(e, tmp_path)
    p = {"opening_cash": "200000"}
    key = uid()
    a = cmd(c, h, "pos.open", p, key)
    assert a.status_code == 200, a.text
    assert cmd(c, h, "pos.open", p, key).json() == a.json()
    assert cmd(c, h, "pos.open", {"opening_cash": "300000"}, key).status_code == 409
    with app.state.db.read() as db:
        assert len(rows(db, "pos_shifts")) == 1
        assert len(rows(db, "sync_outbox")) == 1


def test_two_offline_cashiers_replay_and_no_double_ack(env, tmp_path):
    e = env
    e.stock(e.bread, e.wh["T01"], 3, 3000)
    with e.db.write() as c:
        t2 = sync.register(c, e.actor, dict(code="K02", outlet_id=e.outlet))
    terminals = []
    for terminal in [e.terminal, t2]:
        app, client, h = local(e, tmp_path, terminal)
        opened = cmd(client, h, "pos.open", {"opening_cash": 0})
        assert opened.status_code == 200, opened.text
        p = {
            "shift_id": opened.json()["id"],
            "price_list_id": e.price,
            "lines": [
                {
                    "product_id": e.bread,
                    "quantity": 2,
                    "stock_source": "owned",
                    "negative_reason": "Sinkron tertunda",
                }
            ],
            "tenders": [
                {
                    "method_id": e.cashmethod,
                    "cash_bank_account_id": e.cash,
                    "amount_applied": 16000,
                }
            ],
        }
        sale = cmd(client, h, "pos.sale", p)
        assert sale.status_code == 200, sale.text
        terminals.append((terminal, app, sale.json()))
    for terminal, app, sale in terminals:
        with app.state.db.read() as c:
            events = sorted(rows(c, "sync_outbox"), key=lambda x: x["local_sequence"])
        for event in events:
            with e.db.write() as c:
                result = sync.apply_event(c, terminal["terminal"], clean(event))
                again = sync.apply_event(c, terminal["terminal"], clean(event))
                assert result == again
    with e.db.read() as c:
        assert len(rows(c, "pos_sales")) == 2
        assert inventory.balance(c, e.bread, e.wh["T01"])["quantity"] == -1
        assert len(rows(c, "sync_inbox")) == 4


def test_same_event_id_changed_payload_rejected(env, tmp_path):
    e = env
    app, client, h = local(e, tmp_path)
    cmd(client, h, "pos.open", {"opening_cash": 0})
    events, _ = push_all(e, app)
    bad = clean(events[0])
    bad["payload"]["parameters"]["opening_cash"] = "99999"
    bad["payload_hash"] = digest(bad["payload"])
    with pytest.raises(BusinessError), e.db.write() as c:
        sync.apply_event(c, e.terminal["terminal"], bad)


def test_snapshot_watermark_overlays_only_unapplied_movement(env, tmp_path):
    e = env
    e.stock(e.bread, e.wh["T01"], 10, 3000)
    app, client, h = local(e, tmp_path)
    shift = cmd(client, h, "pos.open", {"opening_cash": 0}).json()
    p = {
        "shift_id": shift["id"],
        "price_list_id": e.price,
        "lines": [
            {
                "product_id": e.bread,
                "quantity": 2,
                "stock_source": "owned",
                "negative_reason": "Snapshot lokal",
            }
        ],
        "tenders": [
            {
                "method_id": e.cashmethod,
                "cash_bank_account_id": e.cash,
                "amount_applied": 16000,
            }
        ],
    }
    assert cmd(client, h, "pos.sale", p).status_code == 200
    # Snapshot before cloud has the sale: keep the local -2 overlay.
    with e.db.read() as c:
        snap = sync.snapshot(c, e.terminal["terminal"])
    with app.state.db.write() as c:
        sync.install_snapshot(c, e.actor, snap)
        assert inventory.balance(c, e.bread, e.wh["T01"])["quantity"] == 8
    push_all(e, app)
    with e.db.read() as c:
        snap = sync.snapshot(c, e.terminal["terminal"])
    with app.state.db.write() as c:
        sync.install_snapshot(c, e.actor, snap)
        assert inventory.balance(c, e.bread, e.wh["T01"])["quantity"] == 8


def test_restart_local_database_retains_pending_event(env, tmp_path):
    e = env
    app, client, h = local(e, tmp_path)
    cmd(client, h, "pos.open", {"opening_cash": 0})
    again = Database(str(app.state.db.engine.url))
    with again.read() as c:
        assert len(rows(c, "sync_outbox")) == 1
        assert rows(c, "sync_outbox")[0]["status"] == "pending"
        assert len(rows(c, "pos_shifts")) == 1


def test_pos_has_no_backoffice_commands_and_cloud_no_pos_commands(env, tmp_path):
    app, c, h = local(env, tmp_path)
    assert cmd(c, h, "so.create", {}).status_code == 403
    cloud = TestClient(
        create_app(
            env.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    hh = login(cloud)
    assert cmd(cloud, hh, "pos.open", {}).status_code == 403


def test_login_locks_after_five_failures(env):
    c = TestClient(
        create_app(
            env.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    for i in range(5):
        assert (
            c.post(
                "/api/login", json={"username": "admin", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        c.post(
            "/api/login",
            json={"username": "admin", "password": "correct-admin-password"},
        ).status_code
        == 429
    )


def test_permission_denied_even_with_cross_location_read(env):
    e = env
    with e.db.write() as c:
        role = insert(
            c,
            "roles",
            dict(code="VIEW", name="Pembaca", permissions=["reports"], active=True),
        )
        master.user(
            c,
            e.actor,
            dict(
                username="viewer",
                name="Pembaca",
                password="viewer-test-password",
                role_ids=[role["id"]],
            ),
        )
    client = TestClient(
        create_app(
            e.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    h = login(client, "viewer", "viewer-test-password")
    assert len(client.get("/api/tables/warehouses").json()["rows"]) == 29
    assert cmd(client, h, "po.create", {}).status_code == 403


def test_approval_credential_expired_offline(env, tmp_path):
    e = env
    app, client, h = local(e, tmp_path)
    with app.state.db.write() as c:
        cache = setting(c, "pos_cache")
        cache["credential_expires_at"] = (now() - dt.timedelta(seconds=1)).isoformat()
        set_setting(c, e.actor, "pos_cache", cache)
    assert cmd(client, h, "pos.open", {"opening_cash": 0}).status_code == 403


def test_sync_endpoint_signature_and_post_commit_ack(env, tmp_path):
    e = env
    app, client, h = local(e, tmp_path)
    cmd(client, h, "pos.open", {"opening_cash": 0})
    with app.state.db.read() as c:
        event = clean(rows(c, "sync_outbox")[0])
    cloud = TestClient(
        create_app(
            e.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    headers = {"Authorization": "Terminal " + e.terminal["token"]}
    assert (
        cloud.post(
            "/api/sync/events",
            headers=headers,
            json={"event": event, "signature": "bad"},
        ).status_code
        == 403
    )
    p = {"event": event, "signature": sync.sign(e.terminal["token"], event)}
    r = cloud.post("/api/sync/events", headers=headers, json=p)
    assert r.status_code == 200, r.text
    assert cloud.post("/api/sync/events", headers=headers, json=p).json() == r.json()
    with e.db.read() as c:
        assert len(rows(c, "pos_shifts")) == 1
        assert rows(c, "sync_inbox")[0]["status"] == "applied"
