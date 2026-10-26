"""Authenticated event transport: durable outbox, ACK after commit, replay detection."""

import asyncio
import httpx
from sqlalchemy import select
from app.core import *
from app.services import pos, commerce

MASTER_TABLES = [
    "companies",
    "uoms",
    "categories",
    "products",
    "product_uoms",
    "suppliers",
    "customers",
    "outlets",
    "kitchens",
    "warehouses",
    "users",
    "roles",
    "user_roles",
    "price_lists",
    "price_list_items",
    "promotion_rules",
    "vouchers",
    "loyalty_accounts",
    "payment_methods",
    "chart_of_accounts",
    "cash_bank_accounts",
    "taxes",
    "fiscal_periods",
    "approval_rules",
    "approval_steps",
    "consignment_agreements",
    "pos_terminals",
]
OPS = {
    "pos.open": pos.open_shift,
    "pos.sale": pos.sale,
    "pos.cash": pos.cash_entry,
    "pos.close": pos.close_shift,
    "pos.return": pos.pos_return,
}


def sync_policy(c):
    return {
        "interval_seconds": setting(c, "pos_sync_policy", {}).get(
            "interval_seconds", 15
        )
    }


def configure_policy(c, actor, p):
    allowed(c, actor, "users")
    need(isinstance(p, dict), "Pengaturan sinkronisasi harus berupa objek")
    interval = p.get("interval_seconds")
    need(
        type(interval) is int and 1 <= interval <= 86400,
        "Interval sinkronisasi harus bilangan bulat 1–86400 detik",
    )
    policy = {"interval_seconds": interval}
    set_setting(c, actor, "pos_sync_policy", policy)
    return policy


async def worker(db, settings_changed):
    """The POS schedules outbound sync using its durable terminal policy.

    Recalculate the next deadline after configuration changes, including when
    shortening a long wait. Each attempt finishes before another is scheduled.
    """
    loop = asyncio.get_running_loop()
    last_finished = loop.time()
    while True:
        settings_changed.clear()
        with db.read() as c:
            interval = sync_policy(c)["interval_seconds"]
        remaining = max(0, interval - (loop.time() - last_finished))
        try:
            await asyncio.wait_for(settings_changed.wait(), timeout=remaining)
            continue
        except TimeoutError:
            pass
        try:
            await asyncio.to_thread(run, db)
        except Exception:
            pass  # failed/pending events remain durable; subsequent cycles retry
        last_finished = loop.time()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def sign(token, payload):
    return hmac.new(
        token.encode(), digest(payload).encode(), hashlib.sha256
    ).hexdigest()


def register(c, actor, p):
    outlet = require(c, "outlets", p["outlet_id"])
    need(
        outlet["kind"] == "store" and outlet["pos_enabled"],
        "Terminal hanya untuk toko fisik",
    )
    warehouses = rows(c, "warehouses", outlet_id=outlet["id"], kind="store")
    need(warehouses, "Gudang toko belum tersedia")
    t = insert(
        c,
        "pos_terminals",
        dict(
            code=p["code"],
            outlet_id=outlet["id"],
            warehouse_id=warehouses[0]["id"],
            device_public_key=None,
            active=True,
        ),
    )
    secret = secrets.token_urlsafe(48)
    insert(
        c, "app_tokens", dict(id=token_hash(secret), terminal_id=t["id"], active=True)
    )
    audit(c, actor, "pos_terminals", t["id"], "register", after=t)
    return {
        "terminal": t,
        "token": secret,
        "message": "Salin token sekali ini untuk pemasangan POS. Token tidak ditampilkan kembali.",
    }


def auth_terminal(c, token):
    t = get(c, "app_tokens", token_hash(token))
    need(t and t["active"], "Token terminal tidak valid", 401)
    terminal = require(c, "pos_terminals", t["terminal_id"])
    need(terminal["active"], "Terminal nonaktif", 403)
    return terminal


