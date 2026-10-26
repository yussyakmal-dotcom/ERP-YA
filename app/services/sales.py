from app.core import *
from app.services.approval import approved, invalidate
from app.services.inventory import move, balance
from app.services import commerce


def create_so(c, actor, p):
    d = doc(c, actor, "SO", p)
    sv = require(c, "schedule_versions", p["schedule_version_id"])
    outlet = require(c, "outlets", p["outlet_id"])
    require(c, "customers", p["customer_id"])
    delivery = dt.date.fromisoformat(p["delivery_date"])
    need(delivery > d["business_date"], "SO harus dikirim minimal H+1")
    need(sv["cutoff_day_offset"] == 1, "Batas pesanan wajib H-1")
    need(sv["cutoff_time"] and sv["delivery_time"], "Jadwal belum lengkap")
    packing = require(c, "warehouses", p["fulfillment_warehouse_id"])
    need(packing["kind"] == "packing", "Pemenuhan SO harus dari packing")
    cutoff = dt.datetime.combine(
        delivery - dt.timedelta(days=1), sv["cutoff_time"], WIB
    )
    send = dt.datetime.combine(delivery, sv["delivery_time"], WIB)
    need(
        sv["effective_from"] <= d["business_date"]
        and (not sv["effective_to"] or sv["effective_to"] >= d["business_date"]),
        "Versi jadwal belum / tidak lagi berlaku",
    )
    subtotal = ZERO
    prepared = []
    need(p.get("lines"), "SO harus mempunyai item")
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        need(product["is_saleable"], "Produk tidak dapat dijual")
        q = dec(a["quantity"], True)
        price = dec(a["unit_price"])
        amount = money(q * price)
        subtotal += amount
        prepared.append(
            dict(
                sales_order_id=d["id"],
                product_id=product["id"],
                qty_input=q,
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_base=q * u["factor_to_base"],
                unit_price_input=price,
                discount_amount=0,
                tax_snapshot={},
                line_total=amount,
                is_package_snapshot=product["is_phantom"],
            )
        )
    pricing = commerce.quote(
        c,
        dict(
            channel="so",
            price_list_id=p["price_list_id"],
            lines=[
                dict(
                    product_id=a["product_id"],
                    uom_id=a["uom_id"],
                    quantity=str(a["qty_input"]),
                    _unit_price=str(a["unit_price_input"]),
                )
                for a in prepared
            ],
        ),
        True,
    )
    for a, price in zip(prepared, pricing["lines"]):
        a["line_total"] = price["total"]
        a["tax_snapshot"] = price["tax"]
    insert(
        c,
        "sales_orders",
        dict(
            id=d["id"],
            outlet_id=outlet["id"],
            customer_id=p["customer_id"],
            fulfillment_warehouse_id=packing["id"],
            order_date=d["business_date"],
            delivery_date=delivery,
            schedule_version_id=sv["id"],
            cutoff_at_snapshot=cutoff,
            delivery_at_snapshot=send,
            price_list_id=p["price_list_id"],
            sales_user_id=actor,
            sales_group_name=p.get("sales_group_name"),
            subtotal=subtotal,
            discount_total=0,
            tax_total=pricing["tax_total"],
            total=pricing["total"],
        ),
    )
    for a in prepared:
        insert(c, "sales_order_lines", a)
    return d


