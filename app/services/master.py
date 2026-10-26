from app.core import *
from app.db import MODEL

EDITABLE = {
    "products",
    "product_uoms",
    "categories",
    "uoms",
    "suppliers",
    "customers",
    "product_kitchen_routes",
    "replenishment_policies",
    "price_lists",
    "price_list_items",
    "promotion_rules",
    "vouchers",
    "consignment_agreements",
    "outlets",
    "kitchens",
    "warehouses",
    "payment_methods",
    "cash_bank_accounts",
    "chart_of_accounts",
    "taxes",
    "fiscal_periods",
    "roles",
}
IMMUTABLE_VERSIONS = {
    "schedule_versions",
    "boms",
    "approval_rules",
    "taxes",
    "price_list_items",
}


def save(c, actor, name, p, id=None):
    need(name in EDITABLE, "Master ini harus melalui perintah khusus", 403)
    allowed(c, actor, "master")
    old = require(c, name, id) if id else None
    if name == "roles":
        allowed(c, actor, "users")
    if old:
        need(
            name not in IMMUTABLE_VERSIONS,
            "Buat versi baru; riwayat harga/resep/jadwal tidak diedit",
        )
        if (
            name == "products"
            and p.get("base_uom_id", old["base_uom_id"]) != old["base_uom_id"]
        ):
            need(
                not rows(c, "stock_movements", product_id=id),
                "Satuan dasar sudah dipakai; buat SKU baru",
            )
        values = {**old, **p}
        values.pop("id", None)
        values.pop("created_at", None)
        need(
            not any(k in p for k in ("password_hash", "pin_hash")),
            "Field autentikasi tidak boleh ditulis langsung",
        )
    else:
        values = {}
        for f in MODEL[name]["fields"]:
            k = f["name"]
            if k in ("id", "created_at") or k in p:
                continue
            if f["nullable"]:
                values[k] = None
            elif f["type"] == "boolean":
                values[k] = k == "active"
            elif f["type"] == "jsonb":
                values[k] = {}
            elif f["type"].startswith(("decimal", "int", "bigint")):
                values[k] = 0
            elif not f["ref"] and f["type"].startswith(("text", "varchar")):
                values[k] = ""
        values.update(p)
    if name == "fiscal_periods" and old:
        need(
            old["status"] == "open" and values.get("status") == old["status"],
            "Status periode hanya berubah melalui tutup / buka terotorisasi",
        )
        need(
            not rows(c, "journal_entries", period_id=id)
            or (
                str(values["start_date"]) == str(old["start_date"])
                and str(values["end_date"]) == str(old["end_date"])
            ),
            "Tanggal periode yang sudah dipakai tidak dapat diubah",
        )
    if name == "products":
        need(
            values.get("sku") and values.get("name") and values.get("base_uom_id"),
            "SKU, nama dan satuan dasar wajib",
        )
        dec(values.get("default_sale_price", 0))
        dec(values.get("default_purchase_cost", 0))
    if name == "product_uoms":
        dec(values["factor_to_base"], True)
        pr = require(c, "products", values["product_id"])
        if values.get("is_base"):
            need(
                values["uom_id"] == pr["base_uom_id"]
                and dec(values["factor_to_base"]) == 1,
                "Satuan dasar harus faktor 1",
            )
        if values.get("barcode"):
            need(
                not any(
                    r["id"] != id for r in rows(c, name, barcode=values["barcode"])
                ),
                "Barcode telah dipakai satuan lain",
            )
    if name == "replenishment_policies":
        need(
            dec(values["min_qty"]) <= dec(values["target_qty"])
            and dec(values["order_multiple"], True) > 0,
            "Minimum, target, atau kelipatan tidak valid",
        )
    if name == "consignment_agreements":
        dec(values["unit_cost_base"])
        need(
            require(c, "warehouses", values["warehouse_id"])["kind"] == "store",
            "Perjanjian titipan untuk gudang toko",
        )
    if name == "fiscal_periods":
        start = dt.date.fromisoformat(str(values["start_date"]))
        end = dt.date.fromisoformat(str(values["end_date"]))
        need(start <= end, "Tanggal periode terbalik")
        need(
            values.get("status", "open") == "open",
            "Penutupan melalui tindakan tutup periode",
        )
        need(
            not any(
                r["id"] != id and r["start_date"] <= end and r["end_date"] >= start
                for r in rows(c, name)
            ),
            "Periode bertumpang tindih",
        )
        values.update(
            status="open", closed_at=None, closed_by=None, closing_document_id=None
        )
    if id:
        update(c, name, id, **values)
        r = require(c, name, id)
    else:
        r = insert(c, name, values)
    if name == "products" and not old:
        insert(
            c,
            "product_uoms",
            dict(
                product_id=r["id"],
                uom_id=r["base_uom_id"],
                factor_to_base=1,
                barcode=None,
                is_base=True,
                allow_sale=r["is_saleable"],
                allow_purchase=r["is_purchasable"],
                active=True,
            ),
        )
    audit(c, actor, name, r["id"], "update" if old else "create", before=old, after=r)
    return r


