"""Versioned approvals, bound to document revisions and explicit permissions."""

from app.core import *


def subject_amount(c, document_id, action):
    """Use server-owned document values, never a caller's claimed nominal."""
    d = document(c, document_id)
    kind = d["document_type"]
    if kind == "PO":
        return require(c, "purchase_orders", document_id)["original_total"]
    if kind == "SO":
        return require(c, "sales_orders", document_id)["total"]
    if kind == "ADJUSTMENT":
        return sum(
            (
                abs(a["qty_delta"] * a["unit_cost"])
                for a in rows(
                    c, "inventory_adjustment_lines", adjustment_id=document_id
                )
            ),
            ZERO,
        )
    if kind == "RETURN":
        return sum(
            (
                a["refund_basis_amount"]
                for a in rows(c, "return_lines", return_id=document_id)
            ),
            ZERO,
        )
    if kind == "POS_SALE":
        return require(c, "pos_sales", document_id)["discount_total"]
    if kind == "TRANSFER":
        return sum(
            (
                a["qty_dispatched"] * a["unit_cost_snapshot"]
                for a in rows(c, "transfer_lines", transfer_id=document_id)
            ),
            ZERO,
        )
    if kind == "WO":
        return sum(
            (
                a["issued_qty_base"] * a["unit_cost_snapshot"]
                for a in rows(
                    c, "production_materials", production_order_id=document_id
                )
            ),
            ZERO,
        )
    return ZERO


def in_range(rule, amount):
    return (rule["min_amount"] is None or amount >= dec(rule["min_amount"])) and (
        rule["max_amount"] is None or amount <= dec(rule["max_amount"])
    )


def request(c, actor, document_id, action, reason, amount=None):
    d = document(c, document_id)
    if (
        d["document_type"] == "SO"
        and d["status"] == "confirmed"
        and action == "production_addition"
    ):
        need(
            amount is not None,
            "Gunakan usulan penambahan SO agar jumlah yang disetujui tercatat",
        )
    amount = subject_amount(c, document_id, action) if amount is None else dec(amount)
    rules = [
        r
        for r in rows(c, "approval_rules", action_code=action)
        if r["active"] and as_utc(r["effective_from"]) <= now() and in_range(r, amount)
    ]
    need(rules, "Aturan persetujuan belum dikonfigurasi untuk " + action)
    r = max(rules, key=lambda a: a["version"])
    steps = rows(c, "approval_steps", rule_id=r["id"])
    need(steps, "Langkah penyetuju belum diisi")
    existing = [
        q
        for q in rows(
            c,
            "approval_requests",
            document_id=document_id,
            document_revision=d["revision"],
            rule_id=r["id"],
        )
        if q["status"] in ("pending", "approved")
    ]
    if existing:
        return existing[0]
    q = insert(
        c,
        "approval_requests",
        dict(
            document_id=document_id,
            document_revision=d["revision"],
            rule_id=r["id"],
            requested_by=actor,
            status="pending",
            rule_snapshot=clean(
                {"rule": r, "steps": steps, "action": action, "amount": str(amount)}
            ),
            reason=reason,
        ),
    )
    audit(
        c, actor, "approval_requests", q["id"], "request", after=q, document=document_id
    )
    return q


def decide(c, actor, id, decision, reason="", terminal=None):
    q = require(c, "approval_requests", id)
    need(q["status"] == "pending", "Permintaan tidak lagi menunggu", 409)
    d = document(c, q["document_id"])
    need(
        d["revision"] == q["document_revision"],
        "Revisi berubah; ajukan approval ulang",
        409,
    )
    need(decision in ("approve", "reject"), "Keputusan tidak valid")
    steps = sorted(q["rule_snapshot"]["steps"], key=lambda a: a["step_no"])
    done = rows(c, "approval_actions", request_id=id)
    active = None
    for step in steps:
        yes = {
            a["actor_id"]
            for a in done
            if a["step_id"] == step["id"] and a["decision"] == "approve"
        }
        if len(yes) < step["required_count"]:
            active = step
            break
    need(active, "Semua langkah telah selesai", 409)
    roles = {r["role_id"] for r in rows(c, "user_roles", user_id=actor)}
    need(
        active["approver_user_id"] == actor or active["approver_role_id"] in roles,
        "Bukan penyetuju pada langkah ini",
        403,
    )
    need(
        active["allow_self_approval"] or actor != q["requested_by"],
        "Pengaju tidak boleh menyetujui permintaan sendiri",
        403,
    )
    need(
        not any(a["actor_id"] == actor and a["step_id"] == active["id"] for a in done),
        "Keputusan sudah dicatat",
        409,
    )
    user = require(c, "users", actor)
    insert(
        c,
        "approval_actions",
        dict(
            request_id=id,
            step_id=active["id"],
            actor_id=actor,
            terminal_id=terminal,
            decision=decision,
            decided_at=now(),
            credential_version=user["credential_version"],
            evidence={"reason": reason},
        ),
    )
    if decision == "reject":
        update(c, "approval_requests", id, status="rejected")
    else:
        done = rows(c, "approval_actions", request_id=id)
        if all(
            len(
                {
                    a["actor_id"]
                    for a in done
                    if a["step_id"] == s["id"] and a["decision"] == "approve"
                }
            )
            >= s["required_count"]
            for s in steps
        ):
            update(c, "approval_requests", id, status="approved")
    audit(
        c,
        actor,
        "approval_requests",
        id,
        decision,
        after={"reason": reason},
        document=d["id"],
    )
    return require(c, "approval_requests", id)


def approved(c, actor, document_id, action, reason="", amount=None):
    d = document(c, document_id)
    amount = subject_amount(c, document_id, action) if amount is None else dec(amount)
    rr = [
        q
        for q in rows(
            c,
            "approval_requests",
            document_id=document_id,
            document_revision=d["revision"],
        )
        if q["status"] == "approved"
        and q["rule_snapshot"]["action"] == action
        and in_range(q["rule_snapshot"]["rule"], amount)
    ]
    need(rr, "Persetujuan " + action + " untuk revisi ini belum selesai", 409)
    return rr[0]


def invalidate(c, document_id):
    d = document(c, document_id)
    for q in rows(c, "approval_requests", document_id=document_id):
        if q["status"] in ("pending", "approved"):
            update(c, "approval_requests", q["id"], status="superseded")
    update(c, "documents", document_id, revision=d["revision"] + 1)
