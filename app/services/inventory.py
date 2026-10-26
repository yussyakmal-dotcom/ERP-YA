from app.core import *
from app.services.approval import approved


def balance(c, pid, wid):
    require(c, "products", pid)
    require(c, "warehouses", wid)
    rr = rows(c, "stock_balances", product_id=pid, warehouse_id=wid)
    if rr:
        return rr[0]
    return insert(
        c,
        "stock_balances",
        dict(
            product_id=pid,
            warehouse_id=wid,
            quantity=0,
            reserved_quantity=0,
            inventory_value=0,
            avg_cost=0,
            version=0,
        ),
    )


def move(
    c,
    docid,
    linekey,
    pid,
    wid,
    quantity,
    kind,
    cost=None,
    allow_negative=False,
    negative_reason=None,
):
    qty = Decimal(str(quantity))
    need(qty.is_finite() and qty != 0, "Mutasi harus bernilai nonnol")
    p = require(c, "products", pid)
    need(not p["is_phantom"], "Paket SO tidak mempunyai saldo stok")
    d = document(c, docid)
    period(c, d["business_date"])
    b = balance(c, pid, wid)
    old = dec(b["quantity"]) if b["quantity"] >= 0 else Decimal(b["quantity"])
    if qty < 0 and not allow_negative:
        need(
            old - b["reserved_quantity"] >= -qty,
            "Stok tersedia tidak cukup; periksa reservasi",
            409,
        )
    if qty < 0 and allow_negative and old - b["reserved_quantity"] < -qty:
        need(bool(negative_reason), "Alasan stok minus POS wajib diisi")
    uc = dec(cost if cost is not None else b["avg_cost"])
    value_delta = qty * uc
    transient = kind.startswith("consignment_")
    provisional = qty < 0 and old + qty < 0 and not transient
    correction = ZERO
    movement = insert(
        c,
        "stock_movements",
        dict(
            source_document_id=docid,
            source_line_key=str(linekey),
            product_id=pid,
            warehouse_id=wid,
            movement_kind=kind,
            qty_input=abs(qty),
            uom_id=p["base_uom_id"],
            factor_snapshot=1,
            qty_delta=qty,
            unit_cost=uc,
            value_delta=value_delta,
            effective_at=dt.datetime.combine(d["business_date"], dt.time(), WIB),
            posted_at=now(),
            is_provisional=provisional,
            negative_reason=negative_reason,
            reversal_of_id=None,
        ),
    )
    if provisional:
        shortage = min(-qty, -(old + qty))
        insert(
            c,
            "negative_stock_cases",
            dict(
                out_movement_id=movement["id"],
                product_id=pid,
                warehouse_id=wid,
                qty_short=shortage,
                qty_settled=0,
                provisional_unit_cost=uc,
                status="open",
            ),
        )
    if qty > 0 and not transient:
        remaining = qty
        for case in sorted(
            rows(c, "negative_stock_cases", product_id=pid, warehouse_id=wid),
            key=lambda r: r["created_at"],
        ):
            if case["status"] == "closed" or remaining <= 0:
                continue
            settle = min(remaining, case["qty_short"] - case["qty_settled"])
            delta = settle * (uc - case["provisional_unit_cost"])
            remaining -= settle
            correction += delta
            update(
                c,
                "negative_stock_cases",
                case["id"],
                qty_settled=case["qty_settled"] + settle,
                status=(
                    "closed"
                    if settle + case["qty_settled"] == case["qty_short"]
                    else "open"
                ),
            )
            if delta:
                event = "hpp-" + case["id"][:12] + "-" + movement["id"][:12]
                j = journal(
                    c,
                    docid,
                    event,
                    [
                        ("5000", max(delta, ZERO), max(-delta, ZERO)),
                        ("1200", max(-delta, ZERO), max(delta, ZERO)),
                    ],
                )
                insert(
                    c,
                    "inventory_cost_adjustments",
                    dict(
                        source_document_id=docid,
                        negative_case_id=case["id"],
                        receipt_movement_id=movement["id"],
                        qty_settled=settle,
                        value_delta=delta,
                        journal_id=j["id"],
                        reason="Penyelesaian HPP provisional",
                    ),
                )
    new = old + qty
    val = Decimal(b["inventory_value"]) + value_delta - correction
    if new == 0:
        val = ZERO
    avg = b["avg_cost"] if transient else (val / new) if new > 0 else uc
    update(
        c,
        "stock_balances",
        b["id"],
        quantity=new,
        inventory_value=val,
        avg_cost=avg,
        version=b["version"] + 1,
    )
    return movement