def snapshot(c, terminal):
    data = {name: clean(rows(c, name)) for name in MASTER_TABLES}
    # Terminal never needs other terminals' credentials. User password/PIN hashes
    # are cached only over authenticated transport for local login/authorization.
    data["pos_terminals"] = [clean(terminal)]
    data["stock_balances"] = clean(
        rows(c, "stock_balances", warehouse_id=terminal["warehouse_id"])
    )
    for period_row in data["fiscal_periods"]:
        period_row["closing_document_id"] = None
    data["settings"] = clean(
        [
            r
            for r in rows(c, "settings")
            if r["key"] in ("offline_policy", "tax_policy", "loyalty_policy")
        ]
    )
    applied = rows(c, "sync_inbox", terminal_id=terminal["id"], status="applied")
    seq = max([r["local_sequence"] for r in applied], default=0)
    return {
        "terminal_id": terminal["id"],
        "watermark": seq,
        "generated_at": now().isoformat(),
        "tables": data,
    }


def enqueue(c, terminal, actor, command, parameters, result):
    p = clean(dict(parameters))
    p.pop("authorization", None)
    p["_authorization"] = result.get("authorization")
    if command == "pos.open":
        p["_opened_at"] = clean(result["opened_at"])
    if command == "pos.close":
        p["_closed_at"] = clean(result["closed_at"])
    if command == "pos.sale":
        p["_pricing"] = result["pricing"]
        sale = require(c, "pos_sales", result["id"])
        p["_sold_at"] = clean(sale["sold_at"])
        p["_sequence"] = sale["local_sequence"]
        saved = rows(c, "pos_sale_lines", pos_sale_id=result["id"])
        for a, ln in zip(p["lines"], saved):
            a["_line_id"] = ln["id"]
            a["_unit_price"] = str(ln["unit_price_input"])
    if command == "pos.return":
        p["_refund_id"] = result.get("refund_id")
    p["id"] = result["id"] if command != "pos.cash" else parameters["id"]
    original = document(c, p["id"])
    p["document_no"] = original["document_no"]
    p["business_date"] = str(original["business_date"])
    sequence = pos.next_sequence(c, terminal["id"])
    payload = {"actor_id": actor, "command": command, "parameters": p}
    payload_hash = digest(payload)
    out = insert(
        c,
        "sync_outbox",
        dict(
            terminal_id=terminal["id"],
            local_sequence=sequence,
            aggregate_document_id=(
                p["id"] if command not in ("pos.close",) else parameters["shift_id"]
            ),
            event_type=command,
            schema_version=1,
            occurred_at=now(),
            payload=payload,
            payload_hash=payload_hash,
            status="pending",
            attempt_count=0,
            acknowledged_at=None,
        ),
    )
    return out


