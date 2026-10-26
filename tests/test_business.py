import datetime as dt
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.core import BusinessError, document, doc, now, WIB, post
from app.db import rows, get, update, insert, clean, metadata, MODEL
from app.services import (
    purchasing as po,
    inventory as inv,
    production as prod,
    sales,
    finance as fin,
    pos,
    master,
    approval,
    sync,
)


def make_po(e, qty=10):
    d = e.call(
        po.create_po,
        dict(
            supplier_id=e.supplier,
            receiving_warehouse_id=e.wh["CDC"],
            lines=[
                dict(
                    product_id=e.flour,
                    uom_id=e.uoms["dus"],
                    quantity=qty,
                    unit_price=100000,
                )
            ],
        ),
    )
    e.approve(d["id"], "purchase")
    e.call(po.confirm_po, d["id"])
    return d


def receive_po(e, d, qty=5):
    with e.db.read() as c:
        ln = rows(c, "purchase_order_lines", purchase_order_id=d["id"])[0]
    return e.call(
        po.receive,
        d["id"],
        dict(
            lines=[dict(line_id=ln["id"], quantity=qty, reason="Kurang dari supplier")]
        ),
    )


def so(e, qty=100, product=None, price=25000):
    date = now().astimezone(WIB).date() + dt.timedelta(days=1)
    return e.call(
        sales.create_so,
        dict(
            outlet_id=e.outlet,
            customer_id=e.customer,
            fulfillment_warehouse_id=e.wh["PACK"],
            delivery_date=str(date),
            schedule_version_id=e.sv,
            price_list_id=e.price,
            lines=[
                dict(product_id=product or e.package, quantity=qty, unit_price=price)
            ],
        ),
    )


def sale_params(e, shift, qty=2, source="owned", agreement=None, price=16000):
    return dict(
        shift_id=shift["id"],
        price_list_id=e.price,
        lines=[
            dict(
                product_id=e.bread,
                quantity=qty,
                stock_source=source,
                agreement_id=agreement,
                negative_reason="Perkiraan stok kasir belum terkini",
            )
        ],
        tenders=[
            dict(
                method_id=e.cashmethod,
                cash_bank_account_id=e.cash,
                amount_applied=price,
                amount_received=price,
            )
        ],
    )


def open_shift(e):
    return e.call(
        pos.open_shift,
        dict(terminal_id=e.terminal["terminal"]["id"], opening_cash=200000),
    )


def test_bootstrap_restart_and_schema(env):
    from app.db import Database

    e = env
    again = Database(e.db.engine.url.render_as_string(hide_password=False))
    assert len(MODEL) == 104
    with again.read() as c:
        assert len(rows(c, "warehouses")) == 29
        assert len(rows(c, "users")) == 2
    with pytest.raises(BusinessError), e.db.write() as c:
        __import__("app.core", fromlist=["bootstrap"]).bootstrap(
            c, "another", "not-short-password"
        )


def test_po_once_receive_closes_short_and_reject_late(env):
    e = env
    d = make_po(e)
    r = receive_po(e, d)
    with e.db.read() as c:
        assert document(c, d["id"])["status"] == "received"
        ln = rows(c, "goods_receipt_lines", receipt_id=r["id"])[0]
        assert ln["qty_received_base"] == 50 and ln["qty_closed_short"] == 50
        assert inv.balance(c, e.flour, e.wh["CDC"])["quantity"] == 50
    with pytest.raises(BusinessError):
        receive_po(e, d)
    e.call(
        po.reject_arrival,
        d["id"],
        dict(reason="PO sudah diterima final", items=[{"quantity": 5, "uom": "dus"}]),
    )
    with e.db.read() as c:
        assert len(rows(c, "goods_receipts")) == 1
        assert inv.balance(c, e.flour, e.wh["CDC"])["quantity"] == 50


def test_po_concurrent_receipt_has_one_commit(env):
    e = env
    d = make_po(e)

    def run():
        try:
            receive_po(e, d)
            return True
        except BusinessError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(), range(2))) == [False, True]