def transfer_create(c, actor, p):
    source = require(c, "warehouses", p["from_warehouse_id"])
    dest = require(c, "warehouses", p["to_warehouse_id"])
    need(
        source["id"] != dest["id"]
        and source["kind"] != "transit"
        and dest["kind"] != "transit",
        "Pilih lokasi fisik berbeda",
    )
    transit = rows(c, "warehouses", kind="transit")[0]
    d = doc(c, actor, "TRANSFER", p)
    insert(
        c,
        "transfer_orders",
        dict(
            id=d["id"],
            from_warehouse_id=source["id"],
            to_warehouse_id=dest["id"],
            transit_warehouse_id=transit["id"],
            dispatch_at=None,
            expected_arrival=p.get("expected_arrival"),
            notes=p.get("notes", ""),
        ),
    )
    need(p.get("lines"), "Pilih barang transfer")
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        q = dec(a["quantity"], True)
        insert(
            c,
            "transfer_lines",
            dict(
                transfer_id=d["id"],
                product_id=product["id"],
                demand_id=a.get("demand_id"),
                qty_input=q,
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_dispatched=q * u["factor_to_base"],
                unit_cost_snapshot=0,
            ),
        )
    return d


def dispatch(c, actor, id):
    document(c, id, ["draft"], "TRANSFER")
    tr = require(c, "transfer_orders", id)
    for a in rows(c, "transfer_lines", transfer_id=id):
        product = require(c, "products", a["product_id"])
        source = require(c, "warehouses", tr["from_warehouse_id"])
        dest = require(c, "warehouses", tr["to_warehouse_id"])
        if source["kind"] == "kitchen_finished" and product["is_manufacturable"]:
            expected = (
                "central"
                if product["intermediate_type"] == "premix"
                else (
                    "kitchen_raw"
                    if product["intermediate_type"] == "wip"
                    else "packing"
                )
            )
            need(
                dest["kind"] == expected,
                "Rute hasil produksi tidak sesuai: " + expected,
            )
        mv = move(
            c,
            id,
            a["id"],
            a["product_id"],
            tr["from_warehouse_id"],
            -a["qty_dispatched"],
            "transfer_dispatch",
        )
        move(
            c,
            id,
            a["id"] + "-transit",
            a["product_id"],
            tr["transit_warehouse_id"],
            a["qty_dispatched"],
            "transfer_in_transit",
            mv["unit_cost"],
        )
        update(c, "transfer_lines", a["id"], unit_cost_snapshot=mv["unit_cost"])
    update(c, "transfer_orders", id, dispatch_at=now())
    post(c, actor, id, "in_transit")
    return require(c, "transfer_orders", id)


def line_remaining(c, line):
    received = sum(
        (
            r["qty_received"]
            for r in rows(c, "transfer_receipt_lines", transfer_line_id=line["id"])
        ),
        ZERO,
    )
    resolved = ZERO
    for dis in rows(c, "transfer_discrepancies", transfer_line_id=line["id"]):
        resolved += sum(
            (
                r["qty_base"]
                for r in rows(c, "transfer_resolutions", discrepancy_id=dis["id"])
                if r["resolution_type"] not in ("in_transit", "received")
            ),
            ZERO,
        )
    return line["qty_dispatched"] - received - resolved