def so_components(c, so):
    for ln in rows(c, "sales_order_lines", sales_order_id=so["id"]):
        p = require(c, "products", ln["product_id"])
        if ln["is_package_snapshot"]:
            boms = [
                b
                for b in rows(c, "boms", product_id=p["id"])
                if b["purpose"] == "package" and b["active"]
            ]
            need(boms, "Resep komponen paket belum tersedia")
            bom = max(boms, key=lambda b: b["version"])
            parts = rows(c, "bom_lines", bom_id=bom["id"])
            need(parts, "Komponen paket kosong")
        else:
            bom = None
            parts = [dict(component_product_id=p["id"], qty_base=1, id=None)]
        for a in parts:
            cp = require(c, "products", a["component_product_id"])
            need(not cp["is_phantom"], "Paket bertingkat tidak didukung")
            per = Decimal(a["qty_base"]) / (bom["output_qty_base"] if bom else 1)
            source = (
                "production"
                if cp["is_manufacturable"]
                else "purchase" if cp["is_purchasable"] else "stock"
            )
            comp = insert(
                c,
                "sales_order_components",
                dict(
                    sales_order_line_id=ln["id"],
                    product_id=cp["id"],
                    bom_line_id=a["id"],
                    qty_per_parent_base=per,
                    qty_required_base=per * ln["qty_base"],
                    source_method=source,
                    version=1,
                ),
            )
            insert(
                c,
                "demand_lines",
                dict(
                    product_id=cp["id"],
                    so_component_id=comp["id"],
                    store_request_line_id=None,
                    source_document_id=so["id"],
                    origin="sales_order",
                    required_at=so["delivery_at_snapshot"],
                    schedule_version_id=so["schedule_version_id"],
                    revision=1,
                    qty_required=comp["qty_required_base"],
                    status="open",
                ),
            )


def confirm_so(c, actor, id):
    d = document(c, id, ["draft"], "SO")
    so = require(c, "sales_orders", id)
    cutoff = so["cutoff_at_snapshot"]
    cutoff = cutoff.replace(tzinfo=WIB) if cutoff.tzinfo is None else cutoff
    wo = [
        x
        for x in rows(
            c,
            "production_orders",
            plan_date=so["delivery_date"],
            schedule_version_id=so["schedule_version_id"],
        )
        if document(c, x["id"])["status"] != "cancelled"
    ]
    if wo:
        approved(c, actor, id, "production_addition")
    elif now() > cutoff:
        raise BusinessError(
            "Batas pesanan H-1 sudah lewat; hubungi penanggung jawab produksi"
        )
    need(
        not any(
            rows(c, "sales_order_components", sales_order_line_id=ln["id"])
            for ln in rows(c, "sales_order_lines", sales_order_id=id)
        ),
        "Komponen sudah dibentuk",
        409,
    )
    so_components(c, so)
    post(c, actor, id, "confirmed")
    return {"id": id, "status": "confirmed"}


def revision_proposal(c, id, p):
    document(c, id, ["confirmed"], "SO")
    so = require(c, "sales_orders", id)
    need(p.get("lines"), "Isi jumlah baru yang diusulkan")
    need(
        len({a["line_id"] for a in p["lines"]}) == len(p["lines"]),
        "Baris revisi tidak boleh duplikat",
    )
    lines = []
    total = so["total"]
    changed = False
    for a in p["lines"]:
        ln = require(c, "sales_order_lines", a["line_id"])
        need(ln["sales_order_id"] == id, "Baris bukan milik SO ini")
        qty = dec(a["quantity"], True)
        q = qty * ln["factor_snapshot"]
        need(q >= ln["qty_base"], "Pengurangan memerlukan pembatalan atau retur")
        total += money(q * ln["line_total"] / ln["qty_base"]) - ln["line_total"]
        changed = changed or q > ln["qty_base"]
        lines.append({"line_id": ln["id"], "quantity": str(qty.normalize())})
    need(changed, "Tidak ada penambahan jumlah")
    return {"lines": sorted(lines, key=lambda a: a["line_id"]), "total": str(total)}


def propose_revision(c, actor, id, p):
    from app.services import approval

    proposal = revision_proposal(c, id, p)
    need(p.get("reason"), "Alasan penambahan wajib")
    invalidate(c, id)
    q = approval.request(
        c, actor, id, "production_addition", p["reason"], amount=proposal["total"]
    )
    snapshot = {**q["rule_snapshot"], "proposal": proposal}
    update(c, "approval_requests", q["id"], rule_snapshot=snapshot)
    audit(
        c, actor, "sales_orders", id, "revision_proposed", after=proposal, document=id
    )
    return {**q, "rule_snapshot": snapshot}