def test_po_all_zero_rolls_back(env):
    e = env
    d = make_po(e)
    with pytest.raises(BusinessError):
        receive_po(e, d, 0)
    with e.db.read() as c:
        assert not rows(c, "goods_receipts")
        assert document(c, d["id"])["status"] == "confirmed"


def test_transfer_receives_98_then_2(env):
    e = env
    e.stock(e.bread, e.wh["PACK"], 100, 3000)
    d = e.call(
        inv.transfer_create,
        dict(
            from_warehouse_id=e.wh["PACK"],
            to_warehouse_id=e.wh["T01"],
            lines=[dict(product_id=e.bread, quantity=100)],
        ),
    )
    e.call(inv.dispatch, d["id"])
    with e.db.read() as c:
        ln = rows(c, "transfer_lines", transfer_id=d["id"])[0]
    e.call(
        inv.receive_transfer, d["id"], dict(lines=[dict(line_id=ln["id"], quantity=98)])
    )
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 98
        assert inv.balance(c, e.bread, e.wh["TRANSIT"])["quantity"] == 2
        assert rows(c, "transfer_discrepancies")[0]["status"] == "open"
    e.call(
        inv.receive_transfer, d["id"], dict(lines=[dict(line_id=ln["id"], quantity=2)])
    )
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 100
        assert rows(c, "transfer_discrepancies")[0]["status"] == "closed"


@pytest.mark.parametrize(
    "resolution", ["lost", "damaged", "dispatch_error", "returned", "in_transit"]
)
def test_transit_resolution_disposition(env, resolution):
    e = env
    e.stock(e.bread, e.wh["PACK"], 100, 3000)
    d = e.call(
        inv.transfer_create,
        dict(
            from_warehouse_id=e.wh["PACK"],
            to_warehouse_id=e.wh["T01"],
            lines=[dict(product_id=e.bread, quantity=100)],
        ),
    )
    e.call(inv.dispatch, d["id"])
    with e.db.read() as c:
        ln = rows(c, "transfer_lines", transfer_id=d["id"])[0]
    e.call(
        inv.receive_transfer, d["id"], dict(lines=[dict(line_id=ln["id"], quantity=98)])
    )
    with e.db.read() as c:
        case = rows(c, "transfer_discrepancies")[0]
    if resolution != "in_transit":
        e.approve(d["id"], "transit_resolution")
    e.call(
        inv.resolve,
        case["id"],
        dict(
            resolution_type=resolution,
            quantity=2,
            evidence="Bukti pemeriksaan",
            confirmed_at_source=True,
        ),
    )
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["TRANSIT"])["quantity"] == (
            2 if resolution == "in_transit" else 0
        )
        assert inv.balance(c, e.bread, e.wh["PACK"])["quantity"] == (
            2 if resolution in ("returned", "dispatch_error") else 0
        )


def test_so_package_h1_and_snapshot(env):
    e = env
    d = so(e)
    with e.db.write() as c:
        sv = master.schedule(
            c,
            e.actor,
            dict(
                schedule_id=rows(c, "production_schedules")[0]["id"],
                cutoff_time="22:00",
                delivery_time="09:00",
                effective_from=str(now().date()),
            ),
        )
        assert get(c, "sales_orders", d["id"])["schedule_version_id"] != sv["id"]
    e.call(sales.confirm_so, d["id"])
    with e.db.read() as c:
        lines = rows(c, "sales_order_lines", sales_order_id=d["id"])
        assert len(lines) == 1
        assert lines[0]["line_total"] == 2500000
        assert (
            len(rows(c, "sales_order_components", sales_order_line_id=lines[0]["id"]))
            == 2
        )
    with pytest.raises(BusinessError):
        e.call(
            sales.create_so,
            dict(
                outlet_id=e.outlet,
                customer_id=e.customer,
                fulfillment_warehouse_id=e.wh["PACK"],
                delivery_date=str(now().astimezone(WIB).date()),
                schedule_version_id=e.sv,
                price_list_id=e.price,
                lines=[dict(product_id=e.bread, quantity=1, unit_price=1)],
            ),
        )


