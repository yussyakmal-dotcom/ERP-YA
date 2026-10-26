import asyncio
import contextlib
import csv
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db import Database, MODEL
from app.core import *
from app.services import (
    approval,
    inventory,
    purchasing,
    sales,
    production,
    finance,
    pos,
    sync,
    master,
    commerce,
)

COMMANDS = {
    "po.create": ("purchasing", purchasing.create_po),
    "po.confirm": ("purchasing", lambda c, a, p: purchasing.confirm_po(c, a, p["id"])),
    "po.receive": ("purchasing", lambda c, a, p: purchasing.receive(c, a, p["id"], p)),
    "po.reject": (
        "purchasing",
        lambda c, a, p: purchasing.reject_arrival(c, a, p["id"], p),
    ),
    "purchase.invoice": ("finance", purchasing.invoice),
    "consignment.settle": ("purchasing", purchasing.settlement),
    "so.create": ("sales", sales.create_so),
    "so.confirm": ("sales", lambda c, a, p: sales.confirm_so(c, a, p["id"])),
    "so.propose_revision": (
        "sales",
        lambda c, a, p: sales.propose_revision(c, a, p["id"], p),
    ),
    "so.revise": ("sales", lambda c, a, p: sales.revise_so(c, a, p["id"], p)),
    "so.cancel": ("sales", lambda c, a, p: sales.cancel_so(c, a, p["id"], p)),
    "so.deliver": ("sales", lambda c, a, p: sales.delivery(c, a, p["id"], p)),
    "so.invoice": ("finance", lambda c, a, p: sales.invoice(c, a, p["id"], p)),
    "wo.plan": ("production", production.plan),
    "wo.start": ("production", lambda c, a, p: production.start(c, a, p["id"])),
    "wo.complete": (
        "production",
        lambda c, a, p: production.complete(c, a, p["id"], p),
    ),
    "store.request": ("production", production.store_request),
    "transfer.create": ("inventory", inventory.transfer_create),
    "transfer.dispatch": (
        "inventory",
        lambda c, a, p: inventory.dispatch(c, a, p["id"]),
    ),
    "transfer.receive": (
        "inventory",
        lambda c, a, p: inventory.receive_transfer(c, a, p["id"], p),
    ),
    "transit.resolve": (
        "inventory",
        lambda c, a, p: inventory.resolve(c, a, p["id"], p),
    ),
    "stock.adjust": ("inventory", inventory.adjust),
    "stock.post_adjustment": (
        "inventory",
        lambda c, a, p: inventory.post_adjust(c, a, p["id"]),
    ),
    "stock.reserve": ("inventory", inventory.reserve),
    "return.create": (
        "inventory",
        lambda c, a, p: __import__("app.services.returns", fromlist=["create"]).create(
            c, a, p
        ),
    ),
    "return.post": (
        "inventory",
        lambda c, a, p: __import__(
            "app.services.returns", fromlist=["post_return"]
        ).post_return(c, a, p["id"]),
    ),
    "payment.create": ("finance", finance.payment),
    "deposit.apply": ("finance", finance.apply_deposit),
    "credit.apply": ("finance", finance.apply_credit),
    "refund.create": ("finance", finance.refund),
    "expense.create": ("finance", finance.expense),
    "period.close": ("finance", lambda c, a, p: finance.close_period(c, a, p["id"], p)),
    "period.reopen": ("finance", lambda c, a, p: finance.reopen(c, a, p["id"], p)),
    "approval.request": (
        "approvals",
        lambda c, a, p: approval.request(c, a, p["id"], p["action_code"], p["reason"]),
    ),
    "approval.decide": (
        "approvals",
        lambda c, a, p: approval.decide(
            c, a, p["id"], p["decision"], p.get("reason", "")
        ),
    ),
    "schedule.version": ("master", master.schedule),
    "bom.version": ("master", master.bom),
    "approval.rule": ("users", master.rule),
    "user.save": ("users", lambda c, a, p: master.user(c, a, p, p.get("id"))),
    "terminal.register": ("users", sync.register),
    "settings.save": ("users", lambda c, a, p: set_setting(c, a, p["key"], p["value"])),
    "sync.review": ("finance", sync.review_conflict),
    "sync.resolve": ("finance", sync.resolve_conflict),
    **{k: ("pos", v) for k, v in sync.OPS.items()},
}


