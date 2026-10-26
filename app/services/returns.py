from app.core import *
from app.services.approval import approved
from app.services.inventory import move


def create(c, actor, p, offline_authorized=False):
    source = document(c, p["source_document_id"])
    channel = p.get("channel", "backoffice")
    side = p["side"]
    need(side in ("customer", "supplier"), "Jenis retur tidak valid")
    need(p.get("reason"), "Alasan retur wajib")
    need(
        (side == "supplier" and source["document_type"] == "GOODS_RECEIPT")
        or (side == "customer" and source["document_type"] in ("POS_SALE", "DELIVERY")),
        "Jenis retur harus sesuai dokumen asal",
    )
    p = dict(p)
    if side == "supplier":
        receipt = require(c, "goods_receipts", source["id"])
        p["supplier_id"] = require(c, "purchase_orders", receipt["purchase_order_id"])[
            "supplier_id"
        ]
        p["customer_id"] = None
    else:
        p["supplier_id"] = None
        p["customer_id"] = (
            require(c, "pos_sales", source["id"])["customer_id"]
            if source["document_type"] == "POS_SALE"
            else require(
                c,
                "sales_orders",
                require(c, "deliveries", source["id"])["sales_order_id"],
            )["customer_id"]
        )
    if channel == "pos":
        need(
            source["document_type"] == "POS_SALE",
            "POS hanya memproses retur penjualan toko",
        )
    dd = doc(c, actor, "RETURN", p)
    # Prepare and approve before the first physical/financial posting.
    insert(
        c,
        "returns",
        dict(
            id=dd["id"],
            side=side,
            channel=channel,
            source_document_id=source["id"],
            supplier_id=p.get("supplier_id"),
            customer_id=p.get("customer_id"),
            warehouse_id=p["warehouse_id"],
            terminal_id=p.get("terminal_id"),
            reason=p["reason"],
        ),
    )
    total = ZERO
    inventory_total = ZERO
    consign_total = ZERO
    prepared = []
    need(p.get("lines"), "Isi baris retur")
    need(
        len({a["line_id"] for a in p["lines"]}) == len(p["lines"]),
        "Baris retur tidak boleh duplikat",
    )
    for a in p["lines"]:
        q = dec(a["quantity"], True)
        condition = a.get("condition", "good")
        need(condition in ("good", "damaged"), "Kondisi tidak valid")
        pos_id = delivery_id = receipt_id = None
        agreement = None
        if source["document_type"] == "POS_SALE":
            ln = require(c, "pos_sale_lines", a["line_id"])
            need(ln["pos_sale_id"] == source["id"], "Baris struk tidak cocok")
            pos_id = ln["id"]
            original = ln["qty_base"]
            cost = ln["cost_snapshot"]
            basis = money(q * ln["line_total"] / original)
            pid = ln["product_id"]
            used = rows(c, "return_lines", pos_sale_line_id=ln["id"])
            agreement = ln["agreement_id"]
        elif source["document_type"] == "DELIVERY":
            ln = require(c, "delivery_lines", a["line_id"])
            need(ln["delivery_id"] == source["id"], "Baris delivery tidak cocok")
            delivery_id = ln["id"]
            original = ln["qty_base"]
            cost = ln["unit_cost_snapshot"]
            cp = require(c, "sales_order_components", ln["so_component_id"])
            sol = require(c, "sales_order_lines", cp["sales_order_line_id"])
            pid = cp["product_id"]
            used = rows(c, "return_lines", delivery_line_id=ln["id"])
            comps = rows(c, "sales_order_components", sales_order_line_id=sol["id"])
            delivered = min(
                (
                    sum(
                        (
                            dl["qty_base"]
                            for dl in rows(
                                c, "delivery_lines", so_component_id=co["id"]
                            )
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
                    il["qty_parent_base"]
                    for il in rows(c, "sales_invoice_lines", so_line_id=sol["id"])
                ),
                ZERO,
            )
            need(
                billed >= delivered and billed > 0,
                "Terbitkan invoice untuk pengiriman SO sebelum memproses kredit retur",
            )
            # Package value is allocated by component count, not recognized a second time.
            allcomps = rows(c, "sales_order_components", sales_order_line_id=sol["id"])
            den = sum((x["qty_per_parent_base"] for x in allcomps), ZERO)
            basis = money(q * sol["line_total"] / sol["qty_base"] / den)
        else:
            need(
                source["document_type"] == "GOODS_RECEIPT" and side == "supplier",
                "Dokumen asal retur tidak valid",
            )
            ln = require(c, "goods_receipt_lines", a["line_id"])
            need(ln["receipt_id"] == source["id"], "Baris penerimaan tidak cocok")
            receipt_id = ln["id"]
            pol = require(c, "purchase_order_lines", ln["po_line_id"])
            pid = pol["product_id"]
            original = ln["qty_received_base"]
            cost = ln["unit_cost_snapshot"]
            basis = money(q * cost)
            used = rows(c, "return_lines", goods_receipt_line_id=ln["id"])
        used = [r for r in used if document(c, r["return_id"])["status"] == "posted"]
        need(
            q + sum((r["qty_base"] for r in used), ZERO) <= original,
            "Retur melebihi sisa jumlah transaksi asal",
        )
        total += basis
        prepared.append(
            dict(
                return_id=dd["id"],
                pos_sale_line_id=pos_id,
                delivery_line_id=delivery_id,
                goods_receipt_line_id=receipt_id,
                product_id=pid,
                qty_base=q,
                condition=condition,
                stock_disposition=(
                    "supplier"
                    if side == "supplier"
                    else (
                        "manual_consignment"
                        if agreement and condition == "good"
                        else "stock" if condition == "good" else "loss"
                    )
                ),
                original_unit_cost=cost,
                refund_basis_amount=basis,
            )
        )
    for a in prepared:
        insert(c, "return_lines", a)
    # Ordinary backoffice return is a draft requiring authorization at post_return.
    if channel == "pos" and offline_authorized:
        return post_return(c, actor, dd["id"], True)
    return dd


def post_return(c, actor, id, offline_authorized=False):
    document(c, id, ["draft"], "RETURN")
    r = require(c, "returns", id)
    if not offline_authorized:
        approved(c, actor, id, "return")
    total = ZERO
    customer_stock = ZERO
    supplier_stock = ZERO
    consign = ZERO
    tax_total = ZERO
    tax_entries = []
    unbilled_return = ZERO
    pos_refunds = {}
    for a in rows(c, "return_lines", return_id=id):
        q = a["qty_base"]
        cost = a["original_unit_cost"]
        source_key = (
            "pos_sale_line_id"
            if a["pos_sale_line_id"]
            else (
                "delivery_line_id" if a["delivery_line_id"] else "goods_receipt_line_id"
            )
        )
        source_table = {
            "pos_sale_line_id": "pos_sale_lines",
            "delivery_line_id": "delivery_lines",
            "goods_receipt_line_id": "goods_receipt_lines",
        }[source_key]
        source = require(c, source_table, a[source_key])
        original = source.get("qty_base", source.get("qty_received_base"))
        previous = sum(
            (
                r["qty_base"]
                for r in rows(c, "return_lines", **{source_key: a[source_key]})
                if r["return_id"] != id
                and document(c, r["return_id"])["status"] == "posted"
            ),
            ZERO,
        )
        need(q + previous <= original, "Retur melebihi sisa jumlah transaksi asal", 409)
        if source_key == "goods_receipt_line_id":
            billed = sum(
                (
                    ln["qty_base"]
                    for ln in rows(
                        c, "purchase_invoice_lines", receipt_line_id=source["id"]
                    )
                ),
                ZERO,
            )
            unbilled = max(ZERO, source["qty_received_base"] - billed - previous)
            no_claim = min(q, unbilled)
            unbilled_return += no_claim * cost
            pol = require(c, "purchase_order_lines", source["po_line_id"])
            ptax = pol["tax_snapshot"]
            tax_claim = money((q - no_claim) * cost * dec(ptax.get("rate", 0)))
            if tax_claim:
                tax_entries.append((ptax["input_account_code"], 0, tax_claim))
            update(
                c,
                "return_lines",
                a["id"],
                refund_basis_amount=(q - no_claim) * cost + tax_claim,
            )
            a["refund_basis_amount"] = (q - no_claim) * cost + tax_claim
        if a["pos_sale_line_id"]:
            original = require(c, "pos_sale_lines", a["pos_sale_line_id"])
            tax = original["tax_snapshot"]
            ta = money(
                (previous + q) * dec(tax.get("amount", 0)) / original["qty_base"]
            ) - money(previous * dec(tax.get("amount", 0)) / original["qty_base"])
            a["refund_basis_amount"] = money(
                (previous + q) * original["line_total"] / original["qty_base"]
            ) - money(previous * original["line_total"] / original["qty_base"])
            update(
                c, "return_lines", a["id"], refund_basis_amount=a["refund_basis_amount"]
            )
            pos_refunds[original["pos_sale_id"]] = (
                pos_refunds.get(original["pos_sale_id"], ZERO)
                + a["refund_basis_amount"]
            )
        elif a["delivery_line_id"]:
            dl = require(c, "delivery_lines", a["delivery_line_id"])
            co = require(c, "sales_order_components", dl["so_component_id"])
            sl = require(c, "sales_order_lines", co["sales_order_line_id"])
            tax = sl["tax_snapshot"]
            den = sum(
                (
                    x["qty_per_parent_base"]
                    for x in rows(
                        c, "sales_order_components", sales_order_line_id=sl["id"]
                    )
                ),
                ZERO,
            )
            ta = money(q * dec(tax.get("amount", 0)) / sl["qty_base"] / den)
        else:
            tax = {}
            ta = ZERO
        total += a["refund_basis_amount"]
        if ta:
            tax_total += ta
            tax_entries.append((tax["output_account_code"], ta, 0))
        if a["stock_disposition"] == "supplier":
            move(
                c,
                id,
                a["id"],
                a["product_id"],
                r["warehouse_id"],
                -q,
                "supplier_return",
                cost,
            )
            supplier_stock += q * cost
        elif a["stock_disposition"] == "stock":
            move(
                c,
                id,
                a["id"],
                a["product_id"],
                r["warehouse_id"],
                q,
                "customer_return",
                cost,
            )
            customer_stock += q * cost
        elif a["stock_disposition"] == "manual_consignment":
            # Reverse the paired recognition, leaving no owned stock in the system.
            move(
                c,
                id,
                a["id"] + "-in",
                a["product_id"],
                r["warehouse_id"],
                q,
                "consignment_return_in",
                cost,
            )
            move(
                c,
                id,
                a["id"] + "-out",
                a["product_id"],
                r["warehouse_id"],
                -q,
                "consignment_return_out",
                cost,
                True,
                "Pembalikan titipan",
            )
            consign += q * cost
    cd = doc(c, actor, "CREDIT_NOTE")
    credit = insert(
        c,
        "credit_notes",
        dict(
            id=cd["id"],
            return_id=id,
            source_document_id=r["source_document_id"],
            direction="receivable" if r["side"] == "supplier" else "payable",
            customer_id=r["customer_id"],
            supplier_id=r["supplier_id"],
            amount=total,
            reason=r["reason"],
        ),
    )
    entries = (
        [("2150", total, 0), ("2120", unbilled_return, 0), ("1200", 0, supplier_stock)]
        + tax_entries
        if r["side"] == "supplier"
        else [
            ("4000", total - tax_total, 0),
            ("2140", 0, total),
            ("1200", customer_stock, 0),
            ("5000", 0, customer_stock),
            ("2100", consign, 0),
            ("5000", 0, consign),
        ]
        + tax_entries
    )
    from app.services import commerce

    for saleid, amount in pos_refunds.items():
        commerce.reverse_earn(c, saleid, id, amount)
    journal(c, id, "return", entries)
    post(c, actor, id)
    post(c, actor, cd["id"])
    return {"id": id, "credit_note_id": credit["id"], "credit_amount": total}
