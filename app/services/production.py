from app.core import *
from app.services.approval import approved
from app.services.inventory import move, balance


def demand_unplanned(c, d):
    allocated = ZERO
    for a in rows(c, "wo_demand_allocations", demand_id=d["id"]):
        status = document(c, a["production_order_id"])["status"]
        allocated += (
            a["qty_fulfilled"]
            if status == "completed"
            else a["qty_planned"] - a["qty_cancelled"] if status != "cancelled" else 0
        )
    return max(ZERO, d["qty_required"] - allocated)


def plan(c, actor, p):
    need(p.get("demand_ids"), "Pilih kebutuhan")
    groups = {}
    for id in p["demand_ids"]:
        d = require(c, "demand_lines", id)
        need(d["status"] != "cancelled", "Kebutuhan dibatalkan")
        q = demand_unplanned(c, d)
        if not q:
            continue
        product = require(c, "products", d["product_id"])
        need(product["is_manufacturable"], "Komponen supplier / stok tidak dibuat WO")
        routes = [
            r
            for r in rows(c, "product_kitchen_routes", product_id=product["id"])
            if r["active"] and r["is_default"]
        ]
        need(routes, "Rute dapur belum tersedia")
        route = routes[0]
        boms = [
            b
            for b in rows(
                c, "boms", product_id=product["id"], kitchen_id=route["kitchen_id"]
            )
            if b["active"] and b["purpose"] == "production"
        ]
        need(boms, "Resep produksi aktif belum tersedia")
        bom = max(boms, key=lambda a: a["version"])
        key = (
            product["id"],
            route["kitchen_id"],
            bom["id"],
            str(d["required_at"].date()),
            d["schedule_version_id"],
        )
        groups.setdefault(key, dict(route=route, bom=bom, alloc=[]))["alloc"].append(
            (d, q)
        )
    out = []
    for key, g in groups.items():
        d = doc(c, actor, "WO", p)
        q = sum(x[1] for x in g["alloc"])
        route = g["route"]
        bom = g["bom"]
        insert(
            c,
            "production_orders",
            dict(
                id=d["id"],
                product_id=key[0],
                bom_id=bom["id"],
                kitchen_id=route["kitchen_id"],
                output_warehouse_id=route["output_warehouse_id"],
                schedule_version_id=key[4],
                plan_date=key[3],
                planned_qty_base=q,
                actual_good_qty_base=None,
                material_net_cost=0,
                parent_wo_id=p.get("parent_wo_id"),
                started_at=None,
                completed_at=None,
            ),
        )
        for demand, amount in g["alloc"]:
            insert(
                c,
                "wo_demand_allocations",
                dict(
                    production_order_id=d["id"],
                    demand_id=demand["id"],
                    qty_planned=amount,
                    qty_fulfilled=0,
                    qty_cancelled=0,
                ),
            )
        materials = rows(c, "bom_lines", bom_id=bom["id"])
        need(materials, "Resep tidak memiliki bahan")
        for m in materials:
            insert(
                c,
                "production_materials",
                dict(
                    production_order_id=d["id"],
                    bom_line_id=m["id"],
                    product_id=m["component_product_id"],
                    warehouse_id=m["source_warehouse_id"] or route["raw_warehouse_id"],
                    planned_qty_base=m["qty_base"] * q / bom["output_qty_base"],
                    issued_qty_base=0,
                    unit_cost_snapshot=0,
                    issue_movement_id=None,
                ),
            )
        out.append(d)
    need(out, "Kebutuhan yang dipilih sudah memiliki pemenuhan / WO")
    return out


def start(c, actor, id):
    document(c, id, ["draft"], "WO")
    wo = require(c, "production_orders", id)
    cost = ZERO
    for m in rows(c, "production_materials", production_order_id=id):
        mv = move(
            c,
            id,
            m["id"],
            m["product_id"],
            m["warehouse_id"],
            -m["planned_qty_base"],
            "production_issue",
        )
        cost += m["planned_qty_base"] * mv["unit_cost"]
        update(
            c,
            "production_materials",
            m["id"],
            issued_qty_base=m["planned_qty_base"],
            unit_cost_snapshot=mv["unit_cost"],
            issue_movement_id=mv["id"],
        )
    journal(c, id, "production_start", [("1400", cost, 0), ("1200", 0, cost)])
    update(c, "production_orders", id, started_at=now(), material_net_cost=cost)
    post(c, actor, id, "started")
    return {"id": id, "material_cost": cost}