def prepare_wo(e, qty=100):
    d = so(e, qty, e.bread, 8000)
    e.call(sales.confirm_so, d["id"])
    with e.db.read() as c:
        ds = rows(c, "demand_lines", source_document_id=d["id"])
    wo = e.call(prod.plan, {"demand_ids": [ds[0]["id"]]})[0]
    return d, wo


def test_production_material_returns_white_zero_and_snapshot(env):
    e = env
    e.stock(e.eggs, e.wh["D01-RAW"], 100, 2400)
    e.stock(e.flour, e.wh["D01-RAW"], 10, 10000)
    so_d, wo = prepare_wo(e)
    # Creating a new master recipe cannot rewrite already-snapshotted materials.
    e.call(
        master.bom,
        dict(
            product_id=e.bread,
            purpose="production",
            kitchen_id=e.kitchen,
            output_quantity=100,
            valid_from=str(now().date()),
            lines=[dict(product_id=e.eggs, quantity=200)],
        ),
    )
    e.call(prod.start, wo["id"])
    with e.db.read() as c:
        m = [
            a
            for a in rows(c, "production_materials", production_order_id=wo["id"])
            if a["product_id"] == e.flour
        ][0]
    r = e.call(
        prod.complete,
        wo["id"],
        dict(
            good_quantity=96,
            failed_quantity=4,
            material_returns=[
                dict(material_id=m["id"], warehouse_id=e.wh["D01-RAW"], quantity=".5")
            ],
            byproducts=[
                dict(product_id=e.whites, warehouse_id=e.wh["D01-RAW"], quantity=3)
            ],
        ),
    )
    with e.db.read() as c:
        assert inv.balance(c, e.eggs, e.wh["D01-RAW"])["quantity"] == 0
        assert inv.balance(c, e.flour, e.wh["D01-RAW"])["quantity"] == D(".5")
        assert inv.balance(c, e.whites, e.wh["D01-RAW"])["inventory_value"] == 0
        assert r["net_material_cost"] == 335000


def test_production_shortage_rolls_back_all_materials(env):
    e = env
    e.stock(e.eggs, e.wh["D01-RAW"], 100, 2400)
    _, wo = prepare_wo(e)
    with pytest.raises(BusinessError):
        e.call(prod.start, wo["id"])
    with e.db.read() as c:
        assert inv.balance(c, e.eggs, e.wh["D01-RAW"])["quantity"] == 100
        assert document(c, wo["id"])["status"] == "draft"


def test_production_total_failure_requires_approval(env):
    e = env
    e.stock(e.eggs, e.wh["D01-RAW"], 100, 2400)
    e.stock(e.flour, e.wh["D01-RAW"], 10, 10000)
    _, wo = prepare_wo(e)
    e.call(prod.start, wo["id"])
    with pytest.raises(BusinessError):
        e.call(
            prod.complete,
            wo["id"],
            dict(good_quantity=0, failed_quantity=100, failure_reason="Gagal"),
        )
    e.approve(wo["id"], "production_loss")
    e.call(
        prod.complete,
        wo["id"],
        dict(good_quantity=0, failed_quantity=100, failure_reason="Gagal"),
    )
    with e.db.read() as c:
        assert document(c, wo["id"])["status"] == "completed"
        assert not rows(c, "production_outputs", production_order_id=wo["id"])


def test_planning_avoids_duplicate_and_addition_delta(env):
    e = env
    d, wo = prepare_wo(e)
    with e.db.read() as c:
        ds = rows(c, "demand_lines", source_document_id=d["id"])
        line = rows(c, "sales_order_lines", sales_order_id=d["id"])[0]
    with pytest.raises(BusinessError):
        e.call(prod.plan, {"demand_ids": [ds[0]["id"]]})
    proposal = e.call(
        sales.propose_revision,
        d["id"],
        dict(
            reason="Tambahan pelanggan", lines=[dict(line_id=line["id"], quantity=120)]
        ),
    )
    with e.db.write() as c:
        approval.decide(c, e.supervisor, proposal["id"], "approve")
    with pytest.raises(BusinessError):
        e.call(
            sales.revise_so,
            d["id"],
            dict(lines=[dict(line_id=line["id"], quantity=121)]),
        )
    e.call(sales.revise_so, d["id"], {})
    extra = e.call(prod.plan, {"demand_ids": [ds[0]["id"]]})[0]
    with e.db.read() as c:
        assert get(c, "production_orders", extra["id"])["planned_qty_base"] == 20


