from app.core import *
from app.services.inventory import move, balance
from app.services import returns as return_service, finance
from app.services import commerce


def next_sequence(c, terminal):
    return (
        max(
            [r["local_sequence"] for r in rows(c, "sync_outbox", terminal_id=terminal)],
            default=0,
        )
        + 1
    )


def authorize(c, actor, action, p, terminal, replay=False):
    proof = p.get("_authorization") if replay else None
    if not replay:
        a = p.get("authorization") or {}
        user = require(c, "users", a.get("user_id", ""))
        key = "pin:" + user["id"]
        attempt = get(c, "app_security", key)
        if attempt and attempt["blocked_until"]:
            need(
                attempt["blocked_until"].replace(tzinfo=dt.timezone.utc) <= now(),
                "PIN sementara terkunci",
                403,
            )
        need(
            verify(str(a.get("pin", "")), user["pin_hash"]),
            "PIN supervisor tidak valid",
            403,
        )
        proof = {
            "actor_id": user["id"],
            "credential_version": user["credential_version"],
            "action": action,
            "at": now().isoformat(),
        }
    need(
        proof and proof["action"] == action,
        "Bukti persetujuan supervisor tidak tersedia",
        403,
    )
    supervisor = require(c, "users", proof["actor_id"])
    need(
        supervisor["active"]
        and supervisor["credential_version"] == proof["credential_version"],
        "Kredensial supervisor berubah; perlu tinjauan",
        409,
    )
    from app.services.approval import in_range

    amount = (
        dec(p.get("discount_amount", 0))
        if action == "pos_discount"
        else sum(
            (
                money(
                    dec(a["quantity"], True)
                    * require(c, "pos_sale_lines", a["line_id"])["line_total"]
                    / require(c, "pos_sale_lines", a["line_id"])["qty_base"]
                )
                for a in p.get("lines", [])
            ),
            ZERO,
        )
    )
    rules = [
        r
        for r in rows(c, "approval_rules", action_code=action)
        if r["active"]
        and r["offline_allowed"]
        and as_utc(r["effective_from"]) <= now()
        and in_range(r, amount)
    ]
    need(rules, "Izin offline untuk tindakan ini belum dikonfigurasi", 403)
    rule = max(rules, key=lambda r: r["version"])
    steps = rows(c, "approval_steps", rule_id=rule["id"])
    roles = {r["role_id"] for r in rows(c, "user_roles", user_id=supervisor["id"])}
    need(
        len(steps) == 1 and steps[0]["required_count"] == 1,
        "POS offline membutuhkan aturan satu supervisor; tindakan bertingkat menunggu backoffice",
    )
    step = steps[0]
    need(
        step["approver_user_id"] == supervisor["id"]
        or step["approver_role_id"] in roles,
        "Supervisor tidak berhak untuk tindakan ini",
        403,
    )
    need(
        step["allow_self_approval"] or actor != supervisor["id"],
        "Persetujuan sendiri tidak diizinkan",
        403,
    )
    proof.update(rule_id=rule["id"], rule_version=rule["version"], amount=str(amount))
    return proof


def record_authorization(c, actor, id, proof, reason, terminal):
    from app.services.approval import request, decide

    q = request(c, actor, id, proof["action"], reason, amount=proof["amount"])
    return decide(c, proof["actor_id"], q["id"], "approve", reason, terminal)


def open_shift(c, actor, p):
    terminal = require(c, "pos_terminals", p["terminal_id"])
    need(terminal["active"], "Terminal nonaktif")
    need(
        not [
            s
            for s in rows(c, "pos_shifts", terminal_id=terminal["id"])
            if not s["closed_at"]
        ],
        "Terminal masih mempunyai shift aktif",
        409,
    )
    d = doc(c, actor, "SHIFT", p)
    r = insert(
        c,
        "pos_shifts",
        dict(
            id=d["id"],
            terminal_id=terminal["id"],
            opened_by=actor,
            closed_by=None,
            opened_at=p.get("_opened_at") or now(),
            closed_at=None,
            opening_cash=money(dec(p["opening_cash"])),
            actual_closing_cash=None,
            expected_closing_cash=None,
            variance=None,
        ),
    )
    post(c, actor, d["id"], "open")
    return r