def apply_event(c, terminal, e):
    need(e["terminal_id"] == terminal["id"], "Event milik terminal lain", 403)
    need(e["schema_version"] == 1, "Versi schema event tidak didukung", 409)
    need(e["payload_hash"] == digest(e["payload"]), "Hash payload tidak cocok", 409)
    need(
        e["event_type"] == e["payload"]["command"],
        "Jenis event tidak cocok dengan perintah",
        409,
    )
    existing = get(c, "sync_inbox", e["id"])
    if existing:
        need(
            existing["payload_hash"] == e["payload_hash"]
            and existing["terminal_id"] == terminal["id"]
            and existing["local_sequence"] == e["local_sequence"],
            "Identitas event sama dengan payload berbeda",
            409,
        )
        need(
            existing["status"] == "applied",
            "Transaksi perlu penyelesaian konflik di backoffice",
            409,
        )
        return existing["result"]
    prior = rows(
        c, "sync_inbox", terminal_id=terminal["id"], local_sequence=e["local_sequence"]
    )
    need(not prior, "Urutan terminal sudah digunakan event berbeda", 409)
    need(e["payload_hash"] == digest(e["payload"]), "Hash payload tidak cocok", 409)
    applied = rows(c, "sync_inbox", terminal_id=terminal["id"], status="applied")
    expected = max([r["local_sequence"] for r in applied], default=0) + 1
    need(
        e["local_sequence"] == expected,
        "Urutan event terputus; kirim kejadian sebelumnya dahulu",
        409,
    )
    payload = e["payload"]
    command = payload["command"]
    need(command in OPS, "Perintah sync tidak diizinkan")
    p = dict(payload["parameters"])
    p["_local_runtime"] = False
    actor = payload["actor_id"]
    allowed(c, actor, "pos")
    if command == "pos.open":
        need(p["terminal_id"] == terminal["id"], "Terminal shift tidak cocok")
    else:
        need(
            require(c, "pos_shifts", p["shift_id"])["terminal_id"] == terminal["id"],
            "Shift bukan milik terminal ini",
        )
    fn = OPS[command]
    result = (
        fn(c, actor, p, True)
        if command in ("pos.sale", "pos.return")
        else fn(c, actor, p)
    )
    result = clean(result)
    result["cloud_status"] = "applied"
    insert(
        c,
        "sync_inbox",
        dict(
            id=e["id"],
            terminal_id=terminal["id"],
            local_sequence=e["local_sequence"],
            aggregate_document_id=e["aggregate_document_id"],
            event_type=e["event_type"],
            schema_version=1,
            occurred_at=e["occurred_at"],
            received_at=now(),
            applied_at=now(),
            payload_hash=e["payload_hash"],
            payload=payload,
            status="applied",
            result=result,
        ),
    )
    cp = rows(c, "sync_checkpoints", terminal_id=terminal["id"], stream="cloud_ack")
    values = dict(
        cursor_value=str(e["local_sequence"]),
        last_ack_sequence=e["local_sequence"],
        last_success_at=now(),
    )
    if cp:
        update(c, "sync_checkpoints", cp[0]["id"], **values)
    else:
        insert(
            c,
            "sync_checkpoints",
            dict(terminal_id=terminal["id"], stream="cloud_ack", **values),
        )
    return result


def cloud_url(url):
    from urllib.parse import urlsplit
    import os

    u = urlsplit(url)
    need(
        u.hostname
        and not u.username
        and not u.password
        and not u.query
        and not u.fragment,
        "URL cloud tidak valid",
    )
    need(
        u.scheme == "https"
        or (
            u.scheme == "http"
            and (
                u.hostname in ("localhost", "127.0.0.1", "testserver")
                or os.getenv("ALLOW_INSECURE_CLOUD") == "1"
            )
        ),
        "Cloud harus HTTPS; HTTP hanya untuk pengujian lokal yang dikonfigurasi",
    )
    return url.rstrip("/")


def install_snapshot(c, actor, snap):
    # Master data upserts preserve references held by historical local transactions.
    for name in MASTER_TABLES + ["settings"]:
        for r in snap["tables"].get(name, []):
            if get(c, name, r["id"]):
                update(c, name, r["id"], **{k: v for k, v in r.items() if k != "id"})
            else:
                insert(c, name, r)
    terminal = require(c, "pos_terminals", snap["terminal_id"])
    watermark = snap["watermark"]
    pending = [
        e
        for e in rows(c, "sync_outbox", terminal_id=terminal["id"])
        if e["local_sequence"] > watermark
    ]
    # Rebuild the approximate balance from cloud plus local movements not in that snapshot.
    for r in snap["tables"]["stock_balances"]:
        extraq = ZERO
        extrav = ZERO
        ids = {e["aggregate_document_id"] for e in pending}
        for docid in ids:
            for m in rows(
                c,
                "stock_movements",
                source_document_id=docid,
                product_id=r["product_id"],
                warehouse_id=terminal["warehouse_id"],
            ):
                extraq += m["qty_delta"]
                extrav += m["value_delta"]
        existing = rows(
            c,
            "stock_balances",
            product_id=r["product_id"],
            warehouse_id=terminal["warehouse_id"],
        )
        values = {
            **r,
            "quantity": str(Decimal(r["quantity"]) + extraq),
            "inventory_value": str(Decimal(r["inventory_value"]) + extrav),
        }
        if existing:
            update(
                c,
                "stock_balances",
                existing[0]["id"],
                **{k: v for k, v in values.items() if k != "id"}
            )
        else:
            insert(c, "stock_balances", values)
    policy = setting(c, "offline_policy", {})
    set_setting(
        c,
        actor,
        "pos_cache",
        {
            "terminal_id": terminal["id"],
            "synced_at": now().isoformat(),
            "credential_expires_at": (
                now() + dt.timedelta(hours=policy.get("max_credential_hours", 72))
            ).isoformat(),
            "watermark": watermark,
        },
    )