def revise_so(c, actor, id, p):
    document(c, id, ["confirmed"], "SO")
    so = require(c, "sales_orders", id)
    newtotal = ZERO
    d = document(c, id)
    requests = [
        q
        for q in rows(
            c, "approval_requests", document_id=id, document_revision=d["revision"]
        )
        if q["status"] == "approved"
        and q["rule_snapshot"].get("action") == "production_addition"
        and q["rule_snapshot"].get("proposal")
    ]
    need(
        requests,
        "Ajukan usulan penambahan jumlah dan selesaikan persetujuan terlebih dahulu",
        409,
    )
    proposal = requests[-1]["rule_snapshot"]["proposal"]
    p = {**p, "lines": p.get("lines") or proposal["lines"]}
    need(
        revision_proposal(c, id, p) == proposal,
        "Jumlah berbeda dari usulan yang disetujui; ajukan ulang",
        409,
    )
    approved(c, actor, id, "production_addition", amount=proposal["total"])
    for a in p["lines"]:
        ln = require(c, "sales_order_lines", a["line_id"])
        need(ln["sales_order_id"] == id, "Baris bukan milik SO ini")
        q = dec(a["quantity"], True) * ln["factor_snapshot"]
        need(
            q >= ln["qty_base"],
            "Pengurangan setelah konfirmasi perlu pembatalan/retur terotorisasi",
        )
        delta = q - ln["qty_base"]
        amount = money(q * ln["line_total"] / ln["qty_base"])
        tax = {
            **ln["tax_snapshot"],
            "amount": str(
                money(q * dec(ln["tax_snapshot"].get("amount", 0)) / ln["qty_base"])
            ),
        }
        if delta:
            for comp in rows(c, "sales_order_components", sales_order_line_id=ln["id"]):
                demand = rows(c, "demand_lines", so_component_id=comp["id"])[0]
                update(
                    c,
                    "sales_order_components",
                    comp["id"],
                    qty_required_base=q * comp["qty_per_parent_base"],
                    version=comp["version"] + 1,
                )
                update(
                    c,
                    "demand_lines",
                    demand["id"],
                    qty_required=q * comp["qty_per_parent_base"],
                    revision=demand["revision"] + 1,
                    status="open",
                )
            update(
                c,
                "sales_order_lines",
                ln["id"],
                qty_input=q / ln["factor_snapshot"],
                qty_base=q,
                line_total=amount,
                tax_snapshot=tax,
            )
    for ln in rows(c, "sales_order_lines", sales_order_id=id):
        newtotal += ln["line_total"]
    tax_total = sum(
        (
            dec(a["tax_snapshot"].get("amount", 0))
            for a in rows(c, "sales_order_lines", sales_order_id=id)
        ),
        ZERO,
    )
    update(
        c,
        "sales_orders",
        id,
        subtotal=newtotal - tax_total,
        tax_total=tax_total,
        total=newtotal,
    )
    invalidate(c, id)
    return require(c, "sales_orders", id)


