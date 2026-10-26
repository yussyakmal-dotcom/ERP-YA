from app.core import *
from app.services.approval import approved
from app.services.inventory import move


def create_po(c, actor, p):
    d = doc(c, actor, "PO", p)
    require(c, "suppliers", p["supplier_id"])
    w = require(c, "warehouses", p["receiving_warehouse_id"])
    so = p.get("sales_order_id")
    if so:
        require(c, "sales_orders", so)
        need(w["kind"] == "packing", "PO khusus SO harus diterima di packing")
    need(p.get("lines"), "PO harus memiliki barang")
    prepared = []
    total = ZERO
    taxid = setting(c, "tax_policy", {}).get("purchase_tax_id")
    tax = require(c, "taxes", taxid) if taxid else None
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        need(product["is_purchasable"], "Produk tidak dapat dibeli")
        q = dec(a["quantity"], True)
        price = dec(a["unit_price"])
        netprice = price
        ts = {}
        if tax:
            need(
                tax["effective_from"] <= d["business_date"]
                and (
                    not tax["effective_to"] or d["business_date"] <= tax["effective_to"]
                ),
                "Pajak pembelian tidak berlaku",
            )
            need(tax["input_account_id"], "Akun pajak masukan belum diisi")
            rate = dec(tax["rate"])
            need(rate <= 1, "Tarif pajak harus pecahan 0..1")
            netprice = price / (1 + rate) if tax["price_inclusive"] else price
            ts = {
                "tax_id": tax["id"],
                "rate": str(rate),
                "inclusive": tax["price_inclusive"],
                "input_account_code": require(
                    c, "chart_of_accounts", tax["input_account_id"]
                )["code"],
            }
            total += money(q * netprice * (1 + rate))
        else:
            total += q * price
        prepared.append(
            dict(
                purchase_order_id=d["id"],
                product_id=product["id"],
                demand_id=a.get("demand_id"),
                qty_input=q,
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_ordered_base=q * u["factor_to_base"],
                unit_price_input=price,
                unit_cost_base=netprice / u["factor_to_base"],
                tax_snapshot=ts,
            )
        )
    insert(
        c,
        "purchase_orders",
        dict(
            id=d["id"],
            supplier_id=p["supplier_id"],
            receiving_warehouse_id=w["id"],
            sales_order_id=so,
            purpose="sales_order" if so else "regular",
            order_date=d["business_date"],
            expected_date=p.get("expected_date"),
            original_total=total,
            actual_total=None,
        ),
    )
    for a in prepared:
        insert(c, "purchase_order_lines", a)
    return d


def confirm_po(c, actor, id):
    document(c, id, ["draft"], "PO")
    approved(c, actor, id, "purchase")
    post(c, actor, id, "confirmed")
    return {"id": id, "status": "confirmed"}


def receive(c, actor, id, p):
    document(c, id, ["confirmed"], "PO")
    po = require(c, "purchase_orders", id)
    need(
        not rows(c, "goods_receipts", purchase_order_id=id),
        "PO sudah menerima satu penerimaan final",
        409,
    )
    lines = rows(c, "purchase_order_lines", purchase_order_id=id)
    actual = {a["line_id"]: a for a in p["lines"]}
    need(
        set(actual) == {a["id"] for a in lines} and len(actual) == len(p["lines"]),
        "Isi seluruh baris PO tepat satu kali, termasuk jumlah nol",
    )
    dd = doc(c, actor, "GOODS_RECEIPT", {k: v for k, v in p.items() if k != "id"})
    gr = insert(
        c,
        "goods_receipts",
        dict(
            id=dd["id"],
            purchase_order_id=id,
            warehouse_id=po["receiving_warehouse_id"],
            receipt_at=now(),
            supplier_reference=p.get("supplier_reference"),
        ),
    )
    total = ZERO
    quantity = ZERO
    for ln in lines:
        a = actual[ln["id"]]
        q = dec(a["quantity"]) * ln["factor_snapshot"]
        need(q <= ln["qty_ordered_base"], "Penerimaan melebihi pesanan")
        short = ln["qty_ordered_base"] - q
        need(not short or a.get("reason"), "Alasan kekurangan / nol wajib diisi")
        r = insert(
            c,
            "goods_receipt_lines",
            dict(
                receipt_id=gr["id"],
                po_line_id=ln["id"],
                qty_received_base=q,
                qty_closed_short=short,
                unit_cost_snapshot=ln["unit_cost_base"],
                variance_reason=a.get("reason"),
            ),
        )
        if q:
            move(
                c,
                dd["id"],
                r["id"],
                ln["product_id"],
                gr["warehouse_id"],
                q,
                "goods_receipt",
                ln["unit_cost_base"],
            )
        total += q * ln["unit_cost_base"]
        quantity += q
    need(quantity > 0, "Semua jumlah nol: gunakan catatan penolakan, bukan penerimaan")
    journal(c, dd["id"], "goods_receipt", [("1200", total, 0), ("2120", 0, total)])
    post(c, actor, dd["id"])
    post(c, actor, id, "received")
    update(c, "purchase_orders", id, actual_total=total)
    return {**gr, "total": total, "po_status": "received"}


