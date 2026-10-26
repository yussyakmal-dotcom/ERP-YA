"""Decimal pricing snapshots. Shared vouchers/points are reserved in cloud only."""

from app.core import *


def quote(c, p, replay=False):
    if replay and p.get("_pricing"):
        result = copy_pricing(p["_pricing"])
        return result
    at = p.get("_sold_at") or now()
    day = as_utc(at).astimezone(WIB).date()
    result = []
    subtotal = ZERO
    for a in p["lines"]:
        product, u = unit(c, a["product_id"], a.get("uom_id"))
        q = dec(a["quantity"], True)
        prices = [
            r
            for r in rows(
                c,
                "price_list_items",
                price_list_id=p["price_list_id"],
                product_uom_id=u["id"],
            )
            if valid_at(r, at)
        ]
        price = (
            dec(a["_unit_price"])
            if replay and "_unit_price" in a
            else (
                max(prices, key=lambda r: r["valid_from"])["price"]
                if prices
                else product["default_sale_price"] * u["factor_to_base"]
            )
        )
        amount = money(q * price)
        subtotal += amount
        result.append(
            {
                "product_id": product["id"],
                "quantity": q,
                "unit_price": price,
                "gross_before_discount": amount,
            }
        )
    manual = money(dec(p.get("discount_amount", 0)))
    need(manual <= subtotal, "Diskon melebihi subtotal")
    promo_amount = ZERO
    if p.get("promotion_id"):
        promotion = require(c, "promotion_rules", p["promotion_id"])
        need(promotion["active"] and valid_at(promotion, at), "Promosi tidak berlaku")
        need(
            promotion["scope"] in ("global", "sale"),
            "Promosi item harus memiliki snapshot baris tersendiri",
        )
        value = dec(promotion["value"])
        promo_amount = (
            money((subtotal - manual) * value / 100)
            if promotion["discount_type"] == "percent"
            else money(value)
        )
        promo_amount = min(subtotal - manual, promo_amount)
    hold = p.get("_redemption") or {}
    shared = money(dec(hold.get("amount", 0)))
    need(
        shared <= subtotal - manual - promo_amount,
        "Potongan voucher/poin melebihi nilai belanja",
    )
    discount = manual + promo_amount + shared
    taxid = setting(c, "tax_policy", {}).get(
        "so_tax_id" if p.get("channel") == "so" else "pos_tax_id"
    )
    tax = None
    if taxid:
        tax = require(c, "taxes", taxid)
        need(
            tax["effective_from"] <= day
            and (not tax["effective_to"] or day <= tax["effective_to"]),
            "Konfigurasi pajak sudah tidak berlaku",
        )
        need(tax["output_account_id"], "Akun pajak keluaran belum diisi")
    allocated = ZERO
    tax_total = ZERO
    net_total = ZERO
    total = ZERO
    for i, ln in enumerate(result):
        disc = (
            discount - allocated
            if i == len(result) - 1
            else (
                money(discount * ln["gross_before_discount"] / subtotal)
                if subtotal
                else ZERO
            )
        )
        allocated += disc
        after = ln["gross_before_discount"] - disc
        taxamount = ZERO
        if tax:
            rate = dec(tax["rate"])
            need(rate <= 1, "Tarif pajak disimpan sebagai pecahan 0..1")
            taxamount = (
                money(after - after / (1 + rate))
                if tax["price_inclusive"]
                else money(after * rate)
            )
        gross = after if not tax or tax["price_inclusive"] else after + taxamount
        net = gross - taxamount
        ln.update(
            discount=disc,
            total=gross,
            net=net,
            tax={
                "tax_id": taxid,
                "amount": str(taxamount),
                "rate": str(tax["rate"]) if tax else "0",
                "inclusive": tax["price_inclusive"] if tax else False,
                "output_account_code": (
                    require(c, "chart_of_accounts", tax["output_account_id"])["code"]
                    if tax
                    else None
                ),
            },
        )
        total += gross
        net_total += net
        tax_total += taxamount
    return {
        "subtotal": subtotal,
        "discount": discount,
        "manual_discount": manual,
        "promotion_discount": promo_amount,
        "shared_discount": shared,
        "total": total,
        "net": net_total,
        "tax_total": tax_total,
        "lines": result,
    }


