import datetime as dt
import hashlib
import hmac
import json
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.db import TABLES as T, clean, get, insert, now, rows, uid, update

WIB = ZoneInfo("Asia/Jakarta")
ZERO = Decimal(0)


class BusinessError(Exception):
    def __init__(self, message, status=422):
        self.message = message
        self.status = status


def need(condition, message, status=422):
    if not condition:
        raise BusinessError(message, status)


def dec(v, positive=False):
    try:
        a = Decimal(str(v))
    except (InvalidOperation, TypeError):
        raise BusinessError("Jumlah / nilai bukan angka valid")
    need(a.is_finite(), "Jumlah / nilai harus angka terbatas")
    need(a >= 0, "Jumlah / nilai tidak boleh negatif")
    if positive:
        need(a > 0, "Jumlah / nilai harus lebih dari nol")
    return a


def money(v):
    return Decimal(v).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def as_utc(v):
    if isinstance(v, str):
        v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    return (
        v.replace(tzinfo=dt.timezone.utc)
        if v.tzinfo is None
        else v.astimezone(dt.timezone.utc)
    )


def valid_at(r, at=None):
    at = as_utc(at or now())
    return as_utc(r["valid_from"]) <= at and (
        not r.get("valid_to") or at <= as_utc(r["valid_to"])
    )


def require(c, t, id):
    r = get(c, t, id)
    need(r is not None, f"{t}: data tidak ditemukan", 404)
    return dict(r)


