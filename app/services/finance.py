from app.core import *
from app.services.approval import approved


def paid(c, target):
    return sum(
        (
            r["amount"]
            for r in rows(c, "payment_allocations", target_document_id=target)
            if not r["reversal_of_id"]
        ),
        ZERO,
    )


def credits_applied(c, target):
    return sum(
        (
            r["amount"]
            for r in rows(c, "credit_applications", invoice_document_id=target)
            if not r["reversal_of_id"]
        ),
        ZERO,
    )


def invoice_due(c, id):
    d = document(c, id)
    kind = d["document_type"]
    need(
        kind in ("PURCHASE_INVOICE", "SALES_INVOICE", "CONSIGNMENT_SETTLEMENT"),
        "Dokumen bukan faktur / settlement",
    )
    t = {
        "PURCHASE_INVOICE": "purchase_invoices",
        "SALES_INVOICE": "sales_invoices",
        "CONSIGNMENT_SETTLEMENT": "consignment_settlements",
    }[kind]
    r = require(c, t, id)
    dep = (
        sum(
            (
                a["amount"]
                for a in rows(c, "deposit_applications", invoice_id=id)
                if not a["reversal_of_id"]
            ),
            ZERO,
        )
        if kind == "SALES_INVOICE"
        else ZERO
    )
    return r["total"] - paid(c, id) - credits_applied(c, id) - dep


def deposit_available(c, id):
    d = require(c, "customer_deposits", id)
    return (
        d["amount"]
        - sum(
            (
                a["amount"]
                for a in rows(c, "deposit_applications", deposit_id=id)
                if not a["reversal_of_id"]
            ),
            ZERO,
        )
        - sum((a["amount"] for a in rows(c, "refund_allocations", deposit_id=id)), ZERO)
    )


def credit_available(c, id):
    d = require(c, "credit_notes", id)
    return (
        d["amount"]
        - sum(
            (
                a["amount"]
                for a in rows(c, "credit_applications", credit_note_id=id)
                if not a["reversal_of_id"]
            ),
            ZERO,
        )
        - sum(
            (a["amount"] for a in rows(c, "refund_allocations", credit_note_id=id)),
            ZERO,
        )
    )


def cash_account(c, id):
    a = require(c, "cash_bank_accounts", id)
    need(a["active"], "Rekening nonaktif")
    return require(c, "chart_of_accounts", a["account_id"])["code"]


def payment(c, actor, p):
    amount = money(dec(p["amount"], True))
    purpose = p["purpose"]
    need(
        purpose in ("deposit", "customer_payment", "supplier_payment"),
        "Jenis pembayaran tidak valid",
    )
    d = doc(c, actor, "PAYMENT", p)
    customer = p.get("customer_id")
    supplier = p.get("supplier_id")
    cash = cash_account(c, p["cash_bank_account_id"])
    method = require(c, "payment_methods", p["method_id"])
    if not method["is_cash"]:
        need(p.get("reference"), "Referensi pembayaran non-tunai wajib")
    insert(
        c,
        "payments",
        dict(
            id=d["id"],
            direction="out" if purpose == "supplier_payment" else "in",
            customer_id=customer,
            supplier_id=supplier,
            method_id=method["id"],
            cash_bank_account_id=p["cash_bank_account_id"],
            payment_date=d["business_date"],
            amount=amount,
            purpose=purpose,
            reference=p.get("reference"),
        ),
    )
    if purpose == "deposit":
        so = require(c, "sales_orders", p["sales_order_id"])
        document(c, so["id"], ["draft", "confirmed", "partial", "delivered"], "SO")
        need(customer == so["customer_id"], "Pelanggan DP tidak cocok dengan SO")
        dp = doc(c, actor, "DEPOSIT")
        insert(
            c,
            "customer_deposits",
            dict(
                id=dp["id"],
                sales_order_id=so["id"],
                customer_id=customer,
                receipt_payment_id=d["id"],
                amount=amount,
            ),
        )
        post(c, actor, dp["id"])
        entries = [(cash, amount, 0), ("2130", 0, amount)]
    else:
        allocated = ZERO
        for a in p.get("allocations", []):
            target = document(c, a["document_id"])
            invoice = require(
                c,
                (
                    "purchase_invoices"
                    if purpose == "supplier_payment"
                    and target["document_type"] == "PURCHASE_INVOICE"
                    else (
                        "consignment_settlements"
                        if purpose == "supplier_payment"
                        else "sales_invoices"
                    )
                ),
                target["id"],
            )
            need(
                (
                    invoice.get("supplier_id") == supplier
                    if purpose == "supplier_payment"
                    else invoice.get("customer_id") == customer
                ),
                "Pihak faktur tidak cocok",
            )
            q = money(dec(a["amount"], True))
            need(q <= invoice_due(c, target["id"]), "Alokasi melebihi saldo faktur")
            allocated += q
            insert(
                c,
                "payment_allocations",
                dict(
                    payment_id=d["id"],
                    target_document_id=target["id"],
                    amount=q,
                    reversal_of_id=None,
                ),
            )
        need(
            allocated == amount,
            "Seluruh pembayaran harus dialokasikan tepat ke saldo faktur",
        )
        entries = (
            [("2100", amount, 0), (cash, 0, amount)]
            if purpose == "supplier_payment"
            else [(cash, amount, 0), ("1300", 0, amount)]
        )
    journal(c, d["id"], "payment", entries)
    post(c, actor, d["id"])
    return d