def create_app(database_url=None, mode=None, start_worker=True):
    mode = mode or os.getenv("APP_MODE", "backoffice")
    need(mode in ("backoffice", "pos"), "APP_MODE tidak valid")
    db = Database(database_url)

    @asynccontextmanager
    async def lifespan(app):
        task = None
        if mode == "pos" and start_worker:
            app.state.sync_settings_changed = asyncio.Event()
            task = asyncio.create_task(sync.worker(db, app.state.sync_settings_changed))
        try:
            yield
        finally:
            app.state.sync_settings_changed = None
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="ERP Yussy Akmal " + mode, version="0.1.0", lifespan=lifespan)
    app.state.db = db
    app.state.mode = mode
    app.state.sync_settings_changed = None
    root = Path(__file__).resolve().parent

    @app.middleware("http")
    async def headers(req, call_next):
        resp = await call_next(req)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Cache-Control"] = (
            "no-store" if req.url.path.startswith("/api") else "no-cache"
        )
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return resp

    @app.exception_handler(BusinessError)
    async def business_error(req, e):
        if e.message == "PIN supervisor tidak valid":
            p = await req.json()
            id = p.get("authorization", {}).get("user_id")
            if id:
                with db.write() as c:
                    if get(c, "users", id):
                        key = "pin:" + id
                        attempt = get(c, "app_security", key)
                        count = (attempt["failures"] if attempt else 0) + 1
                        policy = setting(c, "offline_policy", {})
                        values = {
                            "failures": count,
                            "blocked_until": (
                                now()
                                + dt.timedelta(
                                    minutes=policy.get("pin_lock_minutes", 15)
                                )
                                if count >= policy.get("max_pin_attempts", 5)
                                else None
                            ),
                        }
                        if attempt:
                            update(c, "app_security", key, **values)
                        else:
                            insert(c, "app_security", {"id": key, **values})
        return JSONResponse({"detail": e.message}, status_code=e.status)

    @app.exception_handler(IntegrityError)
    async def integrity_error(req, e):
        return JSONResponse(
            {
                "detail": "Data duplikat, masih direferensikan, atau referensi wajib belum lengkap. Muat ulang dokumen."
            },
            status_code=409,
        )

    @app.exception_handler(KeyError)
    async def missing_error(req, e):
        return JSONResponse(
            {"detail": "Field wajib belum diisi: " + str(e.args[0])}, status_code=422
        )

    @app.exception_handler(ValueError)
    async def invalid_error(req, e):
        return JSONResponse({"detail": str(e)}, status_code=422)

    def session(req, c, write=False):
        token = req.cookies.get("erp_session", "")
        s = get(c, "app_sessions", hashlib.sha256(token.encode()).hexdigest())
        need(
            s and s["expires_at"].replace(tzinfo=dt.timezone.utc) > now(),
            "Silakan masuk kembali",
            401,
        )
        need(require(c, "users", s["user_id"])["active"], "Akun dinonaktifkan", 403)
        if write:
            need(
                hmac.compare_digest(req.headers.get("X-CSRF-Token", ""), s["csrf"]),
                "Token keamanan sesi tidak valid",
                403,
            )
        if mode == "pos":
            cache = setting(c, "pos_cache", {})
            need(
                cache
                and dt.datetime.fromisoformat(cache["credential_expires_at"]) > now(),
                "Cache akun offline kedaluwarsa. Sinkronkan terminal untuk melanjutkan.",
                403,
            )
        return s["user_id"], s

    @app.get("/healthz")
    def health():
        with db.read() as c:
            c.execute(select(T["app_schema_versions"]))
        return {"status": "ok", "mode": mode, "version": "0.1.0"}

    @app.get("/api/bootstrap")
    def bootstrap_state():
        with db.read() as c:
            return {
                "mode": mode,
                "initialized": bool(rows(c, "users")),
                "paired": bool(setting(c, "pos_connection")),
            }

    @app.post("/api/bootstrap")
    async def setup(req: Request):
        need(mode == "backoffice", "POS harus dipasangkan ke backoffice", 403)
        p = await req.json()
        expected = os.getenv("SETUP_TOKEN")
        if expected:
            need(
                hmac.compare_digest(str(p.get("setup_token", "")), expected),
                "Token setup salah",
                403,
            )
        else:
            need(
                req.client.host in ("127.0.0.1", "::1", "testclient"),
                "Setup remote memerlukan SETUP_TOKEN",
                403,
            )
        with db.write() as c:
            return clean(bootstrap(c, p["username"], p["password"]))

    @app.post("/api/pos/pair")
    async def pair(req: Request):
        need(mode == "pos", "Hanya tersedia pada POS", 403)
        try:
            return await asyncio.to_thread(sync.pair, db, await req.json())
        except __import__("httpx").HTTPError:
            raise BusinessError(
                "Backoffice tidak dapat dihubungi atau token ditolak", 502
            )

    @app.post("/api/login")
    async def login(req: Request):
        p = await req.json()
        failure = False
        result = None
        rawtoken = None
        with db.write() as c:
            user = rows(c, "users", username=p.get("username", ""))
            key = "login:" + str(p.get("username", ""))[:100]
            attempt = get(c, "app_security", key)
            if attempt and attempt["blocked_until"]:
                need(
                    attempt["blocked_until"].replace(tzinfo=dt.timezone.utc) <= now(),
                    "Login sementara terkunci; coba lagi setelah 15 menit",
                    429,
                )
            if (
                not user
                or not user[0]["active"]
                or not verify(p.get("password", ""), user[0]["password_hash"])
            ):
                failures = (attempt["failures"] if attempt else 0) + 1
                values = {
                    "failures": failures,
                    "blocked_until": (
                        now() + dt.timedelta(minutes=15) if failures >= 5 else None
                    ),
                }
                if attempt:
                    update(c, "app_security", key, **values)
                else:
                    insert(c, "app_security", {"id": key, **values})
                failure = True
            else:
                if attempt:
                    update(c, "app_security", key, failures=0, blocked_until=None)
                u = user[0]
                rawtoken = secrets.token_urlsafe(40)
                csrf = secrets.token_urlsafe(24)
                insert(
                    c,
                    "app_sessions",
                    dict(
                        id=hashlib.sha256(rawtoken.encode()).hexdigest(),
                        user_id=u["id"],
                        csrf=csrf,
                        expires_at=now() + dt.timedelta(hours=12),
                    ),
                )
                result = {
                    "id": u["id"],
                    "name": u["name"],
                    "csrf": csrf,
                    "permissions": sorted(perms(c, u["id"])),
                }
        if failure:
            raise BusinessError("Nama pengguna atau sandi salah", 401)
        response = JSONResponse(result)
        response.set_cookie(
            "erp_session",
            rawtoken,
            httponly=True,
            samesite="strict",
            secure=os.getenv("COOKIE_SECURE") == "1",
            max_age=43200,
        )
        return response

    @app.post("/api/logout")
    def logout(req: Request):
        with db.write() as c:
            a, s = session(req, c, True)
            c.execute(
                T["app_sessions"].delete().where(T["app_sessions"].c.id == s["id"])
            )
        r = JSONResponse({"status": "logged_out"})
        r.delete_cookie("erp_session")
        return r

    @app.get("/api/me")
    def me(req: Request):
        with db.read() as c:
            actor, s = session(req, c)
            u = require(c, "users", actor)
            return {
                "id": actor,
                "name": u["name"],
                "csrf": s["csrf"],
                "permissions": sorted(perms(c, actor)),
                "mode": mode,
                "cache": setting(c, "pos_cache") if mode == "pos" else None,
            }

    def safe_table(c, actor, name):
        need(name in MODEL, "Tabel tidak ditemukan", 404)
        if mode == "pos":
            need(
                name
                in set(
                    sync.MASTER_TABLES
                    + [
                        "documents",
                        "pos_shifts",
                        "pos_sales",
                        "pos_sale_lines",
                        "pos_tenders",
                        "stock_balances",
                        "sync_outbox",
                        "returns",
                        "return_lines",
                        "refunds",
                        "approval_requests",
                        "approval_actions",
                        "pos_cash_entries",
                    ]
                ),
                "Modul ini ada di backoffice",
                403,
            )
        if name in ("users", "roles", "user_roles", "approval_rules", "approval_steps"):
            allowed(c, actor, "users") if mode == "backoffice" else None
        if name in (
            "journal_entries",
            "journal_lines",
            "chart_of_accounts",
            "account_period_balances",
            "payments",
            "expenses",
        ):
            allowed(c, actor, "finance")

    @app.get("/api/model")
    def model(req: Request):
        with db.read() as c:
            actor, _ = session(req, c)
            return {"tables": MODEL, "editable": sorted(master.EDITABLE), "mode": mode}

    @app.get("/api/tables/{name}")
    def listing(
        name: str, req: Request, limit: int = 100, offset: int = 0, q: str = ""
    ):
        with db.read() as c:
            actor, _ = session(req, c)
            safe_table(c, actor, name)
            table = T[name]
            query = select(table)
            count = select(func.count()).select_from(table)
            filters = []
            for k, v in req.query_params.multi_items():
                if k in table.c and k not in ("limit", "offset", "q"):
                    filters.append(table.c[k] == v)
            if q:
                from sqlalchemy import or_, String

                tests = [
                    col.ilike("%" + q + "%")
                    for col in table.c
                    if isinstance(col.type, String)
                ]
                if tests:
                    filters.append(or_(*tests))
            if filters:
                query = query.where(*filters)
                count = count.where(*filters)
            result = [
                dict(r)
                for r in c.execute(
                    query.order_by(table.c.created_at.desc())
                    .limit(min(max(limit, 1), 500))
                    .offset(max(0, offset))
                ).mappings()
            ]
            for r in result:
                for key in ("password_hash", "pin_hash"):
                    r.pop(key, None)
                if "*" not in perms(c, actor) and "costs" not in perms(c, actor):
                    for key in list(r):
                        if "cost" in key or "inventory_value" in key:
                            r.pop(key, None)
            return clean({"rows": result, "total": c.scalar(count), "offset": offset})

    @app.post("/api/master/{name}")
    async def create_master(name: str, req: Request):
        need(mode == "backoffice", "Master diatur di backoffice", 403)
        p = await req.json()
        with db.write() as c:
            actor, _ = session(req, c, True)
            return clean(master.save(c, actor, name, p))

    @app.patch("/api/master/{name}/{id}")
    async def update_master(name: str, id: str, req: Request):
        need(mode == "backoffice", "Master diatur di backoffice", 403)
        p = await req.json()
        with db.write() as c:
            actor, _ = session(req, c, True)
            return clean(master.save(c, actor, name, p, id))

    @app.delete("/api/master/{name}/{id}")
    def remove_master(name: str, id: str, req: Request):
        need(mode == "backoffice", "Master diatur di backoffice", 403)
        with db.write() as c:
            actor, _ = session(req, c, True)
            return clean(master.remove(c, actor, name, id))

    @app.post("/api/commands/{command}")
    async def command(command: str, req: Request):
        need(command in COMMANDS, "Perintah tidak ditemukan", 404)
        p = await req.json()
        key = req.headers.get("Idempotency-Key", "")
        need(8 <= len(key) <= 100, "Idempotency-Key wajib 8-100 karakter")
        need(
            (
                command.startswith("pos.")
                if mode == "pos"
                else not command.startswith("pos.")
            ),
            "Modul tersedia pada aplikasi yang berbeda",
            403,
        )
        need(
            not any(k.startswith("_") for k in p),
            "Field internal tidak boleh dikirim oleh klien",
            403,
        )
        with db.write() as c:
            actor, _ = session(req, c, True)
            permission, fn = COMMANDS[command]
            allowed(c, actor, permission)
            intent = {**p}
            if "authorization" in intent:
                intent["authorization"] = {
                    k: v for k, v in intent["authorization"].items() if k != "pin"
                }
            fingerprint = digest(
                {"actor": actor, "command": command, "parameters": intent}
            )
            receipt_id = actor + ":" + key
            old = get(c, "app_commands", receipt_id)
            if old:
                need(
                    old["fingerprint"] == fingerprint,
                    "Kunci transaksi dipakai dengan isi berbeda",
                    409,
                )
                return old["result"]
            p.setdefault("id", uid())
            if mode == "pos":
                connection = setting(c, "pos_connection")
                need(connection, "Terminal belum dipasangkan")
                terminal = require(c, "pos_terminals", connection["terminal_id"])
                p["_local_runtime"] = True
                if command == "pos.sale":
                    p["business_date"] = str(now().astimezone(WIB).date())
                    if p.get("redemption_id"):
                        hold = require(c, "app_redemptions", p["redemption_id"])
                        need(
                            hold["status"] == "held"
                            and hold["actor_id"] == actor
                            and hold["terminal_id"] == terminal["id"],
                            "Reservasi tidak tersedia",
                        )
                        p["_redemption"] = clean(hold)
                        p["id"] = hold["sale_id"]
                if command == "pos.open":
                    p["terminal_id"] = terminal["id"]
                else:
                    need(
                        require(c, "pos_shifts", p["shift_id"])["terminal_id"]
                        == terminal["id"],
                        "Shift terminal tidak cocok",
                    )
            result = clean(fn(c, actor, p))
            if mode == "pos":
                sync.enqueue(c, terminal, actor, command, p, result)
            insert(
                c,
                "app_commands",
                dict(
                    id=receipt_id,
                    fingerprint=fingerprint,
                    result=result,
                    created_at=now(),
                ),
            )
            return result

    @app.get("/api/dashboard")
    def dashboard(req: Request):
        with db.read() as c:
            actor, _ = session(req, c)
            return clean(
                {
                    "documents": len(rows(c, "documents")),
                    "open_orders": len(
                        [
                            d
                            for d in rows(c, "documents", document_type="SO")
                            if d["status"] in ("confirmed", "partial")
                        ]
                    ),
                    "approvals": len(rows(c, "approval_requests", status="pending")),
                    "transit_cases": len(
                        rows(c, "transfer_discrepancies", status="open")
                    ),
                    "negative_stock": len(
                        rows(c, "negative_stock_cases", status="open")
                    ),
                    "outbox_pending": len(
                        [e for e in rows(c, "sync_outbox") if e["status"] != "applied"]
                    ),
                    "generated_at": now(),
                }
            )

    @app.get("/api/replenishment")
    def replenishment(req: Request):
        with db.write() as c:
            actor, _ = session(req, c)
            allowed(c, actor, "production")
            return clean(production.replenish(c))

    @app.get("/api/periods/{id}/checks")
    def checks(id: str, req: Request):
        with db.read() as c:
            actor, _ = session(req, c)
            allowed(c, actor, "finance")
            return clean(finance.close_checks(c, id))

    @app.get("/api/reports/trial-balance")
    def trial(req: Request, start: str, end: str):
        with db.read() as c:
            actor, _ = session(req, c)
            allowed(c, actor, "finance")
            sd = dt.date.fromisoformat(start)
            ed = dt.date.fromisoformat(end)
            need(sd <= ed, "Rentang tanggal salah")
            result = []
            for a in rows(c, "chart_of_accounts"):
                opening = ZERO
                debit = ZERO
                credit = ZERO
                for ln in rows(c, "journal_lines", account_id=a["id"]):
                    j = require(c, "journal_entries", ln["journal_id"])
                    if j["status"] != "posted":
                        continue
                    if j["entry_date"] < sd:
                        opening += ln["debit"] - ln["credit"]
                    elif j["entry_date"] <= ed:
                        debit += ln["debit"]
                        credit += ln["credit"]
                result.append(
                    {
                        "code": a["code"],
                        "name": a["name"],
                        "type": a["account_type"],
                        "opening": opening,
                        "debit": debit,
                        "credit": credit,
                        "closing": opening + debit - credit,
                    }
                )
            return clean(result)

    @app.get("/api/pos/sync-settings")
    def sync_settings(req: Request):
        need(mode == "pos", "Pengaturan ini tersedia pada POS lokal", 403)
        with db.read() as c:
            session(req, c)
            return sync.sync_policy(c)

    @app.put("/api/pos/sync-settings")
    async def save_sync_settings(req: Request):
        need(mode == "pos", "Pengaturan ini tersedia pada POS lokal", 403)
        p = await req.json()
        with db.write() as c:
            actor, _ = session(req, c, True)
            policy = sync.configure_policy(c, actor, p)
        if app.state.sync_settings_changed is not None:
            app.state.sync_settings_changed.set()
        return policy

    @app.post("/api/sync/run")
    def run_sync(req: Request):
        need(mode == "pos", "Gunakan monitor sinkronisasi pada backoffice", 403)
        with db.read() as c:
            session(req, c, True)
        try:
            return sync.run(db)
        except __import__("httpx").HTTPError:
            return {
                "status": "offline",
                "detail": "Cloud belum dapat dihubungi; transaksi tetap tersimpan lokal",
            }

    @app.post("/api/pos/quote")
    async def quote(req: Request):
        need(mode == "pos", "Quote kasir hanya tersedia pada POS", 403)
        p = await req.json()
        with db.read() as c:
            actor, _ = session(req, c, True)
            allowed(c, actor, "pos")
            if p.get("redemption_id"):
                hold = require(c, "app_redemptions", p["redemption_id"])
                need(
                    hold["actor_id"] == actor and hold["status"] == "held",
                    "Reservasi tidak tersedia",
                )
                p["_redemption"] = clean(hold)
            return clean(commerce.quote(c, p))

    @app.post("/api/pos/redemptions")
    async def redemption(req: Request):
        need(mode == "pos", "Hanya pada POS", 403)
        p = await req.json()
        with db.read() as c:
            actor, _ = session(req, c, True)
            allowed(c, actor, "pos")
        try:
            return clean(await asyncio.to_thread(sync.online_redemption, db, actor, p))
        except __import__("httpx").HTTPStatusError as err:
            raise BusinessError(
                err.response.json().get("detail", "Penukaran ditolak cloud"),
                err.response.status_code,
            )
        except __import__("httpx").HTTPError:
            raise BusinessError("Cloud tidak dapat dihubungi; penukaran ditunda", 502)

    @app.post("/api/sync/redemptions")
    async def reserve_redemption(req: Request):
        need(mode == "backoffice", "Hanya pada cloud", 403)
        p = await req.json()
        payload = p["payload"]
        token = req.headers.get("Authorization", "").removeprefix("Terminal ")
        with db.write() as c:
            terminal = sync.auth_terminal(c, token)
            need(
                hmac.compare_digest(p["signature"], sync.sign(token, payload)),
                "Tanda tangan salah",
                403,
            )
            return clean(
                commerce.reserve_redemption(c, terminal, payload["actor_id"], payload)
            )

    @app.get("/api/pos/redemptions")
    def held(req: Request):
        need(mode == "pos", "Hanya pada POS", 403)
        with db.read() as c:
            actor, _ = session(req, c)
            return clean(rows(c, "app_redemptions", actor_id=actor, status="held"))

    @app.post("/api/pos/redemptions/{id}/release")
    def release(id: str, req: Request):
        need(mode == "pos", "Hanya pada POS", 403)
        with db.read() as c:
            actor, _ = session(req, c, True)
        try:
            return sync.release_redemption(db, actor, id)
        except __import__("httpx").HTTPError:
            raise BusinessError(
                "Cloud belum dapat dihubungi; reservasi tetap ditahan", 502
            )

    @app.post("/api/sync/redemptions/release")
    async def release_cloud(req: Request):
        need(mode == "backoffice", "Hanya pada cloud", 403)
        p = await req.json()
        payload = p["payload"]
        token = req.headers.get("Authorization", "").removeprefix("Terminal ")
        with db.write() as c:
            terminal = sync.auth_terminal(c, token)
            need(
                hmac.compare_digest(p["signature"], sync.sign(token, payload)),
                "Tanda tangan salah",
                403,
            )
            allowed(c, payload["actor_id"], "pos")
            return clean(commerce.cancel_hold(c, terminal, payload["id"]))

    @app.get("/api/sync/snapshot")
    def snapshot(req: Request):
        need(mode == "backoffice", "Bukan endpoint cloud", 403)
        token = req.headers.get("Authorization", "").removeprefix("Terminal ")
        with db.read() as c:
            return sync.snapshot(c, sync.auth_terminal(c, token))

    @app.post("/api/sync/events")
    async def event(req: Request):
        need(mode == "backoffice", "Bukan endpoint cloud", 403)
        p = await req.json()
        e = p["event"]
        token = req.headers.get("Authorization", "").removeprefix("Terminal ")
        with db.read() as c:
            terminal = sync.auth_terminal(c, token)
        need(
            hmac.compare_digest(p["signature"], sync.sign(token, e)),
            "Tanda tangan event salah",
            403,
        )
        try:
            with db.write() as c:
                return sync.apply_event(c, terminal, e)
        except BusinessError as err:
            with db.write() as c:
                existing = get(c, "sync_inbox", e["id"])
                if (
                    not existing
                    and e["terminal_id"] == terminal["id"]
                    and not rows(
                        c,
                        "sync_inbox",
                        terminal_id=terminal["id"],
                        local_sequence=e["local_sequence"],
                    )
                ):
                    insert(
                        c,
                        "sync_inbox",
                        dict(
                            id=e["id"],
                            terminal_id=terminal["id"],
                            local_sequence=e["local_sequence"],
                            aggregate_document_id=None,
                            event_type=e["event_type"],
                            schema_version=e["schema_version"],
                            occurred_at=e["occurred_at"],
                            received_at=now(),
                            applied_at=None,
                            payload_hash=e["payload_hash"],
                            payload=e["payload"],
                            status="conflict",
                            result={"detail": err.message},
                        ),
                    )
                    insert(
                        c,
                        "sync_conflicts",
                        dict(
                            inbox_event_id=e["id"],
                            conflict_type="business_rule",
                            details={"detail": err.message},
                            status="open",
                            resolved_by=None,
                            resolution_document_id=None,
                            resolved_at=None,
                        ),
                    )
            raise

    app.mount("/static", StaticFiles(directory=root / "static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(root / "static/index.html")

    return app


app = create_app()