def test_minimum_accounts_for_open_store_request(env):
    e = env
    e.call(
        master.save,
        "replenishment_policies",
        dict(
            product_id=e.bread,
            warehouse_id=e.wh["T01"],
            source_warehouse_id=e.wh["PACK"],
            min_qty=30,
            target_qty=100,
            order_multiple=1,
            active=True,
        ),
    )
    with e.db.write() as c:
        assert prod.replenish(c)[0]["suggested_quantity"] == 100
    e.call(
        prod.store_request,
        dict(
            warehouse_id=e.wh["T01"],
            required_date=str(now().date() + dt.timedelta(days=1)),
            schedule_version_id=e.sv,
            lines=[dict(product_id=e.bread, quantity=100)],
        ),
    )
    with e.db.write() as c:
        assert prod.replenish(c)[0]["suggested_quantity"] == 0


def test_deposit_invoice_and_allocation_no_double_cash(env):
    e = env
    d = so(e, 2, e.bread, 8000)
    e.call(sales.confirm_so, d["id"])
    e.stock(e.bread, e.wh["PACK"], 2, 3000)
    payment = e.call(
        fin.payment,
        dict(
            purpose="deposit",
            customer_id=e.customer,
            sales_order_id=d["id"],
            amount=10000,
            method_id=e.cashmethod,
            cash_bank_account_id=e.cash,
        ),
    )
    with e.db.read() as c:
        dep = rows(c, "customer_deposits", receipt_payment_id=payment["id"])[0]
        ln = rows(c, "sales_order_lines", sales_order_id=d["id"])[0]
        comp = rows(c, "sales_order_components", sales_order_line_id=ln["id"])[0]
    e.call(
        sales.delivery, d["id"], dict(lines=[dict(component_id=comp["id"], quantity=2)])
    )
    invoice = e.call(sales.invoice, d["id"], {})
    e.call(
        fin.apply_deposit,
        dict(deposit_id=dep["id"], invoice_id=invoice["id"], amount=10000),
    )
    with e.db.read() as c:
        assert fin.invoice_due(c, invoice["id"]) == 6000
        assert fin.deposit_available(c, dep["id"]) == 0
        assert len(rows(c, "payments")) == 1


def test_pos_prices_packaging_and_tender_cash(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 10, 3000)
    shift = open_shift(e)
    p = sale_params(e, shift)
    p["tenders"][0]["amount_received"] = 20000
    r = e.call(pos.sale, p)
    with e.db.read() as c:
        assert get(c, "pos_sales", r["id"])["total"] == 16000
        assert rows(c, "pos_tenders")[0]["change_amount"] == 4000
        assert pos.expected_cash(c, shift["id"]) == 216000
    p = sale_params(e, shift)
    p["lines"][0]["product_id"] = e.package
    with pytest.raises(BusinessError):
        e.call(pos.sale, p)


def test_pos_negative_provisional_adjusted_on_receipt(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 1, 3000)
    s = open_shift(e)
    e.call(pos.sale, sale_params(e, s, qty=2))
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == -1
        assert rows(c, "negative_stock_cases")[0]["qty_short"] == 1
    e.stock(e.bread, e.wh["T01"], 1, 4000)
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 0
        assert rows(c, "negative_stock_cases")[0]["status"] == "closed"
        assert rows(c, "inventory_cost_adjustments")[0]["value_delta"] == 1000