def pair(db, p):
    url = cloud_url(p["cloud_url"])
    token = p["token"]
    with db.read() as c:
        need(
            not setting(c, "pos_connection"),
            "Terminal sudah terpasang; ubah koneksi melalui prosedur administrasi",
            409,
        )
    with httpx.Client(timeout=20, trust_env=False) as client:
        r = client.get(
            url + "/api/sync/snapshot", headers={"Authorization": "Terminal " + token}
        )
        r.raise_for_status()
        snap = r.json()
    with db.write() as c:
        actor = snap["tables"]["users"][0]["id"]
        install_snapshot(c, actor, snap)
        set_setting(
            c,
            actor,
            "pos_connection",
            {"cloud_url": url, "token": token, "terminal_id": snap["terminal_id"]},
        )
    return {"terminal_id": snap["terminal_id"], "status": "paired"}


def run(db):
    with db.read() as c:
        config = setting(c, "pos_connection")
        need(config, "POS belum dipasangkan")
    url = cloud_url(config["cloud_url"])
    token = config["token"]
    results = []
    with httpx.Client(timeout=20, trust_env=False) as client:
        with db.read() as c:
            events = sorted(
                [
                    clean(e)
                    for e in rows(c, "sync_outbox", terminal_id=config["terminal_id"])
                    if e["status"] != "applied"
                ],
                key=lambda e: e["local_sequence"],
            )
        for e in events:
            try:
                with db.write() as c:
                    update(
                        c,
                        "sync_outbox",
                        e["id"],
                        status="sending",
                        attempt_count=e["attempt_count"] + 1,
                    )
                r = client.post(
                    url + "/api/sync/events",
                    json={"event": e, "signature": sign(token, e)},
                    headers={"Authorization": "Terminal " + token},
                )
                if r.status_code >= 400:
                    with db.write() as c:
                        update(
                            c,
                            "sync_outbox",
                            e["id"],
                            status="conflict" if r.status_code == 409 else "retry",
                        )
                    return {
                        "status": "needs_review" if r.status_code == 409 else "retry",
                        "event_id": e["id"],
                        "detail": r.json().get("detail", "Sinkronisasi ditolak"),
                        "applied": len(results),
                    }
                result = r.json()
                with db.write() as c:
                    update(
                        c,
                        "sync_outbox",
                        e["id"],
                        status="applied",
                        acknowledged_at=now(),
                    )
                results.append(result)
            except httpx.HTTPError:
                with db.write() as c:
                    update(c, "sync_outbox", e["id"], status="retry")
                return {"status": "offline", "applied": len(results)}
        r = client.get(
            url + "/api/sync/snapshot", headers={"Authorization": "Terminal " + token}
        )
        r.raise_for_status()
        snap = r.json()
        with db.write() as c:
            actor = snap["tables"]["users"][0]["id"]
            install_snapshot(c, actor, snap)
    return {"status": "online", "applied": len(results), "watermark": snap["watermark"]}


def online_redemption(db, actor, p):
    result = run(db)
    need(
        result["status"] == "online",
        "Voucher / penukaran poin memerlukan koneksi cloud",
    )
    with db.read() as c:
        config = setting(c, "pos_connection")
        pricing = commerce.quote(c, p)
        payload = {
            "actor_id": actor,
            "sale_id": uid(),
            "customer_id": p.get("customer_id"),
            "voucher_code": p.get("voucher_code"),
            "points": p.get("points", 0),
            "eligible_amount": str(pricing["total"]),
        }
    with httpx.Client(timeout=20, trust_env=False) as client:
        r = client.post(
            config["cloud_url"] + "/api/sync/redemptions",
            json={"payload": payload, "signature": sign(config["token"], payload)},
            headers={"Authorization": "Terminal " + config["token"]},
        )
        r.raise_for_status()
        hold = r.json()
        r = client.get(
            config["cloud_url"] + "/api/sync/snapshot",
            headers={"Authorization": "Terminal " + config["token"]},
        )
        r.raise_for_status()
        snap = r.json()
    with db.write() as c:
        install_snapshot(c, actor, snap)
        insert(c, "app_redemptions", hold)
    return hold


