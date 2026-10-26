from decimal import Decimal as D
import datetime as dt
import pytest
from app.core import now, set_setting, document, BusinessError, digest
from app.db import rows, insert, get, update, clean
from app.services import (
    commerce,
    pos,
    master,
    sync,
    inventory,
    purchasing,
    finance,
    approval,
)
from tests.test_business import open_shift, sale_params, make_po, receive_po


def tax(e, inclusive=False):
    with e.db.write() as c:
        account = insert(
            c,
            "chart_of_accounts",
            dict(
                code="2180",
                name="Pajak keluaran",
                account_type="liability",
                normal_balance="credit",
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
                code="TEST",
                version=1,
                rate=".1",
                price_inclusive=inclusive,
                output_account_id=account["id"],
                effective_from=str(now().date()),
            ),
        )
        set_setting(c, e.actor, "tax_policy", {"pos_tax_id": tx["id"]})


@pytest.mark.parametrize("inclusive", [False, True])
def test_tax_snapshot_balanced_and_return_reverses_tax(env, inclusive):
    e = env
    tax(e, inclusive)
    e.stock(e.bread, e.wh["T01"], 2, 3000)
    s = open_shift(e)
    p = sale_params(e, s)
    p["tenders"][0]["amount_applied"] = 16000 if inclusive else 17600
    p["tenders"][0]["amount_received"] = p["tenders"][0]["amount_applied"]
    r = e.call(pos.sale, p)
    with e.db.read() as c:
        sale = get(c, "pos_sales", r["id"])
        ln = rows(c, "pos_sale_lines", pos_sale_id=r["id"])[0]
        assert sale["total"] == (16000 if inclusive else 17600)
        assert sale["tax_total"] == (D("1454.55") if inclusive else D("1600"))
    result = e.call(
        pos.pos_return,
        dict(
            source_document_id=r["id"],
            shift_id=s["id"],
            reason="Retur",
            method_id=e.cashmethod,
            cash_bank_account_id=e.cash,
            authorization={"user_id": e.supervisor, "pin": "123456"},
            lines=[dict(line_id=ln["id"], quantity=2, condition="good")],
        ),
    )
    with e.db.read() as c:
        account = rows(c, "chart_of_accounts", code="2180")[0]
        lines = rows(c, "journal_lines", account_id=account["id"])
        assert sum(a["debit"] - a["credit"] for a in lines) == 0


def test_global_promotion_without_manual_price_override(env):
    e = env
    with e.db.write() as c:
        promo = master.save(
            c,
            e.actor,
            "promotion_rules",
            dict(
                code="PROMO",
                version=1,
                scope="global",
                discount_type="percent",
                value=10,
                conditions={},
                valid_from=(now() - dt.timedelta(minutes=1)).isoformat(),
                active=True,
            ),
        )
    e.stock(e.bread, e.wh["T01"], 2, 3000)
    s = open_shift(e)
    p = sale_params(e, s)
    p["promotion_id"] = promo["id"]
    p["tenders"][0]["amount_applied"] = 14400
    p["tenders"][0]["amount_received"] = 14400
    r = e.call(pos.sale, p)
    with e.db.read() as c:
        assert get(c, "pos_sales", r["id"])["discount_total"] == 1600


def test_voucher_hold_is_exclusive_across_two_terminals(env):
    e = env
    with e.db.write() as c:
        promo = master.save(
            c,
            e.actor,
            "promotion_rules",
            dict(
                code="PROMO",
                version=1,
                scope="global",
                discount_type="fixed",
                value=2000,
                conditions={},
                valid_from=(now() - dt.timedelta(minutes=1)).isoformat(),
                active=True,
            ),
        )
        voucher = master.save(
            c,
            e.actor,
            "vouchers",
            dict(
                code="ONLYONE",
                promotion_rule_id=promo["id"],
                max_uses=1,
                valid_from=(now() - dt.timedelta(minutes=1)).isoformat(),
                valid_to=(now() + dt.timedelta(days=1)).isoformat(),
                active=True,
            ),
        )
        t2 = sync.register(c, e.actor, dict(code="K02", outlet_id=e.outlet))
        hold = commerce.reserve_redemption(
            c,
            e.terminal["terminal"],
            e.actor,
            dict(sale_id="draft-a", voucher_code="ONLYONE", eligible_amount=16000),
        )
    with pytest.raises(BusinessError), e.db.write() as c:
        commerce.reserve_redemption(
            c,
            t2["terminal"],
            e.actor,
            dict(sale_id="draft-b", voucher_code="ONLYONE", eligible_amount=16000),
        )
    with e.db.write() as c:
        commerce.cancel_hold(c, e.terminal["terminal"], hold["id"])
        new = commerce.reserve_redemption(
            c,
            t2["terminal"],
            e.actor,
            dict(sale_id="draft-b", voucher_code="ONLYONE", eligible_amount=16000),
        )
        assert new["amount"] == 2000


