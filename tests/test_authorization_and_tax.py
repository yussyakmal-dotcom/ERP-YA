"""Regression coverage for monetary boundaries and partial reversals."""

from decimal import Decimal as D
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core import BusinessError, set_setting, now
from app.db import rows, get, insert
from app.services import master, approval, purchasing, pos, sales, finance
from app.services import returns as rt
from tests.test_api_sync import login, cmd
from tests.test_business import make_po, receive_po, open_shift, sale_params, so
from tests.test_commerce import tax


def test_purchase_approval_uses_server_value_instead_of_claimed_amount(env):
    e = env
    e.call(
        master.rule,
        dict(action_code="purchase", max_amount=100, steps=[{"user_id": e.supervisor}]),
    )
    order = e.call(
        purchasing.create_po,
        dict(
            supplier_id=e.supplier,
            receiving_warehouse_id=e.wh["CDC"],
            lines=[dict(product_id=e.flour, quantity=2, unit_price=1000)],
        ),
    )
    client = TestClient(
        create_app(
            e.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    response = cmd(
        client,
        login(client),
        "approval.request",
        dict(id=order["id"], action_code="purchase", reason="Periksa", amount=1),
    )
    assert response.status_code == 422
    with e.db.read() as c:
        assert not rows(c, "approval_requests", document_id=order["id"])


def test_pos_refund_limit_uses_returned_goods_value(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 2, 3000)
    shift = open_shift(e)
    sale = e.call(pos.sale, sale_params(e, shift))
    with e.db.read() as c:
        line = rows(c, "pos_sale_lines", pos_sale_id=sale["id"])[0]
    e.call(
        master.rule,
        dict(
            action_code="pos_refund",
            offline_allowed=True,
            max_amount=100,
            steps=[{"user_id": e.supervisor}],
        ),
    )
    with pytest.raises(BusinessError):
        e.call(
            pos.pos_return,
            dict(
                source_document_id=sale["id"],
                shift_id=shift["id"],
                reason="Retur",
                amount=1,
                method_id=e.cashmethod,
                cash_bank_account_id=e.cash,
                authorization={"user_id": e.supervisor, "pin": "123456"},
                lines=[dict(line_id=line["id"], quantity=1)],
            ),
        )
    with e.db.read() as c:
        assert not rows(c, "returns")


def test_partial_returns_reverse_all_inclusive_tax_cents_and_earned_points(env):
    e = env
    tax(e, inclusive=True)
    with e.db.write() as c:
        set_setting(c, e.actor, "loyalty_policy", {"spend_per_point": 1000})
    e.stock(e.bread, e.wh["T01"], 3, 3000)
    shift = open_shift(e)
    p = sale_params(e, shift, qty=3, price=24000)
    p["customer_id"] = e.customer
    sale = e.call(pos.sale, p)
    with e.db.read() as c:
        line = rows(c, "pos_sale_lines", pos_sale_id=sale["id"])[0]
    for _ in range(3):
        e.call(
            pos.pos_return,
            dict(
                source_document_id=sale["id"],
                shift_id=shift["id"],
                reason="Retur sebagian",
                method_id=e.cashmethod,
                cash_bank_account_id=e.cash,
                authorization={"user_id": e.supervisor, "pin": "123456"},
                lines=[dict(line_id=line["id"], quantity=1, condition="good")],
            ),
        )
    with e.db.read() as c:
        account = rows(c, "chart_of_accounts", code="2180")[0]
        assert (
            sum(
                a["debit"] - a["credit"]
                for a in rows(c, "journal_lines", account_id=account["id"])
            )
            == 0
        )
        assert (
            rows(c, "loyalty_accounts", customer_id=e.customer)[0]["points_balance"]
            == 0
        )
        assert pos.expected_cash(c, shift["id"]) == shift["opening_cash"]


@pytest.mark.parametrize("inclusive", [False, True])
def test_purchase_tax_is_not_capitalized_and_supplier_refund_includes_tax(
    env, inclusive
):
    e = env
    with e.db.write() as c:
        account = insert(
            c,
            "chart_of_accounts",
            dict(
                code="1450",
                name="Pajak masukan",
                account_type="asset",
                normal_balance="debit",
                parent_id=None,
                is_postable=True,
                active=True,
            ),
        )
        tx = master.save(
            c,
            e.actor,
            "taxes",
            dict(
                code="INPUT",
                version=1,
                rate=".1",
                price_inclusive=inclusive,
                input_account_id=account["id"],
                effective_from=str(now().date()),
            ),
        )
        set_setting(c, e.actor, "tax_policy", {"purchase_tax_id": tx["id"]})
    d = e.call(
        purchasing.create_po,
        dict(
            supplier_id=e.supplier,
            receiving_warehouse_id=e.wh["CDC"],
            lines=[
                dict(
                    product_id=e.flour,
                    quantity=2,
                    unit_price=11000 if inclusive else 10000,
                )
            ],
        ),
    )
    e.approve(d["id"], "purchase")
    e.call(purchasing.confirm_po, d["id"])
    gr = receive_po(e, d, qty=2)
    with e.db.read() as c:
        line = rows(c, "goods_receipt_lines", receipt_id=gr["id"])[0]
        assert line["unit_cost_snapshot"] == 10000
    invoice = e.call(
        purchasing.invoice,
        dict(
            goods_receipt_id=gr["id"],
            supplier_invoice_no="INPUT-1",
            lines=[dict(receipt_line_id=line["id"], quantity=2)],
        ),
    )
    r = e.call(
        rt.create,
        dict(
            source_document_id=gr["id"],
            side="supplier",
            warehouse_id=e.wh["CDC"],
            reason="Retur supplier",
            lines=[dict(line_id=line["id"], quantity=1)],
        ),
    )
    e.approve(r["id"], "return")
    result = e.call(rt.post_return, r["id"])
    assert result["credit_amount"] == 11000
    with e.db.read() as c:
        assert get(c, "purchase_invoices", invoice["id"])["total"] == 22000


def test_so_return_requires_invoice_then_reverses_package_credit(env):
    e = env
    order = so(e, qty=1)
    e.call(sales.confirm_so, order["id"])
    e.stock(e.bread, e.wh["PACK"], 1, 3000)
    e.stock(e.box, e.wh["PACK"], 1, 1000)
    with e.db.read() as c:
        line = rows(c, "sales_order_lines", sales_order_id=order["id"])[0]
        components = rows(c, "sales_order_components", sales_order_line_id=line["id"])
    delivery = e.call(
        sales.delivery,
        order["id"],
        dict(lines=[dict(component_id=co["id"], quantity=1) for co in components]),
    )
    with e.db.read() as c:
        lines = rows(c, "delivery_lines", delivery_id=delivery["id"])
    params = dict(
        source_document_id=delivery["id"],
        side="customer",
        warehouse_id=e.wh["PACK"],
        reason="Kembali lengkap",
        lines=[dict(line_id=ln["id"], quantity=1) for ln in lines],
    )
    with pytest.raises(BusinessError):
        e.call(rt.create, params)
    invoice = e.call(sales.invoice, order["id"], {})
    r = e.call(rt.create, params)
    e.approve(r["id"], "return")
    result = e.call(rt.post_return, r["id"])
    assert result["credit_amount"] == 25000
    e.call(
        finance.apply_credit,
        dict(
            credit_note_id=result["credit_note_id"],
            invoice_id=invoice["id"],
            amount=25000,
        ),
    )
    with e.db.read() as c:
        assert finance.invoice_due(c, invoice["id"]) == 0