def receive_transfer(c, actor, id, p):
    document(c, id, ["in_transit", "partial"], "TRANSFER")
    tr = require(c, "transfer_orders", id)
    dd = doc(c, actor, "TRANSFER_RECEIPT", {k: v for k, v in p.items() if k != "id"})
    r = insert(
        c,
        "transfer_receipts",
        dict(id=dd["id"], transfer_id=id, received_at=now(), received_by=actor),
    )
    need(p.get("lines"), "Isi jumlah aktual diterima")
    for a in p["lines"]:
        ln = require(c, "transfer_lines", a["line_id"])
        need(ln["transfer_id"] == id, "Baris berasal dari transfer lain")
        qty = dec(a["quantity"])
        remaining = line_remaining(c, ln)
        need(qty <= remaining, "Penerimaan melebihi sisa transit")
        if qty:
            rl = insert(
                c,
                "transfer_receipt_lines",
                dict(receipt_id=r["id"], transfer_line_id=ln["id"], qty_received=qty),
            )
            move(
                c,
                dd["id"],
                rl["id"],
                ln["product_id"],
                tr["transit_warehouse_id"],
                -qty,
                "transfer_receive_out",
                ln["unit_cost_snapshot"],
            )
            move(
                c,
                dd["id"],
                rl["id"] + "-in",
                ln["product_id"],
                tr["to_warehouse_id"],
                qty,
                "transfer_receive_in",
                ln["unit_cost_snapshot"],
            )
        else:
            rl = None
        rem = remaining - qty
        cases = rows(c, "transfer_discrepancies", transfer_line_id=ln["id"])
        if not cases and rem:
            insert(
                c,
                "transfer_discrepancies",
                dict(
                    transfer_line_id=ln["id"],
                    qty_disputed=rem,
                    qty_resolved=0,
                    reason=p.get("reason", "Jumlah terima kurang"),
                    status="open",
                    responsible_user_id=actor,
                ),
            )
        elif cases and qty:
            case = cases[0]
            applied = min(qty, case["qty_disputed"] - case["qty_resolved"])
            rd = doc(c, actor, "TRANSIT_RESOLUTION")
            insert(
                c,
                "transfer_resolutions",
                dict(
                    id=rd["id"],
                    discrepancy_id=case["id"],
                    resolution_type="received",
                    qty_base=applied,
                    destination_warehouse_id=tr["to_warehouse_id"],
                    related_receipt_line_id=rl["id"],
                    notes="Penerimaan tambahan",
                ),
            )
            post(c, actor, rd["id"])
            update(
                c,
                "transfer_discrepancies",
                case["id"],
                qty_resolved=case["qty_resolved"] + applied,
                status=(
                    "closed"
                    if case["qty_resolved"] + applied == case["qty_disputed"]
                    else "open"
                ),
            )
    need(
        rows(c, "transfer_receipt_lines", receipt_id=r["id"]),
        "Minimal satu jumlah diterima lebih dari nol",
    )
    remaining = sum(
        (line_remaining(c, a) for a in rows(c, "transfer_lines", transfer_id=id)), ZERO
    )
    post(c, actor, dd["id"])
    update(c, "documents", id, status="received" if remaining == 0 else "partial")
    return r


def resolve(c, actor, id, p):
    case = require(c, "transfer_discrepancies", id)
    need(case["status"] == "open", "Kasus sudah selesai", 409)
    ln = require(c, "transfer_lines", case["transfer_line_id"])
    tr = require(c, "transfer_orders", ln["transfer_id"])
    typ = p["resolution_type"]
    need(
        typ in ["in_transit", "returned", "damaged", "lost", "dispatch_error"],
        "Jenis penyelesaian tidak valid",
    )
    q = dec(p["quantity"], True)
    need(
        q <= case["qty_disputed"] - case["qty_resolved"],
        "Jumlah melebihi selisih yang belum selesai",
    )
    dd = doc(c, actor, "TRANSIT_RESOLUTION", {k: v for k, v in p.items() if k != "id"})
    if typ != "in_transit":
        # The approval is bound to the original transfer revision and case payload.
        approved(c, actor, tr["id"], "transit_resolution")
        need(p.get("evidence"), "Bukti penyelesaian wajib diisi")
        move(
            c,
            dd["id"],
            id,
            ln["product_id"],
            tr["transit_warehouse_id"],
            -q,
            "transit_" + typ,
            ln["unit_cost_snapshot"],
        )
        if typ in ("returned", "dispatch_error"):
            need(
                p.get("confirmed_at_source") is True,
                "Konfirmasi barang ada / tiba kembali di sumber wajib",
            )
            move(
                c,
                dd["id"],
                id + "-source",
                ln["product_id"],
                tr["from_warehouse_id"],
                q,
                "transit_return_source",
                ln["unit_cost_snapshot"],
            )
        else:
            journal(
                c,
                dd["id"],
                "transit_loss",
                [
                    ("5100", q * ln["unit_cost_snapshot"], 0),
                    ("1200", 0, q * ln["unit_cost_snapshot"]),
                ],
            )
        update(
            c,
            "transfer_discrepancies",
            id,
            qty_resolved=case["qty_resolved"] + q,
            status=(
                "closed" if case["qty_resolved"] + q == case["qty_disputed"] else "open"
            ),
        )
    rr = insert(
        c,
        "transfer_resolutions",
        dict(
            id=dd["id"],
            discrepancy_id=id,
            resolution_type=typ,
            qty_base=q,
            destination_warehouse_id=(
                tr["from_warehouse_id"]
                if typ in ("returned", "dispatch_error")
                else None
            ),
            related_receipt_line_id=None,
            notes=p.get("notes", "") + " " + p.get("evidence", ""),
        ),
    )
    if typ != "in_transit":
        from app.services.approval import invalidate

        invalidate(c, tr["id"])  # another disposition must be reviewed separately
        if all(
            line_remaining(c, a) == 0
            for a in rows(c, "transfer_lines", transfer_id=tr["id"])
        ):
            update(c, "documents", tr["id"], status="received")
    post(c, actor, dd["id"])
    return rr


