import datetime as dt
import os
from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.db import Database, rows, insert, get, update, metadata
from app.core import bootstrap, doc, journal, now, WIB
from app.services import master, approval, inventory, sync


@pytest.fixture
def env(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url

        assert make_url(url).database.endswith(
            "_test"
        ), "PostgreSQL regression tests require a dedicated *_test database"
        engine = create_engine(url)
        metadata.drop_all(engine)
        engine.dispose()
    db = Database(url or "sqlite:///" + str(tmp_path / "cloud.db"))
    with db.write() as c:
        result = bootstrap(c, "admin", "correct-admin-password")
        actor = result["user_id"]
        adminrole = rows(c, "roles", code="ADMIN")[0]
        supervisor = master.user(
            c,
            actor,
            dict(
                username="supervisor",
                name="Supervisor",
                password="correct-supervisor-password",
                pin="123456",
                role_ids=[adminrole["id"]],
            ),
        )["id"]
        for action in [
            "purchase",
            "stock_adjustment",
            "transit_resolution",
            "production_addition",
            "production_loss",
            "cancellation",
            "return",
            "refund",
            "period_close",
            "period_reopen",
            "pos_discount",
            "pos_refund",
        ]:
            master.rule(
                c,
                actor,
                {
                    "action_code": action,
                    "offline_allowed": action.startswith("pos_"),
                    "steps": [{"user_id": supervisor}],
                },
            )
        ids = {
            r["code"]: r["id"]
            for t in [
                "uoms",
                "warehouses",
                "kitchens",
                "outlets",
                "price_lists",
                "payment_methods",
                "cash_bank_accounts",
            ]
            for r in rows(c, t)
        }
        supplier = master.save(
            c,
            actor,
            "suppliers",
            {
                "code": "SUP",
                "name": "Supplier",
                "contact": {},
                "payment_terms_days": 0,
                "active": True,
            },
        )["id"]
        customer = master.save(
            c,
            actor,
            "customers",
            {"code": "CUS", "name": "Pelanggan", "contact": {}, "active": True},
        )["id"]
        sv = master.schedule(
            c,
            actor,
            dict(
                schedule_id=rows(c, "production_schedules")[0]["id"],
                cutoff_time="23:59",
                delivery_time="08:00",
                effective_from=str(now().astimezone(WIB).date()),
            ),
        )["id"]
        kitchen = rows(c, "kitchens", code="D01")[0]["id"]
        outlet = rows(c, "outlets", code="T01")[0]["id"]
        wh = {r["code"]: r["id"] for r in rows(c, "warehouses")}
        uoms = {r["code"]: r["id"] for r in rows(c, "uoms")}
        price = rows(c, "price_lists", code="POS")[0]["id"]
        cash = rows(c, "cash_bank_accounts")[0]["id"]
        cashmethod = rows(c, "payment_methods", code="CASH")[0]["id"]

        def make(sku, uom="pcs", **kw):
            return master.save(
                c,
                actor,
                "products",
                dict(
                    sku=sku,
                    name=sku,
                    base_uom_id=uoms[uom],
                    is_saleable=True,
                    is_purchasable=True,
                    is_manufacturable=False,
                    is_phantom=False,
                    default_sale_price=8000,
                    default_purchase_cost=0,
                    active=True,
                    **kw
                ),
            )["id"]

        bread = make("ROTI")
        flour = make("TEPUNG", "kg")
        eggs = make("TELUR", "butir")
        whites = make("PUTIH", "kg")
        box = make("BOX")
        package = make("PAKET")
        update(c, "products", package, is_phantom=True, is_purchasable=False)
        update(c, "products", bread, is_manufacturable=True)
        master.save(
            c,
            actor,
            "product_uoms",
            dict(
                product_id=flour,
                uom_id=uoms["dus"],
                factor_to_base=10,
                is_base=False,
                allow_sale=False,
                allow_purchase=True,
                active=True,
            ),
        )
        master.save(
            c,
            actor,
            "product_kitchen_routes",
            dict(
                product_id=bread,
                kitchen_id=kitchen,
                raw_warehouse_id=wh["D01-RAW"],
                output_warehouse_id=wh["D01-FIN"],
                is_default=True,
                active=True,
            ),
        )
        bom = master.bom(
            c,
            actor,
            dict(
                product_id=bread,
                purpose="production",
                kitchen_id=kitchen,
                output_quantity=100,
                valid_from=str(now().date()),
                lines=[
                    dict(product_id=eggs, quantity=100),
                    dict(product_id=flour, quantity=10),
                ],
                byproducts=[dict(product_id=whites, quantity=3)],
            ),
        )["id"]
        master.bom(
            c,
            actor,
            dict(
                product_id=package,
                purpose="package",
                output_quantity=1,
                valid_from=str(now().date()),
                lines=[
                    dict(product_id=bread, quantity=1),
                    dict(product_id=box, quantity=1),
                ],
            ),
        )
        terminal = sync.register(c, actor, dict(code="K01", outlet_id=outlet))

    def call(fn, *args, **kwargs):
        with db.write() as c:
            return fn(c, actor, *args, **kwargs)

    def approve(docid, action):
        with db.write() as c:
            q = approval.request(c, actor, docid, action, "Pengujian dokumen")
            return approval.decide(c, supervisor, q["id"], "approve", "Diperiksa")

    def stock(product, warehouse, qty, cost):
        with db.write() as c:
            d = doc(c, actor, "OPENING")
            inventory.move(
                c, d["id"], "opening", product, warehouse, qty, "opening", cost
            )
            journal(
                c,
                d["id"],
                "opening",
                [
                    ("1200", Decimal(str(qty)) * Decimal(str(cost)), 0),
                    ("3000", 0, Decimal(str(qty)) * Decimal(str(cost))),
                ],
            )
            from app.core import post

            post(c, actor, d["id"])

    return SimpleNamespace(
        db=db,
        actor=actor,
        supervisor=supervisor,
        ids=ids,
        wh=wh,
        uoms=uoms,
        supplier=supplier,
        customer=customer,
        sv=sv,
        kitchen=kitchen,
        outlet=outlet,
        price=price,
        cash=cash,
        cashmethod=cashmethod,
        bread=bread,
        flour=flour,
        eggs=eggs,
        whites=whites,
        box=box,
        package=package,
        bom=bom,
        terminal=terminal,
        call=call,
        approve=approve,
        stock=stock,
    )