def reject_arrival(c, actor, id, p):
    document(c, id, ["confirmed", "received"], "PO")
    need(p.get("reason") and p.get("items"), "Alasan dan rincian barang wajib diisi")
    r = insert(
        c,
        "supplier_arrival_rejections",
        dict(
            purchase_order_id=id,
            arrival_at=now(),
            items=p["items"],
            reason=p["reason"],
            recorded_by=actor,
        ),
    )
    audit(
        c,
        actor,
        "supplier_arrival_rejections",
        r["id"],
        "rejected_arrival",
        after=r,
        document=id,
    )
    return r


def invoice(c, actor, p):
    gr = require(c, "goods_receipts", p["goods_receipt_id"])
    po = require(c, "purchase_orders", gr["purchase_order_id"])
    d = doc(c, actor, "PURCHASE_INVOICE", p)
    prepared = []
    total = ZERO
    tax_total = ZERO
    tax_entries = []
    need(
        len({a["receipt_line_id"] for a in p["lines"]}) == len(p["lines"]),
        "Baris faktur tidak boleh duplikat",
    )
    for a in p["lines"]:
        ln = require(c, "goods_receipt_lines", a["receipt_line_id"])
        need(ln["receipt_id"] == gr["id"], "Baris bukan dari penerimaan ini")
        qty = dec(a["quantity"], True)
        price = dec(a.get("unit_price", ln["unit_cost_snapshot"]))
        used = sum(
            (
                x["qty_base"]
                for x in rows(c, "purchase_invoice_lines", receipt_line_id=ln["id"])
            ),
            ZERO,
        )
        returned = sum(
            (
                x["qty_base"]
                for x in rows(c, "return_lines", goods_receipt_line_id=ln["id"])
                if document(c, x["return_id"])["status"] == "posted"
            ),
            ZERO,
        )
        need(
            qty + used <= ln["qty_received_base"] - returned,
            "Tagihan melebihi penerimaan bersih",
        )
        need(
            price == ln["unit_cost_snapshot"],
            "Selisih harga perlu dokumen koreksi terotorisasi; gunakan harga penerimaan untuk faktur ini",
        )
        amount = money(qty * price)
        total += amount
        ts = dict(require(c, "purchase_order_lines", ln["po_line_id"])["tax_snapshot"])
        ta = money(amount * dec(ts.get("rate", 0)))
        tax_total += ta
        if ta:
            tax_entries.append((ts["input_account_code"], ta, 0))
        ts["amount"] = str(ta)
        prepared.append(
            dict(
                invoice_id=d["id"],
                receipt_line_id=ln["id"],
                qty_base=qty,
                unit_price_base=price,
                net_amount=amount,
                tax_snapshot=ts,
            )
        )
    need(prepared, "Isi minimal satu baris faktur")
    insert(
        c,
        "purchase_invoices",
        dict(
            id=d["id"],
            supplier_id=po["supplier_id"],
            goods_receipt_id=gr["id"],
            supplier_invoice_no=p["supplier_invoice_no"],
            invoice_date=d["business_date"],
            due_date=p.get("due_date"),
            subtotal=total,
            tax_total=tax_total,
            total=total + tax_total,
        ),
    )
    for a in prepared:
        insert(c, "purchase_invoice_lines", a)
    journal(
        c,
        d["id"],
        "purchase_invoice",
        [("2120", total, 0), ("2100", 0, total + tax_total)] + tax_entries,
    )
    post(c, actor, d["id"])
    return d


def settlement(c, actor, p):
    d = doc(c, actor, "CONSIGNMENT_SETTLEMENT", p)
    supplier = p["supplier_id"]
    lines = []
    total = ZERO
    start = dt.date.fromisoformat(p["period_from"])
    end = dt.date.fromisoformat(p["period_to"])
    need(start <= end, "Rentang periode tidak valid")
    for sale in rows(c, "consignment_sales", supplier_id=supplier):
        ln = require(c, "pos_sale_lines", sale["pos_sale_line_id"])
        sd = document(c, ln["pos_sale_id"])
        if not start <= sd["business_date"] <= end:
            continue
        previous = rows(
            c, "consignment_settlement_lines", consignment_sale_id=sale["id"]
        )
        if not any(r["return_line_id"] is None for r in previous):
            amount = money(sale["qty_base"] * sale["unit_cost_snapshot"])
            lines.append(
                dict(
                    settlement_id=d["id"],
                    consignment_sale_id=sale["id"],
                    return_line_id=None,
                    qty_signed=sale["qty_base"],
                    amount_signed=amount,
                )
            )
            total += amount
        for ret in rows(c, "return_lines", pos_sale_line_id=ln["id"]):
            if document(c, ret["return_id"])["status"] != "posted":
                continue
            if not any(r["return_line_id"] == ret["id"] for r in previous):
                amount = -money(ret["qty_base"] * sale["unit_cost_snapshot"])
                lines.append(
                    dict(
                        settlement_id=d["id"],
                        consignment_sale_id=sale["id"],
                        return_line_id=ret["id"],
                        qty_signed=-ret["qty_base"],
                        amount_signed=amount,
                    )
                )
                total += amount
    need(lines, "Tidak ada penjualan/retur titipan yang belum diselesaikan")
    insert(
        c,
        "consignment_settlements",
        dict(
            id=d["id"],
            supplier_id=supplier,
            period_from=start,
            period_to=end,
            due_date=p.get("due_date"),
            total=total,
        ),
    )
    for ln in lines:
        insert(c, "consignment_settlement_lines", ln)
    # Recognition already occurred at sale/return; settlement is not a second expense.
    post(c, actor, d["id"])
    return {**d, "total": total}