def sale(c, actor, p, replay=False):
    shift = require(c, "pos_shifts", p["shift_id"])
    need(not shift["closed_at"], "Shift sudah ditutup", 409)
    need(
        shift["opened_by"] == actor or "*" in perms(c, actor),
        "Gunakan shift kasir sendiri",
        403,
    )
    terminal = require(c, "pos_terminals", shift["terminal_id"])
    need(p.get("lines"), "Keranjang kosong")
    sequence = p.get(
        "_sequence",
        max(
            next_sequence(c, terminal["id"]),
            max(
                [
                    s["local_sequence"]
                    for s in rows(c, "pos_sales", terminal_id=terminal["id"])
                ],
                default=0,
            )
            + 1,
        ),
    )
    d = doc(
        c,
        actor,
        "POS_SALE",
        {
            **p,
            "document_no": p.get("document_no")
            or terminal["code"]
            + "-"
            + now().astimezone(WIB).strftime("%y%m%d")
            + "-"
            + str(sequence).zfill(6),
        },
    )
    lines = []
    subtotal = ZERO
    discount = ZERO
    require(c, "price_lists", p["price_list_id"])
    day = d["business_date"]
    proof = None
    if dec(p.get("discount_amount", 0)) > 0:
        need(p.get("discount_reason"), "Alasan diskon wajib")
        proof = authorize(c, actor, "pos_discount", p, terminal["id"], replay)
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        need(
            product["is_saleable"] and not product["is_phantom"] and u["allow_sale"],
            "POS menjual produk dan kemasan terpisah, bukan SKU paket SO",
        )
        q = dec(a["quantity"], True)
        unitdef = require(c, "uoms", u["uom_id"])
        need(
            unitdef["allow_decimal"] or q == q.to_integral_value(),
            "Satuan ini tidak menerima pecahan",
        )
        prices = [
            i
            for i in rows(
                c,
                "price_list_items",
                price_list_id=p["price_list_id"],
                product_uom_id=u["id"],
            )
            if valid_at(i, p.get("_sold_at"))
        ]
        price = (
            dec(a["_unit_price"])
            if replay and "_unit_price" in a
            else (
                max(prices, key=lambda r: r["valid_from"])["price"]
                if prices
                else product["default_sale_price"] * u["factor_to_base"]
            )
        )
        amount = money(q * price)
        subtotal += amount
        source = a.get("stock_source")
        need(
            source in ("owned", "consignment"),
            "Pilih sumber barang: owned atau consignment",
        )
        agreement = None
        if source == "consignment":
            agreement = require(c, "consignment_agreements", a.get("agreement_id", ""))
            need(
                agreement["active"]
                and agreement["product_id"] == product["id"]
                and agreement["warehouse_id"] == terminal["warehouse_id"]
                and valid_at(agreement, p.get("_sold_at")),
                "Perjanjian titipan tidak berlaku untuk SKU/toko/tanggal ini",
            )
        lines.append(
            dict(
                id=a.get("_line_id") or uid(),
                pos_sale_id=d["id"],
                product_id=product["id"],
                qty_input=q,
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_base=q * u["factor_to_base"],
                unit_price_input=price,
                discount_amount=0,
                tax_snapshot={},
                line_total=amount,
                stock_source=source,
                agreement_id=agreement["id"] if agreement else None,
                cost_snapshot=None,
                negative_reason=a.get("negative_reason")
                or (
                    "Stok gabungan minus setelah sinkronisasi terminal"
                    if replay
                    else None
                ),
            )
        )
    pricing = commerce.quote(c, p, replay)
    discount = pricing["discount"]
    total = pricing["total"]
    insert(
        c,
        "pos_sales",
        dict(
            id=d["id"],
            terminal_id=terminal["id"],
            shift_id=shift["id"],
            customer_id=p.get("customer_id"),
            price_list_id=p["price_list_id"],
            local_sequence=sequence,
            sold_at=p.get("_sold_at") or now(),
            subtotal=subtotal,
            discount_total=discount,
            tax_total=pricing["tax_total"],
            total=total,
            offline=p.get("offline", False),
        ),
    )
    cost = ZERO
    consign = ZERO
    allocated = ZERO
    for i, a in enumerate(lines):
        a["discount_amount"] = pricing["lines"][i]["discount"]
        a["line_total"] = pricing["lines"][i]["total"]
        a["tax_snapshot"] = pricing["lines"][i]["tax"]
        ln = insert(c, "pos_sale_lines", a)
        q = ln["qty_base"]
        if ln["stock_source"] == "consignment":
            ag = require(c, "consignment_agreements", ln["agreement_id"])
            cm = move(
                c,
                d["id"],
                ln["id"] + "-recognize",
                ln["product_id"],
                terminal["warehouse_id"],
                q,
                "consignment_recognition",
                ag["unit_cost_base"],
            )
            consign += q * ag["unit_cost_base"]
            mv = move(
                c,
                d["id"],
                ln["id"],
                ln["product_id"],
                terminal["warehouse_id"],
                -q,
                "consignment_sale",
                ag["unit_cost_base"],
                True,
                "Barang titipan terjual",
            )
            insert(
                c,
                "consignment_sales",
                dict(
                    pos_sale_line_id=ln["id"],
                    agreement_id=ag["id"],
                    supplier_id=ag["supplier_id"],
                    qty_base=q,
                    unit_cost_snapshot=ag["unit_cost_base"],
                    recognized_in_movement_id=cm["id"],
                    recognized_out_movement_id=mv["id"],
                ),
            )
        else:
            mv = move(
                c,
                d["id"],
                ln["id"],
                ln["product_id"],
                terminal["warehouse_id"],
                -q,
                "pos_sale",
                allow_negative=True,
                negative_reason=ln["negative_reason"],
            )
        update(c, "pos_sale_lines", ln["id"], cost_snapshot=mv["unit_cost"])
        cost += q * mv["unit_cost"]
    tendered = ZERO
    cash_entries = []
    for a in p.get("tenders", []):
        method = require(c, "payment_methods", a["method_id"])
        applied = money(dec(a["amount_applied"], True))
        received = money(dec(a.get("amount_received", applied)))
        change = received - applied
        need(
            change >= 0 and (method["is_cash"] or change == 0),
            "Kembalian hanya diperbolehkan dari tender tunai",
        )
        if not method["is_cash"]:
            need(
                a.get("provider_reference")
                and a.get("verification_status") == "verified",
                "Pembayaran elektronik perlu bukti dan verifikasi yang valid",
            )
        account = finance.cash_account(c, a["cash_bank_account_id"])
        cash_entries.append((account, applied, 0))
        tendered += applied
        insert(
            c,
            "pos_tenders",
            dict(
                pos_sale_id=d["id"],
                method_id=method["id"],
                amount_applied=applied,
                amount_received=received,
                change_amount=change,
                provider_reference=a.get("provider_reference"),
                verification_status="cash" if method["is_cash"] else "verified",
                cash_bank_account_id=a["cash_bank_account_id"],
            ),
        )
    need(
        tendered == total, "Total alokasi pembayaran harus sama dengan total penjualan"
    )
    taxcode = (
        pricing["lines"][0]["tax"]["output_account_code"]
        if pricing["tax_total"]
        else None
    )
    taxentries = [(taxcode, 0, pricing["tax_total"])] if taxcode else []
    journal(
        c,
        d["id"],
        "pos_sale",
        cash_entries
        + [
            ("4000", 0, pricing["net"]),
            ("1200", consign, 0),
            ("2100", 0, consign),
            ("5000", cost, 0),
            ("1200", 0, cost),
        ]
        + taxentries,
    )
    if p.get("_redemption"):
        commerce.redeem(
            c, terminal, d["id"], p["_redemption"], local=bool(p.get("_local_runtime"))
        )
    if not p.get("_local_runtime"):
        commerce.earn(c, d["id"], p.get("customer_id"), total)
    if proof:
        record_authorization(
            c, actor, d["id"], proof, p["discount_reason"], terminal["id"]
        )
    post(c, actor, d["id"])
    return {
        "id": d["id"],
        "document_no": d["document_no"],
        "total": total,
        "status": "stored_local",
        "authorization": proof,
        "pricing": clean(pricing),
    }