def test_consignment_recognizes_only_sold_and_no_owned_duplication(env):
    e = env
    a = e.call(
        master.save,
        "consignment_agreements",
        dict(
            supplier_id=e.supplier,
            product_id=e.bread,
            warehouse_id=e.wh["T01"],
            version=1,
            unit_cost_base=5000,
            valid_from=str(now().date()),
            active=True,
            settlement_terms={},
        ),
    )
    s = open_shift(e)
    p = sale_params(e, s, qty=20, source="consignment", agreement=a["id"], price=160000)
    r = e.call(pos.sale, p)
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 0
        assert len(rows(c, "consignment_sales")) == 1
        assert len(rows(c, "stock_movements", source_document_id=r["id"])) == 2
    e.stock(e.bread, e.wh["T01"], 2, 5000)
    p = sale_params(e, s)
    e.call(pos.sale, p)
    with e.db.read() as c:
        assert len(rows(c, "consignment_sales")) == 1


def test_return_pos_partial_cumulative_and_refund_limits(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 2, 3000)
    s = open_shift(e)
    r = e.call(pos.sale, sale_params(e, s))
    with e.db.read() as c:
        ln = rows(c, "pos_sale_lines", pos_sale_id=r["id"])[0]
    p = dict(
        source_document_id=r["id"],
        shift_id=s["id"],
        reason="Dikembalikan",
        method_id=e.cashmethod,
        cash_bank_account_id=e.cash,
        authorization={"user_id": e.supervisor, "pin": "123456"},
        lines=[dict(line_id=ln["id"], quantity=1, condition="good")],
    )
    e.call(pos.pos_return, p)
    e.call(pos.pos_return, p)
    with pytest.raises(BusinessError):
        e.call(pos.pos_return, p)
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 2
        assert len(rows(c, "refunds")) == 2
        assert pos.expected_cash(c, s["id"]) == 200000


def test_supplier_return_keeps_po_closed(env):
    from app.services import returns as rt

    e = env
    d = make_po(e)
    gr = receive_po(e, d)
    with e.db.read() as c:
        ln = rows(c, "goods_receipt_lines", receipt_id=gr["id"])[0]
    r = e.call(
        rt.create,
        dict(
            source_document_id=gr["id"],
            side="supplier",
            supplier_id=e.supplier,
            warehouse_id=e.wh["CDC"],
            reason="Mutu",
            lines=[dict(line_id=ln["id"], quantity=10)],
        ),
    )
    e.approve(r["id"], "return")
    e.call(rt.post_return, r["id"])
    with e.db.read() as c:
        assert document(c, d["id"])["status"] == "received"
        assert inv.balance(c, e.flour, e.wh["CDC"])["quantity"] == 40


def test_approval_no_self_and_stale_revision(env):
    e = env
    d = make_po(e)
    with e.db.write() as c:
        q = approval.request(c, e.actor, d["id"], "stock_adjustment", "Koreksi")
    with pytest.raises(BusinessError):
        e.call(approval.decide, q["id"], "approve")
    with e.db.write() as c:
        approval.invalidate(c, d["id"])
    with pytest.raises(BusinessError):
        e.call(approval.decide, q["id"], "approve")


def test_opname_preserves_sales_after_count(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 10, 3000)
    adjustment = e.call(
        inv.adjust,
        dict(
            warehouse_id=e.wh["T01"],
            reason="opname",
            lines=[dict(product_id=e.bread, baseline_quantity=10, counted_quantity=8)],
        ),
    )
    s = open_shift(e)
    e.call(pos.sale, sale_params(e, s))
    e.approve(adjustment["id"], "stock_adjustment")
    e.call(inv.post_adjust, adjustment["id"])
    with e.db.read() as c:
        assert inv.balance(c, e.bread, e.wh["T01"])["quantity"] == 6


def test_all_journals_balanced(env):
    e = env
    d = make_po(e)
    receive_po(e, d)
    e.stock(e.bread, e.wh["T01"], 10, 3000)
    s = open_shift(e)
    e.call(pos.sale, sale_params(e, s))
    with e.db.read() as c:
        for j in rows(c, "journal_entries"):
            lines = rows(c, "journal_lines", journal_id=j["id"])
            assert sum(a["debit"] for a in lines) == sum(a["credit"] for a in lines)