def apply_deposit(c, actor, p):
    dep = require(c, "customer_deposits", p["deposit_id"])
    inv = require(c, "sales_invoices", p["invoice_id"])
    need(
        dep["sales_order_id"] == inv["sales_order_id"],
        "DP dan faktur harus untuk SO sama",
    )
    amount = money(dec(p["amount"], True))
    need(
        amount <= deposit_available(c, dep["id"])
        and amount <= invoice_due(c, inv["id"]),
        "Alokasi melebihi saldo DP/piutang",
    )
    d = doc(c, actor, "DEPOSIT_APPLICATION", {k: v for k, v in p.items() if k != "id"})
    a = insert(
        c,
        "deposit_applications",
        dict(
            id=d["id"],
            deposit_id=dep["id"],
            invoice_id=inv["id"],
            amount=amount,
            reversal_of_id=None,
        ),
    )
    journal(
        c, d["id"], "deposit_application", [("2130", amount, 0), ("1300", 0, amount)]
    )
    post(c, actor, d["id"])
    return a


def apply_credit(c, actor, p):
    cr = require(c, "credit_notes", p["credit_note_id"])
    inv = document(c, p["invoice_id"])
    amount = money(dec(p["amount"], True))
    need(
        amount <= credit_available(c, cr["id"]) and amount <= invoice_due(c, inv["id"]),
        "Kredit / saldo faktur tidak cukup",
    )
    target = require(
        c,
        "sales_invoices" if cr["direction"] == "payable" else "purchase_invoices",
        inv["id"],
    )
    need(
        (
            cr["customer_id"] == target.get("customer_id")
            if cr["direction"] == "payable"
            else cr["supplier_id"] == target.get("supplier_id")
        ),
        "Pihak kredit tidak cocok",
    )
    d = doc(c, actor, "CREDIT_APPLICATION", {k: v for k, v in p.items() if k != "id"})
    a = insert(
        c,
        "credit_applications",
        dict(
            id=d["id"],
            credit_note_id=cr["id"],
            invoice_document_id=inv["id"],
            amount=amount,
            reversal_of_id=None,
        ),
    )
    journal(
        c,
        d["id"],
        "credit_application",
        [
            ("2140" if cr["direction"] == "payable" else "2100", amount, 0),
            ("1300" if cr["direction"] == "payable" else "2150", 0, amount),
        ],
    )
    post(c, actor, d["id"])
    return a


def refund(c, actor, p, offline_authorized=False):
    origin = p.get("approval_document_id") or p.get("return_id")
    need(origin, "Dokumen persetujuan refund wajib")
    if not offline_authorized:
        approved(c, actor, origin, "refund")
    amount = money(dec(p["amount"], True))
    need(
        bool(p.get("deposit_id")) != bool(p.get("credit_note_id")),
        "Pilih satu sumber hak refund",
    )
    customer = None
    supplier = None
    if p.get("deposit_id"):
        cr = require(c, "customer_deposits", p["deposit_id"])
        need(amount <= deposit_available(c, cr["id"]), "Refund melebihi saldo DP")
        customer = cr["customer_id"]
        direction = "out"
        offset = "2130"
        need(cr["sales_order_id"] == origin, "Persetujuan harus merujuk SO pemilik DP")
    else:
        cr = require(c, "credit_notes", p["credit_note_id"])
        need(amount <= credit_available(c, cr["id"]), "Refund melebihi saldo kredit")
        customer = cr["customer_id"]
        supplier = cr["supplier_id"]
        direction = "out" if cr["direction"] == "payable" else "in"
        offset = "2140" if direction == "out" else "2150"
        need(
            cr["return_id"] == origin or cr["source_document_id"] == origin,
            "Persetujuan bukan untuk kredit ini",
        )
    d = doc(c, actor, "REFUND", p)
    cash = cash_account(c, p["cash_bank_account_id"])
    method = require(c, "payment_methods", p["method_id"])
    if not method["is_cash"]:
        need(p.get("reference"), "Bukti pengembalian non-tunai wajib")
    payment = insert(
        c,
        "payments",
        dict(
            id=d["id"],
            direction=direction,
            customer_id=customer,
            supplier_id=supplier,
            method_id=method["id"],
            cash_bank_account_id=p["cash_bank_account_id"],
            payment_date=d["business_date"],
            amount=amount,
            purpose="refund",
            reference=p.get("reference"),
        ),
    )
    insert(
        c,
        "refunds",
        dict(
            id=d["id"],
            payment_id=payment["id"],
            return_id=p.get("return_id"),
            terminal_id=p.get("terminal_id"),
            shift_id=p.get("shift_id"),
            reason=p["reason"],
        ),
    )
    insert(
        c,
        "refund_allocations",
        dict(
            refund_id=d["id"],
            credit_note_id=p.get("credit_note_id"),
            deposit_id=p.get("deposit_id"),
            amount=amount,
        ),
    )
    journal(
        c,
        d["id"],
        "refund",
        (
            [(offset, amount, 0), (cash, 0, amount)]
            if direction == "out"
            else [(cash, amount, 0), (offset, 0, amount)]
        ),
    )
    post(c, actor, d["id"])
    return d