def complete(c, actor, id, p):
    document(c, id, ["started"], "WO")
    wo = require(c, "production_orders", id)
    good = dec(p["good_quantity"])
    failed = dec(p.get("failed_quantity", 0))
    net = wo["material_net_cost"]
    for a in p.get("material_returns", []):
        m = require(c, "production_materials", a["material_id"])
        need(m["production_order_id"] == id, "Bahan bukan dari WO ini")
        q = dec(a["quantity"], True)
        prev = sum(
            (
                r["qty_base"]
                for r in rows(
                    c, "production_material_returns", production_material_id=m["id"]
                )
            ),
            ZERO,
        )
        need(prev + q <= m["issued_qty_base"], "Sisa layak melebihi bahan dikeluarkan")
        w = require(c, "warehouses", a["warehouse_id"])
        need(w["kind"] == "kitchen_raw", "Sisa bahan layak harus kembali ke RAW dapur")
        mv = move(
            c,
            id,
            m["id"] + "-return",
            m["product_id"],
            w["id"],
            q,
            "production_material_return",
            m["unit_cost_snapshot"],
        )
        net -= q * m["unit_cost_snapshot"]
        insert(
            c,
            "production_material_returns",
            dict(
                production_material_id=m["id"],
                warehouse_id=w["id"],
                qty_base=q,
                unit_cost_snapshot=m["unit_cost_snapshot"],
                stock_movement_id=mv["id"],
            ),
        )
    returned = wo["material_net_cost"] - net
    if returned:
        journal(
            c,
            id,
            "production_material_returns",
            [("1200", returned, 0), ("1400", 0, returned)],
        )
    if good:
        cost = net / good
        mv = move(
            c,
            id,
            "main",
            wo["product_id"],
            wo["output_warehouse_id"],
            good,
            "production_output",
            cost,
        )
        insert(
            c,
            "production_outputs",
            dict(
                production_order_id=id,
                product_id=wo["product_id"],
                warehouse_id=wo["output_warehouse_id"],
                kind="main",
                qty_base=good,
                unit_cost=cost,
                stock_movement_id=mv["id"],
            ),
        )
        journal(c, id, "production_complete", [("1200", net, 0), ("1400", 0, net)])
    else:
        approved(c, actor, id, "production_loss")
        need(
            failed > 0 and p.get("failure_reason"),
            "Produksi gagal total perlu jumlah gagal dan alasan",
        )
        journal(c, id, "production_loss", [("5100", net, 0), ("1400", 0, net)])
    byproducts = rows(c, "bom_byproducts", bom_id=wo["bom_id"])
    for a in p.get("byproducts", []):
        need(
            any(
                b["product_id"] == a["product_id"] and b["cost_policy"] == "zero"
                for b in byproducts
            ),
            "Produk turunan harus terdaftar dengan kebijakan biaya nol",
        )
        q = dec(a["quantity"], True)
        mv = move(
            c,
            id,
            "byproduct-" + a["product_id"],
            a["product_id"],
            a["warehouse_id"],
            q,
            "production_byproduct",
            0,
        )
        insert(
            c,
            "production_outputs",
            dict(
                production_order_id=id,
                product_id=a["product_id"],
                warehouse_id=a["warehouse_id"],
                kind="byproduct",
                qty_base=q,
                unit_cost=0,
                stock_movement_id=mv["id"],
            ),
        )
    if failed:
        insert(
            c,
            "production_failures",
            dict(
                production_order_id=id,
                product_id=wo["product_id"],
                qty_base=failed,
                reason=p.get("failure_reason", "Hasil tidak memenuhi standar"),
                disposition="scrap",
                loss_amount=net if not good else 0,
            ),
        )
    remaining = good
    for a in sorted(
        rows(c, "wo_demand_allocations", production_order_id=id),
        key=lambda a: require(c, "demand_lines", a["demand_id"])["required_at"],
    ):
        q = min(remaining, a["qty_planned"] - a["qty_cancelled"])
        remaining -= q
        update(c, "wo_demand_allocations", a["id"], qty_fulfilled=q)
    update(
        c,
        "production_orders",
        id,
        actual_good_qty_base=good,
        material_net_cost=net,
        completed_at=now(),
    )
    post(c, actor, id, "completed")
    return {
        "id": id,
        "net_material_cost": net,
        "good_quantity": good,
        "byproduct_cost": 0,
    }