def cancel_so(c, actor, id, p):
    document(c, id, ["draft", "confirmed"], "SO")
    so = require(c, "sales_orders", id)
    need(
        not rows(c, "deliveries", sales_order_id=id),
        "SO sudah delivery; gunakan retur, bukan pembatalan",
    )
    approved(c, actor, id, "cancellation")
    demands = rows(c, "demand_lines", source_document_id=id)
    for demand in demands:
        for alloc in rows(c, "wo_demand_allocations", demand_id=demand["id"]):
            wo = document(c, alloc["production_order_id"])
            need(
                wo["status"] not in ("started",),
                "WO sedang berjalan; selesaikan dan tinjau hasil sebelum membatalkan SO",
                409,
            )
            update(
                c,
                "wo_demand_allocations",
                alloc["id"],
                qty_cancelled=max(ZERO, alloc["qty_planned"] - alloc["qty_fulfilled"]),
            )
        for res in rows(c, "stock_reservations", demand_id=demand["id"]):
            remain = res["qty_reserved"] - res["qty_consumed"] - res["qty_released"]
            if remain:
                b = balance(c, res["product_id"], res["warehouse_id"])
                update(
                    c,
                    "stock_balances",
                    b["id"],
                    reserved_quantity=b["reserved_quantity"] - remain,
                )
                update(
                    c,
                    "stock_reservations",
                    res["id"],
                    qty_released=res["qty_released"] + remain,
                    status="released",
                )
        update(c, "demand_lines", demand["id"], status="cancelled")
    affected = {
        a["production_order_id"]
        for demand in demands
        for a in rows(c, "wo_demand_allocations", demand_id=demand["id"])
    }
    for woid in affected:
        if document(c, woid)["status"] == "draft":
            wo = require(c, "production_orders", woid)
            newqty = sum(
                (
                    a["qty_planned"] - a["qty_cancelled"]
                    for a in rows(c, "wo_demand_allocations", production_order_id=woid)
                ),
                ZERO,
            )
            for material in rows(c, "production_materials", production_order_id=woid):
                update(
                    c,
                    "production_materials",
                    material["id"],
                    planned_qty_base=material["planned_qty_base"]
                    * newqty
                    / wo["planned_qty_base"],
                )
            update(c, "production_orders", woid, planned_qty_base=newqty)
            if not newqty:
                update(c, "documents", woid, status="cancelled")
    for po in rows(c, "purchase_orders", sales_order_id=id):
        if document(c, po["id"])["status"] in ("draft", "confirmed"):
            update(c, "documents", po["id"], status="cancelled")
    post(c, actor, id, "cancelled")
    return {
        "id": id,
        "message": "SO dibatalkan; DP masih tercatat sampai refund. Barang supplier yang sudah diterima tetap owned; transfer ke toko melalui modul transfer.",
    }


def delivery(c, actor, id, p):
    document(c, id, ["confirmed", "partial", "delivered"], "SO")
    so = require(c, "sales_orders", id)
    dd = doc(c, actor, "DELIVERY", {k: v for k, v in p.items() if k != "id"})
    dl = insert(
        c,
        "deliveries",
        dict(
            id=dd["id"],
            sales_order_id=id,
            warehouse_id=so["fulfillment_warehouse_id"],
            delivery_at=now(),
            recipient_name=p.get("recipient_name"),
        ),
    )
    need(p.get("lines"), "Isi komponen yang dikirim")
    totalcost = ZERO
    for a in p["lines"]:
        comp = require(c, "sales_order_components", a["component_id"])
        ln = require(c, "sales_order_lines", comp["sales_order_line_id"])
        need(ln["sales_order_id"] == id, "Komponen bukan milik SO ini")
        sent = sum(
            (
                l["qty_base"]
                for l in rows(c, "delivery_lines", so_component_id=comp["id"])
            ),
            ZERO,
        )
        q = dec(a["quantity"], True)
        need(
            sent + q <= comp["qty_required_base"],
            "Pengiriman melebihi kebutuhan tersisa",
        )
        demand = rows(c, "demand_lines", so_component_id=comp["id"])[0]
        from app.services.inventory import consume_reservation

        consume_reservation(c, demand["id"], so["fulfillment_warehouse_id"], q)
        mv = move(
            c,
            dd["id"],
            comp["id"],
            comp["product_id"],
            so["fulfillment_warehouse_id"],
            -q,
            "sales_delivery",
        )
        totalcost += q * mv["unit_cost"]
        insert(
            c,
            "delivery_lines",
            dict(
                delivery_id=dd["id"],
                so_component_id=comp["id"],
                reservation_id=None,
                qty_base=q,
                unit_cost_snapshot=mv["unit_cost"],
                stock_movement_id=mv["id"],
            ),
        )
    journal(
        c, dd["id"], "delivery_cost", [("5000", totalcost, 0), ("1200", 0, totalcost)]
    )
    post(c, actor, dd["id"])
    comps = [
        a
        for ln in rows(c, "sales_order_lines", sales_order_id=id)
        for a in rows(c, "sales_order_components", sales_order_line_id=ln["id"])
    ]
    done = all(
        sum(
            (
                x["qty_base"]
                for x in rows(c, "delivery_lines", so_component_id=co["id"])
            ),
            ZERO,
        )
        >= co["qty_required_base"]
        for co in comps
    )
    update(c, "documents", id, status="delivered" if done else "partial")
    return dl