def remove(c, actor, name, id):
    need(
        name in EDITABLE,
        "Penghapusan tidak tersedia untuk ledger / dokumen posted",
        403,
    )
    allowed(c, actor, "master")
    r = require(c, name, id)
    if "active" in r:
        update(c, name, id, active=False)
        action = "deactivate"
    else:
        c.execute(T[name].delete().where(T[name].c.id == id))
        action = "delete_unreferenced"
    audit(c, actor, name, id, action, before=r)
    return {"id": id, "action": action}


def schedule(c, actor, p):
    schedule = require(c, "production_schedules", p["schedule_id"])
    need(
        p.get("cutoff_time") and p.get("delivery_time"),
        "Jam cutoff H-1 dan pengiriman wajib diisi",
    )
    versions = rows(c, "schedule_versions", schedule_id=schedule["id"])
    r = insert(
        c,
        "schedule_versions",
        dict(
            schedule_id=schedule["id"],
            version=max([x["version"] for x in versions], default=0) + 1,
            cutoff_day_offset=1,
            cutoff_time=p["cutoff_time"],
            delivery_time=p["delivery_time"],
            effective_from=p["effective_from"],
            effective_to=p.get("effective_to"),
        ),
    )
    audit(c, actor, "schedule_versions", r["id"], "new_version", after=r)
    return r


def bom(c, actor, p):
    product = require(c, "products", p["product_id"])
    purpose = p["purpose"]
    need(purpose in ("production", "package"), "Jenis resep tidak valid")
    need(
        product["is_phantom"] if purpose == "package" else product["is_manufacturable"],
        "Jenis produk tidak sesuai resep",
    )
    previous = rows(c, "boms", product_id=product["id"], purpose=purpose)
    r = insert(
        c,
        "boms",
        dict(
            product_id=product["id"],
            version=max([b["version"] for b in previous], default=0) + 1,
            purpose=purpose,
            kitchen_id=p.get("kitchen_id"),
            output_qty_base=dec(p["output_quantity"], True),
            valid_from=p["valid_from"],
            valid_to=p.get("valid_to"),
            active=True,
        ),
    )
    need(p.get("lines"), "Bahan / komponen resep wajib")
    for i, a in enumerate(p["lines"]):
        cp, u = unit(c, a["product_id"], a.get("uom_id"))
        need(
            not cp["is_phantom"] and cp["id"] != product["id"],
            "Resep tidak boleh memakai paket atau dirinya sendiri",
        )
        q = dec(a["quantity"], True)
        insert(
            c,
            "bom_lines",
            dict(
                bom_id=r["id"],
                component_product_id=cp["id"],
                qty_input=q,
                uom_id=u["uom_id"],
                factor_snapshot=u["factor_to_base"],
                qty_base=q * u["factor_to_base"],
                source_warehouse_id=a.get("warehouse_id"),
                sequence=i + 1,
            ),
        )
    for a in p.get("byproducts", []):
        insert(
            c,
            "bom_byproducts",
            dict(
                bom_id=r["id"],
                product_id=a["product_id"],
                expected_qty_base=dec(a.get("quantity", 0)),
                cost_policy="zero",
            ),
        )
    for prev in previous:
        update(c, "boms", prev["id"], active=False)
    audit(c, actor, "boms", r["id"], "new_version", after=r)
    return r