def store_request(c, actor, p):
    d = doc(c, actor, "STORE_REQUEST", p)
    w = require(c, "warehouses", p["warehouse_id"])
    need(w["kind"] == "store", "Permintaan harus untuk toko fisik")
    sv = require(c, "schedule_versions", p["schedule_version_id"])
    required = dt.date.fromisoformat(p["required_date"])
    insert(
        c,
        "store_requests",
        dict(
            id=d["id"],
            outlet_id=w["outlet_id"],
            warehouse_id=w["id"],
            required_date=required,
            schedule_version_id=sv["id"],
            origin=p.get("origin", "manual"),
        ),
    )
    need(p.get("lines"), "Isi produk permintaan")
    for a in p["lines"]:
        product, u = unit(c, a["product_id"])
        q = dec(a["quantity"], True)
        ln = insert(
            c,
            "store_request_lines",
            dict(
                store_request_id=d["id"],
                product_id=product["id"],
                qty_base=q,
                policy_id=a.get("policy_id"),
            ),
        )
        insert(
            c,
            "demand_lines",
            dict(
                product_id=product["id"],
                so_component_id=None,
                store_request_line_id=ln["id"],
                source_document_id=d["id"],
                origin="store_request",
                required_at=dt.datetime.combine(required, sv["delivery_time"], WIB),
                schedule_version_id=sv["id"],
                revision=1,
                qty_required=q,
                status="open",
            ),
        )
    post(c, actor, d["id"], "confirmed")
    return d


def replenish(c):
    out = []
    for policy in rows(c, "replenishment_policies", active=True):
        b = balance(c, policy["product_id"], policy["warehouse_id"])
        openqty = ZERO
        for req in rows(c, "store_requests", warehouse_id=policy["warehouse_id"]):
            if document(c, req["id"])["status"] == "cancelled":
                continue
            for ln in rows(
                c,
                "store_request_lines",
                store_request_id=req["id"],
                product_id=policy["product_id"],
            ):
                demand = rows(c, "demand_lines", store_request_line_id=ln["id"])
                if demand and demand[0]["status"] == "open":
                    received = ZERO
                    for transfer_line in rows(
                        c, "transfer_lines", demand_id=demand[0]["id"]
                    ):
                        received += sum(
                            (
                                r["qty_received"]
                                for r in rows(
                                    c,
                                    "transfer_receipt_lines",
                                    transfer_line_id=transfer_line["id"],
                                )
                            ),
                            ZERO,
                        )
                    openqty += max(ZERO, ln["qty_base"] - received)
        incoming = ZERO
        from app.services.inventory import line_remaining

        for tr in rows(c, "transfer_orders", to_warehouse_id=policy["warehouse_id"]):
            if document(c, tr["id"])["status"] in ("in_transit", "partial"):
                for ln in rows(
                    c,
                    "transfer_lines",
                    transfer_id=tr["id"],
                    product_id=policy["product_id"],
                ):
                    if not ln["demand_id"]:
                        incoming += line_remaining(c, ln)
        # Demand-linked transfer is already represented by its open store request.
        position = b["quantity"] - b["reserved_quantity"] + openqty + incoming
        q = (
            max(ZERO, policy["target_qty"] - position)
            if position < policy["min_qty"]
            else ZERO
        )
        multiple = policy["order_multiple"]
        need(multiple > 0, "Kelipatan harus lebih dari nol")
        if q:
            q = (q / multiple).to_integral_value(rounding="ROUND_CEILING") * multiple
        out.append(
            {
                **policy,
                "net_position": position,
                "open_request": openqty,
                "unallocated_in_transit": incoming,
                "suggested_quantity": q,
            }
        )
    return out