def adjust(c, actor, p):
    d = doc(c, actor, "ADJUSTMENT", p)
    insert(
        c,
        "inventory_adjustments",
        dict(
            id=d["id"],
            warehouse_id=p["warehouse_id"],
            reason=p["reason"],
            counted_at=p.get("counted_at"),
            notes=p.get("notes", ""),
        ),
    )
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        b = balance(c, product["id"], p["warehouse_id"])
        counted = dec(a["counted_quantity"]) if "counted_quantity" in a else None
        baseline = Decimal(str(a.get("baseline_quantity", b["quantity"])))
        delta = (
            counted - baseline
            if counted is not None
            else Decimal(str(a["delta"])) * u["factor_to_base"]
        )
        need(delta.is_finite() and delta != 0, "Jumlah koreksi harus nonnol")
        insert(
            c,
            "inventory_adjustment_lines",
            dict(
                adjustment_id=d["id"],
                product_id=product["id"],
                qty_input=abs(delta) / u["factor_to_base"],
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_delta=delta,
                counted_qty=counted,
                baseline_qty=baseline,
                movement_watermark=a.get("movement_watermark"),
                unit_cost=dec(a.get("unit_cost", b["avg_cost"])),
            ),
        )
    return d


def post_adjust(c, actor, id):
    document(c, id, ["draft"], "ADJUSTMENT")
    a = require(c, "inventory_adjustments", id)
    approved(c, actor, id, "stock_adjustment")
    total = ZERO
    for ln in rows(c, "inventory_adjustment_lines", adjustment_id=id):
        mv = move(
            c,
            id,
            ln["id"],
            ln["product_id"],
            a["warehouse_id"],
            ln["qty_delta"],
            "adjustment",
            ln["unit_cost"],
        )
        total += mv["value_delta"]
    journal(
        c,
        id,
        "stock_adjustment",
        [
            ("1200", max(total, ZERO), max(-total, ZERO)),
            (
                "3000" if a["reason"] == "opening" else "5100",
                max(-total, ZERO),
                max(total, ZERO),
            ),
        ],
    )
    post(c, actor, id)
    return {"id": id}


def reserve(c, actor, p):
    d = require(c, "demand_lines", p["demand_id"])
    need(d["status"] == "open", "Kebutuhan sudah ditutup")
    q = dec(p["quantity"], True)
    b = balance(c, d["product_id"], p["warehouse_id"])
    need(
        b["quantity"] - b["reserved_quantity"] >= q,
        "Stok tersedia tidak cukup untuk reservasi",
    )
    reserved = sum(
        (
            r["qty_reserved"] - r["qty_released"]
            for r in rows(c, "stock_reservations", demand_id=d["id"])
        ),
        ZERO,
    )
    need(reserved + q <= d["qty_required"], "Reservasi melebihi kebutuhan")
    r = insert(
        c,
        "stock_reservations",
        dict(
            demand_id=d["id"],
            product_id=d["product_id"],
            warehouse_id=p["warehouse_id"],
            qty_reserved=q,
            qty_consumed=0,
            qty_released=0,
            status="active",
        ),
    )
    update(c, "stock_balances", b["id"], reserved_quantity=b["reserved_quantity"] + q)
    audit(c, actor, "stock_reservations", r["id"], "reserve", after=r)
    return r


def consume_reservation(c, demand_id, warehouse_id, qty):
    left = qty
    selected = []
    for r in rows(
        c,
        "stock_reservations",
        demand_id=demand_id,
        warehouse_id=warehouse_id,
        status="active",
    ):
        q = min(left, r["qty_reserved"] - r["qty_consumed"] - r["qty_released"])
        if q > 0:
            b = balance(c, r["product_id"], warehouse_id)
            update(
                c,
                "stock_balances",
                b["id"],
                reserved_quantity=b["reserved_quantity"] - q,
            )
            update(
                c,
                "stock_reservations",
                r["id"],
                qty_consumed=r["qty_consumed"] + q,
                status=(
                    "consumed"
                    if r["qty_consumed"] + r["qty_released"] + q == r["qty_reserved"]
                    else "active"
                ),
            )
            left -= q
            selected.append(r["id"])
        if not left:
            break
    return selected