def release_redemption(db, actor, id):
    with db.write() as c:
        r = require(c, "app_redemptions", id)
        need(
            r["actor_id"] == actor and r["status"] == "held",
            "Reservasi sudah dipakai atau bukan milik kasir ini",
            409,
        )
        config = setting(c, "pos_connection")
        update(c, "app_redemptions", id, status="releasing")
    payload = {"id": id, "actor_id": actor}
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            res = client.post(
                config["cloud_url"] + "/api/sync/redemptions/release",
                json={"payload": payload, "signature": sign(config["token"], payload)},
                headers={"Authorization": "Terminal " + config["token"]},
            )
            res.raise_for_status()
    except Exception:
        with db.write() as c:
            update(c, "app_redemptions", id, status="held")
        raise
    with db.write() as c:
        update(c, "app_redemptions", id, status="released")
    return {"id": id, "status": "released"}


def review_conflict(c, actor, p):
    cf = require(c, "sync_conflicts", p["conflict_id"])
    need(cf["status"] == "open", "Konflik sudah diselesaikan")
    if cf["resolution_document_id"]:
        return document(c, cf["resolution_document_id"])
    d = doc(c, actor, "SYNC_REVIEW")
    update(c, "sync_conflicts", cf["id"], resolution_document_id=d["id"])
    audit(
        c,
        actor,
        "sync_conflicts",
        cf["id"],
        "review_created",
        after=p,
        document=d["id"],
    )
    return d


def resolve_conflict(c, actor, p):
    from app.services.approval import approved

    cf = require(c, "sync_conflicts", p["conflict_id"])
    need(
        cf["status"] == "open" and cf["resolution_document_id"],
        "Buat dokumen tinjauan terlebih dahulu",
    )
    approved(c, actor, cf["resolution_document_id"], "sync_correction")
    need(p.get("reason"), "Alasan penyelesaian wajib")
    inbox = require(c, "sync_inbox", cf["inbox_event_id"])
    need(
        inbox["schema_version"] == 1
        and inbox["payload_hash"] == digest(inbox["payload"]),
        "Versi atau integritas event tidak dapat dipulihkan dengan koreksi tanggal",
    )
    terminal = require(c, "pos_terminals", inbox["terminal_id"])
    payload = inbox["payload"]
    args = dict(payload["parameters"])
    if p.get("posting_date"):
        args["business_date"] = p["posting_date"]
    args["_local_runtime"] = False
    need(payload["command"] in OPS, "Jenis perintah tidak didukung")
    applied = rows(c, "sync_inbox", terminal_id=terminal["id"], status="applied")
    expected = max([r["local_sequence"] for r in applied], default=0) + 1
    need(inbox["local_sequence"] == expected, "Selesaikan event sebelumnya dahulu")
    fn = OPS[payload["command"]]
    result = (
        fn(c, payload["actor_id"], args, True)
        if payload["command"] in ("pos.sale", "pos.return")
        else fn(c, payload["actor_id"], args)
    )
    result = clean(result)
    result["cloud_status"] = "applied"
    update(
        c,
        "sync_inbox",
        inbox["id"],
        status="applied",
        applied_at=now(),
        aggregate_document_id=(
            args["id"] if payload["command"] != "pos.close" else args["shift_id"]
        ),
        result=result,
    )
    update(
        c,
        "sync_conflicts",
        cf["id"],
        status="resolved",
        resolved_by=actor,
        resolved_at=now(),
    )
    post(c, actor, cf["resolution_document_id"])
    audit(
        c,
        actor,
        "sync_conflicts",
        cf["id"],
        "resolved",
        before={
            "original_business_date": inbox["payload"]["parameters"].get(
                "business_date"
            )
        },
        after=p,
        document=cf["resolution_document_id"],
    )
    return result