def test_points_reserved_once_and_earn_after_sale(env):
    e = env
    with e.db.write() as c:
        set_setting(
            c, e.actor, "loyalty_policy", {"point_value": 100, "spend_per_point": 1000}
        )
        account = insert(
            c,
            "loyalty_accounts",
            dict(customer_id=e.customer, points_balance=20, version=1),
        )
        hold = commerce.reserve_redemption(
            c,
            e.terminal["terminal"],
            e.actor,
            dict(
                sale_id="draft-loyalty",
                customer_id=e.customer,
                points=10,
                eligible_amount=16000,
            ),
        )
    e.stock(e.bread, e.wh["T01"], 2, 3000)
    s = open_shift(e)
    p = sale_params(e, s)
    p.update(id="draft-loyalty", customer_id=e.customer, _redemption=hold)
    p["tenders"][0]["amount_applied"] = 15000
    p["tenders"][0]["amount_received"] = 15000
    r = e.call(pos.sale, p)
    with e.db.read() as c:
        assert get(c, "loyalty_accounts", account["id"])["points_balance"] == 25
        assert get(c, "app_redemptions", hold["id"])["status"] == "applied"
        assert len(rows(c, "loyalty_entries")) == 2


def test_consignment_does_not_settle_owned_negative_stock(env):
    e = env
    e.stock(e.bread, e.wh["T01"], 1, 3000)
    s = open_shift(e)
    e.call(pos.sale, sale_params(e, s))
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
    e.call(pos.sale, sale_params(e, s, source="consignment", agreement=a["id"]))
    with e.db.read() as c:
        assert inventory.balance(c, e.bread, e.wh["T01"])["quantity"] == -1
        assert rows(c, "negative_stock_cases")[0]["status"] == "open"
        assert len(rows(c, "negative_stock_cases")) == 1


def test_supplier_return_before_invoice_does_not_create_double_claim(env):
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
            warehouse_id=e.wh["CDC"],
            reason="Mutu",
            lines=[dict(line_id=ln["id"], quantity=10)],
        ),
    )
    e.approve(r["id"], "return")
    out = e.call(rt.post_return, r["id"])
    assert out["credit_amount"] == 0
    invoice = e.call(
        purchasing.invoice,
        dict(
            goods_receipt_id=gr["id"],
            supplier_invoice_no="INV-SUP-1",
            lines=[dict(receipt_line_id=ln["id"], quantity=40)],
        ),
    )
    with e.db.read() as c:
        assert get(c, "purchase_invoices", invoice["id"])["total"] == 400000
        acc = rows(c, "chart_of_accounts", code="2120")[0]
        j = rows(c, "journal_lines", account_id=acc["id"])
        assert sum(a["debit"] - a["credit"] for a in j) == 0


def test_closed_period_event_preserves_original_payload_and_review(env, tmp_path):
    from tests.test_api_sync import local, cmd
    from fastapi.testclient import TestClient
    from app.main import create_app

    e = env
    e.stock(e.bread, e.wh["T01"], 3, 3000)
    app, client, h = local(e, tmp_path)
    opened = cmd(client, h, "pos.open", {"opening_cash": 0}).json()
    with app.state.db.read() as c:
        event = clean(rows(c, "sync_outbox")[0])
    with e.db.write() as c:
        sync.apply_event(c, e.terminal["terminal"], event)
    p = sale_params(e, opened)
    assert cmd(client, h, "pos.sale", p).status_code == 200
    with app.state.db.read() as c:
        event = clean(
            sorted(rows(c, "sync_outbox"), key=lambda a: a["local_sequence"])[-1]
        )
    with e.db.write() as c:
        per = rows(c, "fiscal_periods")[0]
        update(c, "fiscal_periods", per["id"], status="closed")
        start = per["end_date"] + dt.timedelta(days=1)
        end = (start.replace(day=28) + dt.timedelta(days=4)).replace(
            day=1
        ) - dt.timedelta(days=1)
        master.save(
            c,
            e.actor,
            "fiscal_periods",
            dict(
                name="Periode berikut",
                start_date=str(start),
                end_date=str(end),
                status="open",
            ),
        )
        master.rule(
            c,
            e.actor,
            dict(action_code="sync_correction", steps=[{"user_id": e.supervisor}]),
        )
    cloud = TestClient(
        create_app(
            e.db.engine.url.render_as_string(hide_password=False), start_worker=False
        )
    )
    headers = {"Authorization": "Terminal " + e.terminal["token"]}
    res = cloud.post(
        "/api/sync/events",
        headers=headers,
        json={"event": event, "signature": sync.sign(e.terminal["token"], event)},
    )
    assert res.status_code == 409, res.text
    with e.db.read() as c:
        conflict = rows(c, "sync_conflicts")[0]
        assert get(c, "sync_inbox", event["id"])["payload"] == event["payload"]
        assert not rows(c, "pos_sales")
    review = e.call(sync.review_conflict, dict(conflict_id=conflict["id"]))
    e.approve(review["id"], "sync_correction")
    e.call(
        sync.resolve_conflict,
        dict(
            conflict_id=conflict["id"],
            posting_date=str(start),
            reason="Posting koreksi periode terbuka",
        ),
    )
    with e.db.read() as c:
        inbox = get(c, "sync_inbox", event["id"])
        assert inbox["payload"] == event["payload"]
        assert inbox["status"] == "applied"
        assert document(c, event["aggregate_document_id"])["business_date"] == start
        assert (
            document(c, event["aggregate_document_id"])["document_no"]
            == event["payload"]["parameters"]["document_no"]
        )