def expected_cash(c, id):
    shift = require(c, "pos_shifts", id)
    cash = shift["opening_cash"]
    for s in rows(c, "pos_sales", shift_id=id):
        for t in rows(c, "pos_tenders", pos_sale_id=s["id"]):
            if require(c, "payment_methods", t["method_id"])["is_cash"]:
                cash += t["amount_applied"]
    cash += sum(
        (a["amount_signed"] for a in rows(c, "pos_cash_entries", shift_id=id)), ZERO
    )
    for r in rows(c, "refunds", shift_id=id):
        payment = require(c, "payments", r["payment_id"])
        if require(c, "payment_methods", payment["method_id"])["is_cash"]:
            cash -= payment["amount"]
    return cash


def cash_entry(c, actor, p):
    shift = require(c, "pos_shifts", p["shift_id"])
    need(not shift["closed_at"], "Shift sudah ditutup")
    need(p.get("reason"), "Alasan kas wajib")
    kind = p["kind"]
    need(kind in ("in", "out", "deposit"), "Jenis gerakan kas salah")
    a = money(dec(p["amount"], True))
    d = doc(c, actor, "POS_CASH", p)
    r = insert(
        c,
        "pos_cash_entries",
        dict(
            shift_id=shift["id"],
            document_id=d["id"],
            kind=kind,
            amount_signed=a if kind == "in" else -a,
            reason=p["reason"],
        ),
    )
    post(c, actor, d["id"])
    return r