def invoice(c, actor, id, p):
    document(c, id, ["partial", "delivered"], "SO")
    so = require(c, "sales_orders", id)
    d = doc(c, actor, "SALES_INVOICE", {k: v for k, v in p.items() if k != "id"})
    prepared = []
    total = ZERO
    for ln in rows(c, "sales_order_lines", sales_order_id=id):
        comps = rows(c, "sales_order_components", sales_order_line_id=ln["id"])
        delivered = min(
            (
                sum(
                    (
                        r["qty_base"]
                        for r in rows(c, "delivery_lines", so_component_id=co["id"])
                    ),
                    ZERO,
                )
                / co["qty_per_parent_base"]
                for co in comps
            ),
            default=ZERO,
        )
        billed = sum(
            (
                r["qty_parent_base"]
                for r in rows(c, "sales_invoice_lines", so_line_id=ln["id"])
            ),
            ZERO,
        )
        q = delivered - billed
        if q > 0:
            price = ln["unit_price_input"] / ln["factor_snapshot"]
            previous_lines = rows(c, "sales_invoice_lines", so_line_id=ln["id"])
            amount = money((billed + q) * ln["line_total"] / ln["qty_base"]) - sum(
                (il["line_total"] for il in previous_lines), ZERO
            )
            total += amount
            tax = {
                **ln["tax_snapshot"],
                "amount": str(
                    money(
                        (billed + q)
                        * dec(ln["tax_snapshot"].get("amount", 0))
                        / ln["qty_base"]
                    )
                    - sum(
                        (
                            dec(il["tax_snapshot"].get("amount", 0))
                            for il in previous_lines
                        ),
                        ZERO,
                    )
                ),
            }
            prepared.append(
                dict(
                    invoice_id=d["id"],
                    so_line_id=ln["id"],
                    qty_parent_base=q,
                    unit_price_base=price,
                    discount_amount=0,
                    tax_snapshot=tax,
                    line_total=amount,
                )
            )
    need(prepared, "Belum ada pengiriman yang belum ditagih")
    tax_total = sum((dec(a["tax_snapshot"]["amount"]) for a in prepared), ZERO)
    insert(
        c,
        "sales_invoices",
        dict(
            id=d["id"],
            sales_order_id=id,
            customer_id=so["customer_id"],
            invoice_date=d["business_date"],
            due_date=p.get("due_date"),
            subtotal=total - tax_total,
            discount_total=0,
            tax_total=tax_total,
            total=total,
        ),
    )
    for ln in prepared:
        insert(c, "sales_invoice_lines", ln)
    tax_entries = [
        (a["tax_snapshot"]["output_account_code"], 0, dec(a["tax_snapshot"]["amount"]))
        for a in prepared
        if dec(a["tax_snapshot"]["amount"])
    ]
    journal(
        c,
        d["id"],
        "sales_invoice",
        [("1300", total, 0), ("4000", 0, total - tax_total)] + tax_entries,
    )
    post(c, actor, d["id"])
    return d