def copy_pricing(snapshot):
    r = dict(snapshot)
    for k in (
        "subtotal",
        "discount",
        "manual_discount",
        "promotion_discount",
        "shared_discount",
        "total",
        "net",
        "tax_total",
    ):
        r[k] = dec(r[k])
    r["lines"] = [
        {
            **ln,
            **{
                k: dec(ln[k])
                for k in (
                    "quantity",
                    "unit_price",
                    "gross_before_discount",
                    "discount",
                    "total",
                    "net",
                )
            },
        }
        for ln in r["lines"]
    ]
    return r


def reserve_redemption(c, terminal, actor, p):
    """A durable hold cannot expire while a terminal may have an offline sale.

    It is released explicitly only before local commit, or consumed by its event.
    This trades availability of an abandoned voucher for no double redemption.
    """
    allowed(c, actor, "pos")
    need(p.get("sale_id"), "Identitas draft penjualan wajib")
    existing = rows(c, "app_redemptions", sale_id=p["sale_id"])
    if existing:
        need(
            existing[0]["terminal_id"] == terminal["id"],
            "Reservasi milik terminal lain",
            403,
        )
        return existing[0]
    amount = ZERO
    voucher = None
    account = None
    points = dec(p.get("points", 0))
    base = dec(p["eligible_amount"])
    customer = p.get("customer_id")
    if p.get("voucher_code"):
        matches = rows(c, "vouchers", code=p["voucher_code"])
        need(matches, "Voucher tidak ditemukan")
        voucher = matches[0]
        need(voucher["active"] and valid_at(voucher), "Voucher tidak berlaku")
        used = len(
            [
                r
                for r in rows(c, "voucher_redemptions", voucher_id=voucher["id"])
                if r["status"] == "applied"
            ]
        ) + len(
            [
                r
                for r in rows(c, "app_redemptions", voucher_id=voucher["id"])
                if r["status"] == "held"
            ]
        )
        need(
            voucher["max_uses"] is None or used < voucher["max_uses"],
            "Kuota voucher habis",
        )
        promo = require(c, "promotion_rules", voucher["promotion_rule_id"])
        need(promo["active"] and valid_at(promo), "Promosi voucher tidak berlaku")
        value = dec(promo["value"])
        amount = min(
            base,
            (
                money(base * value / 100)
                if promo["discount_type"] == "percent"
                else money(value)
            ),
        )
    if points:
        need(customer, "Pelanggan wajib untuk penukaran poin")
        accounts = rows(c, "loyalty_accounts", customer_id=customer)
        need(accounts, "Akun loyalty belum tersedia")
        account = accounts[0]
        need(
            points == points.to_integral_value()
            and points <= account["points_balance"],
            "Saldo poin tidak cukup",
        )
        point_value = dec(setting(c, "loyalty_policy", {}).get("point_value", 0))
        need(point_value > 0, "Nilai poin belum dikonfigurasi")
        need(
            amount + points * point_value <= base,
            "Penukaran poin melebihi sisa belanja",
        )
        amount += points * point_value
        update(
            c,
            "loyalty_accounts",
            account["id"],
            points_balance=account["points_balance"] - points,
            version=account["version"] + 1,
        )
    need(amount > 0, "Tidak ada voucher atau poin yang dapat ditukar")
    return insert(
        c,
        "app_redemptions",
        dict(
            sale_id=p["sale_id"],
            terminal_id=terminal["id"],
            actor_id=actor,
            voucher_id=voucher["id"] if voucher else None,
            loyalty_account_id=account["id"] if account else None,
            customer_id=customer,
            points=points,
            amount=amount,
            status="held",
            created_at=now(),
        ),
    )