def close_shift(c, actor, p):
    shift = require(c, "pos_shifts", p["shift_id"])
    need(not shift["closed_at"], "Shift sudah ditutup")
    need(
        shift["opened_by"] == actor or "*" in perms(c, actor),
        "Hak tutup shift tidak sesuai",
        403,
    )
    expected = expected_cash(c, shift["id"])
    actual = money(dec(p["actual_cash"]))
    variance = actual - expected
    need(not variance or p.get("reason"), "Selisih kas harus diberi alasan")
    update(
        c,
        "pos_shifts",
        shift["id"],
        closed_by=actor,
        closed_at=p.get("_closed_at") or now(),
        actual_closing_cash=actual,
        expected_closing_cash=expected,
        variance=variance,
    )
    post(c, actor, shift["id"], "closed")
    return require(c, "pos_shifts", shift["id"])


def pos_return(c, actor, p, replay=False):
    shift = require(c, "pos_shifts", p["shift_id"])
    need(not shift["closed_at"], "Shift sudah ditutup")
    terminal = require(c, "pos_terminals", shift["terminal_id"])
    sale = require(c, "pos_sales", p["source_document_id"])
    need(
        sale["terminal_id"] == terminal["id"],
        "Struk terminal lain: gunakan validasi online di backoffice; tidak dapat diretur lokal",
        409,
    )
    proof = authorize(c, actor, "pos_refund", p, terminal["id"], replay)
    args = {
        **p,
        "channel": "pos",
        "side": "customer",
        "warehouse_id": terminal["warehouse_id"],
        "terminal_id": terminal["id"],
        "customer_id": sale["customer_id"],
    }
    result = return_service.create(c, actor, args, True)
    record_authorization(c, actor, result["id"], proof, p["reason"], terminal["id"])
    if p.get("refund_now", True):
        ref = finance.refund(
            c,
            actor,
            {
                **args,
                "id": p.get("_refund_id") or uid(),
                "approval_document_id": result["id"],
                "return_id": result["id"],
                "credit_note_id": result["credit_note_id"],
                "amount": str(result["credit_amount"]),
            },
            True,
        )
        result["refund_id"] = ref["id"]
    return {**result, "authorization": proof}