def expense(c, actor, p):
    d = doc(c, actor, "EXPENSE", p)
    account = require(c, "chart_of_accounts", p["account_id"])
    need(account["account_type"] == "expense", "Pilih akun beban periode")
    amount = money(dec(p["amount"], True))
    cash = cash_account(c, p["cash_bank_account_id"])
    insert(
        c,
        "expenses",
        dict(
            id=d["id"],
            supplier_id=p.get("supplier_id"),
            account_id=account["id"],
            amount=amount,
            description=p["description"],
            payment_id=None,
        ),
    )
    journal(c, d["id"], "expense", [(account["code"], amount, 0), (cash, 0, amount)])
    post(c, actor, d["id"])
    return d


def close_checks(c, id):
    p = require(c, "fiscal_periods", id)
    checks = []

    def add(code, count):
        checks.append(dict(code=code, count=count, passed=count == 0))

    add(
        "dokumen_draft",
        len(
            [
                d
                for d in rows(c, "documents", status="draft")
                if p["start_date"] <= d["business_date"] <= p["end_date"]
            ]
        ),
    )
    add("selisih_transit", len(rows(c, "transfer_discrepancies", status="open")))
    add("hpp_provisional", len(rows(c, "negative_stock_cases", status="open")))
    terminals = rows(c, "pos_terminals", active=True)
    checkpoints = rows(c, "sync_checkpoints", stream="cloud_ack")
    add(
        "terminal_belum_rekonsiliasi",
        sum(
            1
            for t in terminals
            if not any(
                a["terminal_id"] == t["id"]
                and a["last_success_at"]
                and now() - a["last_success_at"].replace(tzinfo=dt.timezone.utc)
                < dt.timedelta(hours=1)
                for a in checkpoints
            )
        ),
    )
    add("konflik_sync", len(rows(c, "sync_conflicts", status="open")))
    add(
        "penerimaan_belum_ditagih",
        sum(
            1
            for gr in rows(c, "goods_receipts")
            if not rows(c, "purchase_invoices", goods_receipt_id=gr["id"])
        ),
    )
    return checks


def close_period(c, actor, id, p):
    per = require(c, "fiscal_periods", id)
    need(per["status"] == "open", "Periode tidak terbuka")
    d = doc(c, actor, "PERIOD_CLOSE", {k: v for k, v in p.items() if k != "id"})
    bad = [a for a in close_checks(c, id) if not a["passed"]]
    if bad:
        need(
            p.get("exception_document_id") and p.get("reason"),
            "Selesaikan pengecualian atau sertakan persetujuan dan alasan",
        )
        approved(c, actor, p["exception_document_id"], "period_close")
    for a in rows(c, "chart_of_accounts"):
        debit = ZERO
        credit = ZERO
        opening = ZERO
        for ln in rows(c, "journal_lines", account_id=a["id"]):
            j = require(c, "journal_entries", ln["journal_id"])
            if j["status"] != "posted":
                continue
            if j["entry_date"] < per["start_date"]:
                opening += ln["debit"] - ln["credit"]
            elif j["entry_date"] <= per["end_date"]:
                debit += ln["debit"]
                credit += ln["credit"]
        insert(
            c,
            "account_period_balances",
            dict(
                period_id=id,
                account_id=a["id"],
                opening_balance=opening,
                debit_total=debit,
                credit_total=credit,
                closing_balance=opening + debit - credit,
            ),
        )
    post(c, actor, d["id"])
    update(
        c,
        "fiscal_periods",
        id,
        status="closed",
        closed_at=now(),
        closed_by=actor,
        closing_document_id=d["id"],
    )
    return {"id": id, "exceptions": bad}


def reopen(c, actor, id, p):
    per = require(c, "fiscal_periods", id)
    need(per["status"] == "closed", "Periode belum ditutup")
    need(
        not any(
            r["status"] == "closed" and r["start_date"] > per["end_date"]
            for r in rows(c, "fiscal_periods")
        ),
        "Periode sesudahnya sudah ditutup",
    )
    approved(c, actor, p["approval_document_id"], "period_reopen")
    audit(c, actor, "fiscal_periods", id, "reopen", before=per, after=p)
    # Closing snapshots are derived, audited caches. Business journals remain immutable.
    c.execute(
        T["account_period_balances"]
        .delete()
        .where(T["account_period_balances"].c.period_id == id)
    )
    update(
        c,
        "fiscal_periods",
        id,
        status="open",
        closed_at=None,
        closed_by=None,
        closing_document_id=None,
    )
    return {"id": id}