def rule(c, actor, p):
    need(
        not p.get("conditions"),
        "Kondisi tambahan belum didukung; gunakan batas nominal dan langkah penyetuju",
    )
    if p.get("min_amount") is not None:
        dec(p["min_amount"])
    if p.get("max_amount") is not None:
        dec(p["max_amount"])
    if p.get("min_amount") is not None and p.get("max_amount") is not None:
        need(dec(p["min_amount"]) <= dec(p["max_amount"]), "Rentang nominal terbalik")
    need(p.get("steps"), "Minimal satu langkah persetujuan")
    previous = rows(c, "approval_rules", action_code=p["action_code"])
    r = insert(
        c,
        "approval_rules",
        dict(
            action_code=p["action_code"],
            version=max([a["version"] for a in previous], default=0) + 1,
            min_amount=p.get("min_amount"),
            max_amount=p.get("max_amount"),
            conditions=p.get("conditions", {}),
            offline_allowed=p.get("offline_allowed", False),
            effective_from=now(),
            active=True,
        ),
    )
    for i, s in enumerate(p["steps"]):
        need(
            bool(s.get("user_id")) != bool(s.get("role_id")),
            "Pilih pengguna atau peran penyetuju",
        )
        need(int(s.get("required_count", 1)) >= 1, "Jumlah penyetuju minimal satu")
        insert(
            c,
            "approval_steps",
            dict(
                rule_id=r["id"],
                step_no=i + 1,
                approver_user_id=s.get("user_id"),
                approver_role_id=s.get("role_id"),
                required_count=int(s.get("required_count", 1)),
                allow_self_approval=s.get("allow_self_approval", False),
            ),
        )
    for prev in previous:
        update(c, "approval_rules", prev["id"], active=False)
    audit(c, actor, "approval_rules", r["id"], "new_version", after=r)
    return r


def user(c, actor, p, id=None):
    allowed(c, actor, "users")
    need(p.get("password") or id, "Sandi wajib untuk pengguna baru")
    if p.get("password"):
        need(len(p["password"]) >= 12, "Sandi minimal 12 karakter")
    if p.get("pin"):
        need(
            str(p["pin"]).isdigit() and 6 <= len(str(p["pin"])) <= 12,
            "PIN harus 6-12 digit",
        )
    old = require(c, "users", id) if id else None
    values = dict(
        username=p["username"],
        name=p["name"],
        active=p.get("active", True),
        credential_version=old["credential_version"] + 1 if old else 1,
        password_hash=(
            password(p["password"]) if p.get("password") else old["password_hash"]
        ),
        pin_hash=(
            password(str(p["pin"]))
            if p.get("pin")
            else old["pin_hash"] if old else None
        ),
    )
    if id:
        update(c, "users", id, **values)
        r = require(c, "users", id)
        c.execute(T["user_roles"].delete().where(T["user_roles"].c.user_id == id))
    else:
        r = insert(c, "users", values)
    for role in p.get("role_ids", []):
        require(c, "roles", role)
        insert(c, "user_roles", dict(user_id=r["id"], role_id=role))
    audit(
        c,
        actor,
        "users",
        r["id"],
        "credentials_updated",
        after={
            "username": r["username"],
            "role_ids": p.get("role_ids", []),
            "active": r["active"],
        },
    )
    return {"id": r["id"], "username": r["username"]}