def redeem(c, terminal, saleid, hold, local=False):
    if local:
        update(c, "app_redemptions", hold["id"], status="local_committed")
        return
    r = require(c, "app_redemptions", hold["id"])
    need(
        r["terminal_id"] == terminal["id"]
        and r["sale_id"] == saleid
        and r["status"] == "held",
        "Reservasi voucher/poin tidak cocok atau sudah dipakai",
    )
    need(dec(hold["amount"]) == r["amount"], "Nilai reservasi berubah")
    if r["voucher_id"]:
        insert(
            c,
            "voucher_redemptions",
            dict(
                voucher_id=r["voucher_id"],
                sale_document_id=saleid,
                customer_id=r["customer_id"],
                amount=r["amount"],
                status="applied",
                reversal_of_id=None,
            ),
        )
    if r["points"]:
        insert(
            c,
            "loyalty_entries",
            dict(
                account_id=r["loyalty_account_id"],
                source_document_id=saleid,
                kind="redeem",
                points_delta=-r["points"],
                reversal_of_id=None,
            ),
        )
    update(c, "app_redemptions", r["id"], status="applied")


def earn(c, saleid, customer, amount):
    policy = setting(c, "loyalty_policy", {})
    divisor = dec(policy.get("spend_per_point", 0))
    if not customer or divisor <= 0:
        return
    points = (amount / divisor).to_integral_value(rounding="ROUND_FLOOR")
    if points <= 0:
        return
    account = rows(c, "loyalty_accounts", customer_id=customer)
    account = (
        account[0]
        if account
        else insert(
            c,
            "loyalty_accounts",
            dict(customer_id=customer, points_balance=0, version=1),
        )
    )
    update(
        c,
        "loyalty_accounts",
        account["id"],
        points_balance=account["points_balance"] + points,
        version=account["version"] + 1,
    )
    insert(
        c,
        "loyalty_entries",
        dict(
            account_id=account["id"],
            source_document_id=saleid,
            kind="earn",
            points_delta=points,
            reversal_of_id=None,
        ),
    )


def cancel_hold(c, terminal, id):
    r = require(c, "app_redemptions", id)
    need(
        r["terminal_id"] == terminal["id"] and r["status"] == "held",
        "Reservasi tidak dapat dibatalkan",
        409,
    )
    if r["points"]:
        account = require(c, "loyalty_accounts", r["loyalty_account_id"])
        update(
            c,
            "loyalty_accounts",
            account["id"],
            points_balance=account["points_balance"] + r["points"],
            version=account["version"] + 1,
        )
    update(c, "app_redemptions", id, status="released")
    return {"id": id, "status": "released"}


def reverse_earn(c, saleid, returnid, amount):
    """Reverse the sale's earned points cumulatively, including the last point.

    A negative balance is retained if points have already been spent; future
    accruals recover it. Redeemed vouchers/points are not automatically reissued.
    Local replay has no earned entries until cloud recognition, so accrual and
    this reversal both take place once on the authoritative installation.
    """
    sale = require(c, "pos_sales", saleid)
    if sale["total"] <= 0:
        return
    refunded = ZERO
    for ln in rows(c, "pos_sale_lines", pos_sale_id=saleid):
        refunded += sum(
            (
                r["refund_basis_amount"]
                for r in rows(c, "return_lines", pos_sale_line_id=ln["id"])
                if r["return_id"] != returnid
                and document(c, r["return_id"])["status"] == "posted"
            ),
            ZERO,
        )
    for earned in rows(c, "loyalty_entries", source_document_id=saleid, kind="earn"):
        reversed_points = -sum(
            (
                r["points_delta"]
                for r in rows(c, "loyalty_entries", reversal_of_id=earned["id"])
            ),
            ZERO,
        )
        target = (
            min(sale["total"], refunded + amount)
            * earned["points_delta"]
            / sale["total"]
        ).to_integral_value(rounding="ROUND_FLOOR")
        delta = max(ZERO, target - reversed_points)
        if not delta:
            continue
        account = require(c, "loyalty_accounts", earned["account_id"])
        update(
            c,
            "loyalty_accounts",
            account["id"],
            points_balance=account["points_balance"] - delta,
            version=account["version"] + 1,
        )
        insert(
            c,
            "loyalty_entries",
            dict(
                account_id=account["id"],
                source_document_id=returnid,
                kind="earn_return",
                points_delta=-delta,
                reversal_of_id=earned["id"],
            ),
        )