def digest(v):
    return hashlib.sha256(
        json.dumps(
            clean(v), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def password(s, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        "pbkdf2_sha256$310000$"
        + salt
        + "$"
        + hashlib.pbkdf2_hmac("sha256", s.encode(), salt.encode(), 310000).hex()
    )


def verify(s, hash):
    if not hash:
        return False
    try:
        return hmac.compare_digest(password(s, hash.split("$")[2]), hash)
    except (IndexError, AttributeError):
        return False


def perms(c, actor):
    out = set()
    for ur in rows(c, "user_roles", user_id=actor):
        r = require(c, "roles", ur["role_id"])
        if r["active"]:
            out.update(r["permissions"])
    return out


def allowed(c, actor, permission):
    need(require(c, "users", actor)["active"], "Akun nonaktif", 403)
    ps = perms(c, actor)
    need(
        "*" in ps or permission in ps,
        "Hak tindakan tidak mencukupi: " + permission,
        403,
    )


def audit(c, actor, entity, id, action, before=None, after=None, document=None):
    def redact(value):
        if isinstance(value, dict):
            return {
                k: (
                    "[redacted]"
                    if k
                    in (
                        "token",
                        "password",
                        "password_hash",
                        "pin",
                        "pin_hash",
                        "setup_token",
                    )
                    else redact(v)
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    insert(
        c,
        "audit_logs",
        dict(
            actor_id=actor,
            document_id=document,
            entity_name=entity,
            entity_id=id,
            action=action,
            before_data=redact(clean(before)),
            after_data=redact(clean(after)),
            occurred_at=now(),
        ),
    )


def setting(c, key, default=None):
    rr = rows(c, "settings", key=key)
    return max(rr, key=lambda r: r["version"])["value"] if rr else default


def set_setting(c, actor, key, value):
    old = rows(c, "settings", key=key)
    version = max([r["version"] for r in old], default=0) + 1
    r = insert(
        c,
        "settings",
        dict(
            key=key,
            version=version,
            value=clean(value),
            effective_from=now(),
            changed_by=actor,
        ),
    )
    audit(c, actor, "settings", r["id"], "configure", after=r)
    return r


def doc(c, actor, kind, data=None):
    data = data or {}
    company = rows(c, "companies")[0]
    id = data.get("id") or uid()
    date = dt.date.fromisoformat(
        data.get("business_date", str(now().astimezone(WIB).date()))
    )
    return insert(
        c,
        "documents",
        dict(
            id=id,
            company_id=company["id"],
            document_type=kind,
            document_no=data.get("document_no")
            or f"{kind}-{date:%y%m%d}-{id[:8].upper()}",
            business_date=date,
            status="draft",
            revision=1,
            created_by=actor,
            posted_by=None,
            posted_at=None,
            reversal_of_id=None,
            idempotency_key=None,
        ),
    )


def document(c, id, status=None, kind=None):
    d = require(c, "documents", id)
    if status:
        need(
            d["status"] in status,
            f"Status dokumen {d['status']} tidak mengizinkan tindakan ini",
            409,
        )
    if kind:
        need(d["document_type"] == kind, "Jenis dokumen tidak cocok", 409)
    return d


def post(c, actor, id, status="posted"):
    d = require(c, "documents", id)
    update(c, "documents", id, status=status, posted_at=now(), posted_by=actor)
    audit(
        c,
        actor,
        "documents",
        id,
        status,
        before=d,
        after={"status": status},
        document=id,
    )


def period(c, date):
    rr = [
        p for p in rows(c, "fiscal_periods") if p["start_date"] <= date <= p["end_date"]
    ]
    need(len(rr) == 1, "Tanggal belum memiliki satu periode keuangan yang valid")
    need(
        rr[0]["status"] == "open",
        "Periode tertutup; perlu koreksi pada periode terbuka",
        409,
    )
    return rr[0]


def journal(c, document_id, event, entries, date=None):
    d = require(c, "documents", document_id)
    date = date or d["business_date"]
    p = period(c, date)
    need(
        not rows(
            c, "journal_entries", source_document_id=document_id, posting_event=event
        ),
        "Jurnal kejadian sudah diposting",
        409,
    )
    entries = [(a, money(dr), money(cr)) for a, dr, cr in entries if dr or cr]
    need(
        sum(x[1] for x in entries) == sum(x[2] for x in entries),
        "Jurnal tidak seimbang",
    )
    j = insert(
        c,
        "journal_entries",
        dict(
            source_document_id=document_id,
            posting_event=event,
            period_id=p["id"],
            entry_date=date,
            status="posted",
            reversal_of_id=None,
            posted_at=now(),
        ),
    )
    for code, dr, cr in entries:
        accounts = rows(c, "chart_of_accounts", code=code)
        need(accounts, "Pemetaan akun belum tersedia: " + code)
        insert(
            c,
            "journal_lines",
            dict(
                journal_id=j["id"],
                account_id=accounts[0]["id"],
                outlet_id=None,
                warehouse_id=None,
                debit=dr,
                credit=cr,
                description=event,
            ),
        )
    return j


def unit(c, pid, uom=None):
    p = require(c, "products", pid)
    need(p["active"], "Produk nonaktif")
    uom = uom or p["base_uom_id"]
    rr = rows(c, "product_uoms", product_id=pid, uom_id=uom)
    need(rr and rr[0]["active"], "Konversi satuan aktif belum tersedia")
    need(rr[0]["factor_to_base"] > 0, "Faktor konversi tidak valid")
    return p, rr[0]


def bootstrap(c, username, pw):
    need(not rows(c, "users"), "Setup awal sudah selesai", 409)
    need(len(pw) >= 12, "Sandi minimal 12 karakter")
    u = insert(
        c,
        "users",
        dict(
            username=username,
            name="Administrator",
            password_hash=password(pw),
            pin_hash=None,
            credential_version=1,
            active=True,
        ),
    )
    r = insert(
        c,
        "roles",
        dict(code="ADMIN", name="Administrator", permissions=["*"], active=True),
    )
    insert(c, "user_roles", dict(user_id=u["id"], role_id=r["id"]))
    company = insert(
        c,
        "companies",
        dict(
            code="YA", name="Yussy Akmal", timezone="Asia/Jakarta", currency_code="IDR"
        ),
    )
    us = {}
    for code, dimension, fraction in [
        ("pcs", "count", False),
        ("butir", "count", False),
        ("kg", "mass", True),
        ("gram", "mass", True),
        ("dus", "package", False),
        ("box", "package", False),
        ("liter", "volume", True),
    ]:
        us[code] = insert(
            c,
            "uoms",
            dict(code=code, name=code, dimension=dimension, allow_decimal=fraction),
        )
    for i in range(1, 7):
        o = insert(
            c,
            "outlets",
            dict(
                company_id=company["id"],
                code=f"T{i:02}",
                name=f"Toko {i:02}",
                kind="store",
                pos_enabled=True,
                active=True,
            ),
        )
        insert(
            c,
            "warehouses",
            dict(
                company_id=company["id"],
                code=f"T{i:02}",
                name=o["name"],
                kind="store",
                outlet_id=o["id"],
                kitchen_id=None,
                active=True,
            ),
        )
    insert(
        c,
        "outlets",
        dict(
            company_id=company["id"],
            code="DAHLIA",
            name="Dahlia",
            kind="virtual",
            pos_enabled=False,
            active=True,
        ),
    )
    for code, name, kind in [
        ("CDC", "Gudang pusat", "central"),
        ("PACK", "Packing", "packing"),
        ("TRANSIT", "Barang dalam perjalanan", "transit"),
    ]:
        insert(
            c,
            "warehouses",
            dict(
                company_id=company["id"],
                code=code,
                name=name,
                kind=kind,
                outlet_id=None,
                kitchen_id=None,
                active=True,
            ),
        )
    for i in range(1, 11):
        k = insert(
            c,
            "kitchens",
            dict(
                company_id=company["id"],
                code=f"D{i:02}",
                name=f"Dapur {i:02}",
                kind="production",
                active=True,
            ),
        )
        for suffix, kind in [("RAW", "kitchen_raw"), ("FIN", "kitchen_finished")]:
            insert(
                c,
                "warehouses",
                dict(
                    company_id=company["id"],
                    code=f"D{i:02}-{suffix}",
                    name=f"Dapur {i:02} {suffix}",
                    kind=kind,
                    outlet_id=None,
                    kitchen_id=k["id"],
                    active=True,
                ),
            )
    insert(
        c,
        "kitchens",
        dict(
            company_id=company["id"],
            code="PACK",
            name="Packing",
            kind="packing",
            active=True,
        ),
    )
    for code, name in [("PAGI", "Pagi"), ("SIANG", "Siang"), ("SORE", "Sore")]:
        insert(c, "production_schedules", dict(code=code, name=name, active=True))
    insert(
        c,
        "price_lists",
        dict(code="POS", name="Harga toko", is_default=True, active=True),
    )
    insert(
        c,
        "price_lists",
        dict(code="SO", name="Harga pesanan", is_default=False, active=True),
    )
    accountdefs = [
        ("1100", "Kas bank", "asset", "debit"),
        ("1200", "Persediaan", "asset", "debit"),
        ("1300", "Piutang pelanggan", "asset", "debit"),
        ("1400", "Pekerjaan dalam proses", "asset", "debit"),
        ("2100", "Utang supplier", "liability", "credit"),
        ("2120", "Penerimaan belum ditagih", "liability", "credit"),
        ("2130", "DP pelanggan", "liability", "credit"),
        ("2140", "Kredit pelanggan", "liability", "credit"),
        ("2150", "Klaim supplier", "asset", "debit"),
        ("3000", "Saldo pembuka", "equity", "credit"),
        ("4000", "Penjualan", "revenue", "credit"),
        ("5000", "Harga pokok penjualan", "expense", "debit"),
        ("5100", "Kerugian persediaan", "expense", "debit"),
        ("5200", "Beban operasional", "expense", "debit"),
    ]
    for code, name, typ, normal in accountdefs:
        insert(
            c,
            "chart_of_accounts",
            dict(
                code=code,
                name=name,
                account_type=typ,
                normal_balance=normal,
                parent_id=None,
                is_postable=True,
                active=True,
            ),
        )
    cash = rows(c, "chart_of_accounts", code="1100")[0]
    insert(
        c,
        "cash_bank_accounts",
        dict(
            code="KAS",
            name="Kas operasional",
            account_id=cash["id"],
            currency_code="IDR",
            active=True,
        ),
    )
    for code, name, is_cash in [
        ("CASH", "Tunai", True),
        ("TRANSFER", "Transfer", False),
        ("QRIS", "QRIS", False),
        ("CARD", "Kartu", False),
    ]:
        insert(
            c,
            "payment_methods",
            dict(code=code, name=name, is_cash=is_cash, active=True),
        )
    today = now().astimezone(WIB).date()
    start = today.replace(day=1)
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(
        days=1
    )
    insert(
        c,
        "fiscal_periods",
        dict(
            name=f"{start:%Y-%m}",
            start_date=start,
            end_date=end,
            status="open",
            closed_at=None,
            closed_by=None,
            closing_document_id=None,
        ),
    )
    set_setting(
        c,
        u["id"],
        "offline_policy",
        dict(max_credential_hours=72, max_pin_attempts=5, pin_lock_minutes=15),
    )
    audit(c, u["id"], "companies", company["id"], "bootstrap")
    return {"user_id": u["id"], "company_id": company["id"]}
