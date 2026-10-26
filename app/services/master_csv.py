"""Reviewed, atomic CSV commands for Backoffice masters.

Preview executes the ordinary master services inside rolled-back savepoints.
Apply repeats validation against the same master snapshot, then commits the file
as one command. A receipt makes a repeated apply return its original result.
"""

import csv
import datetime as dt
import io
import json
import re
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError, DataError
from app.core import *
from app.db import MODEL, coerce
from app.services import master

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
SPECIAL = {"boms", "approval_rules", "schedule_versions"}
TABLES = master.EDITABLE | SPECIAL
READONLY = {
    "id",
    "created_at",
    "company_id",
    "closed_at",
    "closed_by",
    "closing_document_id",
}
VERSIONED = {"taxes", "price_list_items", "promotion_rules", "consignment_agreements"}
KEYS = {
    "products": ("sku",),
    "categories": ("name",),
    "uoms": ("code",),
    "product_uoms": ("product_id", "uom_id"),
    "product_kitchen_routes": ("product_id", "kitchen_id"),
    "replenishment_policies": ("product_id", "warehouse_id"),
    "price_list_items": ("price_list_id", "product_uom_id"),
    "consignment_agreements": ("supplier_id", "product_id", "warehouse_id"),
    "fiscal_periods": ("name",),
    "boms": ("product_id", "purpose", "kitchen_id"),
    "schedule_versions": ("schedule_id",),
    "approval_rules": ("action_code",),
}
BOM_HEADER = [
    "aksi",
    "id",
    "product_sku",
    "purpose",
    "kitchen_code",
    "output_quantity",
    "valid_from",
    "valid_to",
    "active",
]
BOM_DETAIL = ["line_type", "component_sku", "quantity", "uom_code", "warehouse_code"]
RULE_HEADER = [
    "aksi",
    "id",
    "action_code",
    "min_amount",
    "max_amount",
    "offline_allowed",
    "active",
]
RULE_DETAIL = [
    "step_no",
    "approver_user_username",
    "approver_role_code",
    "required_count",
    "allow_self_approval",
]
NULL = "__NULL__"
EMPTY = "__EMPTY__"


def tables_for(c, actor):
    ps = perms(c, actor)
    if "*" not in ps and "master" not in ps:
        return []
    return sorted(
        t
        for t in TABLES
        if (t not in {"roles", "approval_rules"} or "*" in ps or "users" in ps)
        and (t != "chart_of_accounts" or "*" in ps or "finance" in ps)
    )


def authorize(c, actor, name):
    need(name in TABLES, "CSV hanya tersedia untuk master yang didukung", 403)
    allowed(c, actor, "master")
    if name in {"roles", "approval_rules"}:
        allowed(c, actor, "users")
    if name == "chart_of_accounts":
        allowed(c, actor, "finance")


def has_costs(c, actor):
    return bool(perms(c, actor) & {"*", "costs"})


def reference_columns(field, target):
    prefix = field.removesuffix("_id")
    if target == "product_uoms":
        return ["product_sku", "uom_code"]
    if target == "promotion_rules":
        return ["promotion_code", "promotion_version"]
    key = (
        "sku"
        if target == "products"
        else (
            "username"
            if target == "users"
            else (
                "code"
                if any(f["name"] == "code" for f in MODEL[target]["fields"])
                else "name"
            )
        )
    )
    return [prefix + "_" + key]


def columns(name, costs=True):
    if name == "boms":
        return BOM_HEADER + BOM_DETAIL
    if name == "approval_rules":
        return RULE_HEADER + RULE_DETAIL
    out = ["aksi", "id"]
    for f in MODEL[name]["fields"]:
        key = f["name"]
        if key in READONLY or (name == "fiscal_periods" and key == "status"):
            continue
        if not costs and "cost" in key:
            continue
        out.extend(
            reference_columns(key, f["ref"].split(".")[0]) if f["ref"] else [key]
        )
    return list(dict.fromkeys(out))


def risky(value):
    return bool(re.match(r"^[\s]*[=+\-@]", value)) or value.startswith(
        ("\t", "\r", "\n")
    )


def encode_cell(value):
    if value is None:
        return NULL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(clean(value), ensure_ascii=False, separators=(",", ":"))
    value = str(clean(value))
    if value == "":
        return EMPTY
    return (
        "'" + value
        if value.startswith("'") or value in {NULL, EMPTY} or risky(value)
        else value
    )


def decode_cell(value):
    literal = value.startswith("'") and (
        value[1:].startswith("'") or value[1:] in {NULL, EMPTY} or risky(value[1:])
    )
    return (value[1:], True) if literal else (value, False)


def csv_text(headers, records):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(headers)
    for record in records:
        writer.writerow(
            [
                encode_cell(record.get(h, "")) if record.get(h, "") != "" else ""
                for h in headers
            ]
        )
    return "\ufeff" + stream.getvalue()


def display_ref(c, target, row):
    if target == "product_uoms":
        return {
            "product_sku": require(c, "products", row["product_id"])["sku"],
            "uom_code": require(c, "uoms", row["uom_id"])["code"],
        }
    if target == "promotion_rules":
        return {"promotion_code": row["code"], "promotion_version": row["version"]}
    return None


def export_record(c, name, row):
    out = {"aksi": "UPDATE", "id": row["id"]}
    for f in MODEL[name]["fields"]:
        key = f["name"]
        if key in READONLY or (name == "fiscal_periods" and key == "status"):
            continue
        if not f["ref"]:
            out[key] = row[key]
            continue
        target = f["ref"].split(".")[0]
        aliases = reference_columns(key, target)
        if row[key] is None:
            out.update({a: None for a in aliases})
            continue
        related = require(c, target, row[key])
        special = display_ref(c, target, related)
        if special is not None:
            out.update(special)
        else:
            prop = aliases[0].removeprefix(key.removesuffix("_id") + "_")
            value = related[prop]
            matches = rows(c, target, **{prop: value})
            out[aliases[0]] = value if len(matches) == 1 else "id:" + related["id"]
    return out


def bom_rows(c, row):
    base = {
        "aksi": "UPDATE",
        "id": row["id"],
        "product_sku": require(c, "products", row["product_id"])["sku"],
        "purpose": row["purpose"],
        "kitchen_code": (
            require(c, "kitchens", row["kitchen_id"])["code"]
            if row["kitchen_id"]
            else None
        ),
        "output_quantity": row["output_qty_base"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "active": row["active"],
    }
    out = []
    for a in sorted(
        rows(c, "bom_lines", bom_id=row["id"]), key=lambda a: a["sequence"]
    ):
        out.append(
            {
                **base,
                "line_type": "material",
                "component_sku": require(c, "products", a["component_product_id"])[
                    "sku"
                ],
                "quantity": a["qty_input"],
                "uom_code": require(c, "uoms", a["uom_id"])["code"],
                "warehouse_code": (
                    require(c, "warehouses", a["source_warehouse_id"])["code"]
                    if a["source_warehouse_id"]
                    else None
                ),
            }
        )
    for a in rows(c, "bom_byproducts", bom_id=row["id"]):
        product = require(c, "products", a["product_id"])
        out.append(
            {
                **base,
                "line_type": "byproduct",
                "component_sku": product["sku"],
                "quantity": a["expected_qty_base"] or 0,
                "uom_code": require(c, "uoms", product["base_uom_id"])["code"],
                "warehouse_code": None,
            }
        )
    return out or [base]


def rule_rows(c, row):
    base = {
        "aksi": "UPDATE",
        "id": row["id"],
        **{
            k: row[k]
            for k in (
                "action_code",
                "min_amount",
                "max_amount",
                "offline_allowed",
                "active",
            )
        },
    }
    return [
        {
            **base,
            "step_no": a["step_no"],
            "approver_user_username": (
                require(c, "users", a["approver_user_id"])["username"]
                if a["approver_user_id"]
                else None
            ),
            "approver_role_code": (
                require(c, "roles", a["approver_role_id"])["code"]
                if a["approver_role_id"]
                else None
            ),
            "required_count": a["required_count"],
            "allow_self_approval": a["allow_self_approval"],
        }
        for a in sorted(
            rows(c, "approval_steps", rule_id=row["id"]), key=lambda a: a["step_no"]
        )
    ] or [base]


def export(c, actor, name, template=False):
    authorize(c, actor, name)
    headers = columns(name, has_costs(c, actor))
    records = []
    if not template:
        for row in sorted(rows(c, name), key=lambda r: r["id"]):
            records.extend(
                bom_rows(c, row)
                if name == "boms"
                else (
                    rule_rows(c, row)
                    if name == "approval_rules"
                    else [export_record(c, name, row)]
                )
            )
    return csv_text(headers, records)


def normalize_header(name, header):
    aliases = {"aksi": "action", "nama": "name", "aktif": "active"}
    if name == "products":
        aliases.update(
            kode="sku",
            satuan="base_uom_code",
            harga_jual="default_sale_price",
            harga_beli="default_purchase_cost",
        )
    header = header.strip().lower()
    return aliases.get(header, header)


def parse(name, content):
    need(
        isinstance(content, str) and len(content.encode("utf-8")) <= MAX_BYTES,
        "CSV maksimal 5 MB",
    )
    content = content.lstrip("\ufeff")
    need(content.strip(), "File CSV kosong")
    first = content.splitlines()[0]
    delimiter = max((",", ";", "\t"), key=first.count)
    try:
        reader = csv.reader(
            io.StringIO(content, newline=""), delimiter=delimiter, strict=True
        )
        raw_headers = next(reader)
        headers = [normalize_header(name, h) for h in raw_headers]
        need(len(set(headers)) == len(headers), "Nama kolom CSV duplikat")
        allowed_headers = set(columns(name)) | {"action", "id"}
        if name not in {"boms", "approval_rules"}:
            allowed_headers.update(
                f["name"] for f in MODEL[name]["fields"] if f["name"] not in READONLY
            )
        need(
            "action" in headers,
            "Kolom aksi wajib diisi: CREATE, UPDATE, NEW_VERSION, DEACTIVATE atau DELETE",
        )
        unknown = set(headers) - allowed_headers
        need(not unknown, "Kolom tidak dikenal: " + ", ".join(sorted(unknown)))
        need(
            not (set(headers) & (READONLY - {"id"})), "Kolom sistem tidak boleh diimpor"
        )
        parsed = []
        last_line = reader.line_num
        for values in reader:
            number = last_line + 1
            last_line = reader.line_num
            if not any(v.strip() for v in values):
                continue
            need(
                len(parsed) < MAX_ROWS,
                "CSV maksimal 5000 baris; pecah menjadi beberapa file",
            )
            parsed.append(
                {
                    "line": number,
                    "data": dict(zip(headers, values)),
                    "parse_error": (
                        "Jumlah kolom tidak sesuai header"
                        if len(values) != len(headers)
                        else None
                    ),
                }
            )
    except (csv.Error, StopIteration) as error:
        raise BusinessError("Format CSV tidak valid: " + str(error))
    need(parsed, "CSV belum mempunyai baris data")
    return parsed


def nonblank(data, key):
    return key in data and data[key] != ""


def raw_value(value):
    value, literal = decode_cell(value)
    if not literal and value == NULL:
        return None
    if not literal and value == EMPTY:
        return ""
    return value


def lookup(c, name, prop, value):
    value = str(value).strip()
    if value.startswith("id:"):
        return require(c, name, value[3:])
    matches = rows(c, name, **{prop: value})
    if not matches:
        matches = [
            a for a in rows(c, name) if str(a[prop]).casefold() == value.casefold()
        ]
    need(matches, f"Referensi {name}.{prop} '{value}' tidak ditemukan")
    need(
        len(matches) == 1,
        f"Referensi {name}.{prop} '{value}' ambigu; gunakan id:<identitas>",
    )
    return matches[0]


def resolve(c, field, target, data):
    aliases = reference_columns(field, target)
    if nonblank(data, field):
        value = raw_value(data[field])
        direct = require(c, target, value)["id"] if value is not None else None
        if any(nonblank(data, a) for a in aliases):
            indirect = resolve(
                c, field, target, {k: v for k, v in data.items() if k != field}
            )
            need(direct == indirect, "ID dan kode referensi berbeda: " + field)
        return direct
    values = [raw_value(data[a]) for a in aliases if nonblank(data, a)]
    need(values, "Referensi belum diisi: " + "/".join(aliases))
    if all(v is None for v in values):
        return None
    if target == "product_uoms":
        need(
            all(nonblank(data, a) for a in aliases),
            "SKU dan satuan produk wajib diisi bersama",
        )
        product = lookup(c, "products", "sku", raw_value(data["product_sku"]))
        uom = lookup(c, "uoms", "code", raw_value(data["uom_code"]))
        matches = rows(c, target, product_id=product["id"], uom_id=uom["id"])
    elif target == "promotion_rules":
        need(nonblank(data, "promotion_code"), "Kode promosi wajib diisi")
        matches = rows(c, target, code=raw_value(data["promotion_code"]))
        if nonblank(data, "promotion_version"):
            version = int(raw_value(data["promotion_version"]))
            matches = [r for r in matches if r["version"] == version]
        elif matches:
            matches = [max(matches, key=lambda r: r["version"])]
    else:
        prop = aliases[0].removeprefix(field.removesuffix("_id") + "_")
        return lookup(c, target, prop, values[0])["id"]
    need(
        len(matches) == 1, "Referensi tidak ditemukan atau ambigu: " + "/".join(aliases)
    )
    return matches[0]["id"]


def typed(name, field, value):
    spec = next(f for f in MODEL[name]["fields"] if f["name"] == field)
    value = raw_value(value)
    if value is None:
        need(spec["nullable"], field + " tidak boleh NULL")
        return None
    typ = spec["type"]
    if typ == "boolean":
        need(
            str(value).strip().lower() in {"true", "false", "1", "0", "ya", "tidak"},
            field + " harus true/false",
        )
        return str(value).strip().lower() in {"true", "1", "ya"}
    if typ == "jsonb":
        return json.loads(value)
    if typ.startswith("decimal"):
        number = dec(value)
        precision, scale = map(int, re.findall(r"\d+", typ))
        need(
            number < Decimal(10) ** (precision - scale)
            and number == number.quantize(Decimal(10) ** -scale),
            field + " melampaui ketelitian angka",
        )
        return number
    if typ in {"int", "bigint"}:
        number = Decimal(value)
        need(
            number.is_finite()
            and number == number.to_integral_value()
            and abs(number) <= 2147483647,
            field + " harus bilangan bulat yang valid",
        )
        return int(number)
    if typ.startswith(("varchar", "char")):
        need(len(value) <= int(re.search(r"\d+", typ)[0]), field + " terlalu panjang")
    return coerce(T[name].c[field], value)


def values_for(c, actor, name, data):
    out = {}
    for f in MODEL[name]["fields"]:
        key = f["name"]
        if key in READONLY:
            continue
        if not has_costs(c, actor) and "cost" in key and nonblank(data, key):
            raise BusinessError("Hak costs diperlukan untuk mengubah " + key, 403)
        if f["ref"]:
            target = f["ref"].split(".")[0]
            if any(nonblank(data, k) for k in [key] + reference_columns(key, target)):
                out[key] = resolve(c, key, target, data)
                need(out[key] is not None or f["nullable"], key + " wajib diisi")
        elif nonblank(data, key):
            out[key] = typed(name, key, data[key])
    return out


def target(c, name, data, values):
    if nonblank(data, "id"):
        return require(c, name, raw_value(data["id"]))
    keys = KEYS.get(name, ("code",))
    need(
        all(k in values for k in keys if k != "kitchen_id"),
        "Isi id atau kunci master: " + ", ".join(keys),
    )
    candidates = rows(c, name, **{k: values.get(k) for k in keys})
    if name in {
        "boms",
        "approval_rules",
        "schedule_versions",
        "taxes",
        "promotion_rules",
        "consignment_agreements",
    }:
        if "version" in values:
            candidates = [r for r in candidates if r["version"] == values["version"]]
        elif candidates:
            candidates = [max(candidates, key=lambda r: r["version"])]
    elif name == "price_list_items" and candidates:
        if "valid_from" in values:
            exact = [
                r
                for r in candidates
                if as_utc(r["valid_from"]) == as_utc(values["valid_from"])
            ]
            candidates = exact or [
                max(candidates, key=lambda r: as_utc(r["valid_from"]))
            ]
        else:
            candidates = [max(candidates, key=lambda r: as_utc(r["valid_from"]))]
    need(len(candidates) <= 1, "Kunci master ambigu; isi kolom id dari hasil ekspor")
    return candidates[0] if candidates else None


def business_key(name, row):
    return " / ".join(str(row.get(k, "")) for k in KEYS.get(name, ("code",)))


def validate_values(c, name, values, creating=False):
    for f in MODEL[name]["fields"]:
        key = f["name"]
        if creating and key not in READONLY and not f["nullable"]:
            required = (
                bool(f["ref"])
                or f["type"] in {"date", "time", "timestamptz"}
                or key in {"sku", "code", "name"}
            )
            if name == "price_list_items" and key == "valid_from":
                required = False
            need(
                not required
                or (
                    key in values
                    and values[key] is not None
                    and str(values[key]).strip()
                ),
                key + " wajib diisi",
            )
        if key in values and values[key] is None:
            need(f["nullable"], key + " wajib diisi")
        if (
            not f["nullable"]
            and key in values
            and f["type"].startswith(("varchar", "text"))
        ):
            need(str(values[key]).strip(), key + " wajib diisi")
    if name == "roles":
        need(
            isinstance(values.get("permissions"), list)
            and all(isinstance(v, str) for v in values["permissions"]),
            "permissions harus daftar JSON kode hak akses",
        )
    if name == "taxes":
        need(0 <= dec(values.get("rate", 0)) <= 1, "Tarif pajak harus pecahan 0..1")
    if name == "promotion_rules":
        need(not values.get("conditions"), "Kondisi promosi tambahan belum didukung")


def changes(before, after):
    before, after = clean(before or {}), clean(after or {})
    return [
        {"field": key, "before": before.get(key), "after": after.get(key)}
        for key in sorted(set(before) | set(after))
        if key not in {"id", "created_at"} and before.get(key) != after.get(key)
    ]


def remove(c, actor, name, old):
    if "active" in old:
        if not old["active"]:
            return old, "UNCHANGED"
        update(c, name, old["id"], active=False)
        result = require(c, name, old["id"])
        audit(c, actor, name, old["id"], "deactivate", before=old, after=result)
        return result, "DEACTIVATE"
    need(
        name not in VERSIONED | SPECIAL,
        "Riwayat master berversi dipertahankan; buat versi baru",
    )
    if name == "fiscal_periods":
        need(old["status"] == "open", "Periode tertutup tidak dapat dihapus")
    master.remove(c, actor, name, old["id"])
    return None, "DELETE"


def regular(c, actor, name, data, action, context):
    values = values_for(c, actor, name, data)
    old = target(c, name, data, values)
    if action == "CREATE":
        need(not nonblank(data, "id"), "Kosongkan id untuk CREATE")
        need(old is None or name in VERSIONED, "Kode master sudah ada; gunakan UPDATE")
    else:
        need(old, "Master belum ditemukan; gunakan CREATE untuk data baru")
    if action in {"DELETE", "DEACTIVATE"}:
        result, operation = remove(c, actor, name, old)
        return old, result, operation
    if old and action != "CREATE":
        merged = {**old, **values}
        need(
            values.get("version", old.get("version")) == old.get("version"),
            "Nomor versi dibuat otomatis; gunakan versi asal untuk memilih master",
        )
        if not changes(old, merged) and action != "NEW_VERSION":
            return old, old, "UNCHANGED"
    else:
        merged = values
    validate_values(c, name, merged, creating=not old or action == "CREATE")
    if name == "consignment_agreements":
        need(
            has_costs(c, actor),
            "Hak costs diperlukan untuk impor perjanjian titipan",
            403,
        )
    if name in VERSIONED:
        prepared = {k: v for k, v in merged.items() if k not in {"id", "created_at"}}
        keys = KEYS.get(name, ("code",))
        family = rows(c, name, **{k: prepared.get(k) for k in keys})
        if name == "price_list_items":
            start = prepared.get("valid_from", context["effective_at"])
            if (
                old
                and action != "CREATE"
                and as_utc(start) == as_utc(old["valid_from"])
            ):
                start = max(
                    as_utc(context["effective_at"]),
                    as_utc(old["valid_from"]) + dt.timedelta(microseconds=1),
                )
            if old and action != "CREATE":
                need(
                    as_utc(start) > as_utc(old["valid_from"]),
                    "Versi harga baru harus mulai setelah versi asal",
                )
            need(
                not any(as_utc(r["valid_from"]) == as_utc(start) for r in family),
                "Versi harga pada waktu tersebut sudah ada",
            )
            prepared["valid_from"] = start
            need(
                not prepared.get("valid_to")
                or as_utc(prepared["valid_to"]) > as_utc(start),
                "Akhir harga harus setelah awal versi baru",
            )
        else:
            version = max([r["version"] for r in family], default=0) + 1
            if action == "CREATE" and "version" in values:
                need(
                    values["version"] == version,
                    "Versi CREATE berikutnya harus " + str(version),
                )
            prepared["version"] = version
        result = master.save(c, actor, name, prepared)
        if old and name in {"promotion_rules", "consignment_agreements"}:
            update(c, name, old["id"], active=False)
            audit(
                c,
                actor,
                name,
                old["id"],
                "superseded",
                before=old,
                after={"active": False, "successor_id": result["id"]},
            )
        return (
            old,
            require(c, name, result["id"]),
            "NEW_VERSION" if family else "CREATE",
        )
    need(action != "NEW_VERSION", "Master ini memakai UPDATE, bukan NEW_VERSION")
    if not old or action == "CREATE":
        if any(f["name"] == "company_id" for f in MODEL[name]["fields"]):
            values["company_id"] = rows(c, "companies")[0]["id"]
        if name == "fiscal_periods":
            values.setdefault("status", "open")
        result = master.save(c, actor, name, values)
        return None, require(c, name, result["id"]), "CREATE"
    result = master.save(c, actor, name, values, old["id"])
    return old, result, "UPDATE"


def grouped(name, parsed):
    if name not in {"boms", "approval_rules"}:
        return [
            {
                "lines": [r["line"]],
                "rows": [r],
                "data": r["data"],
                "parse_error": r["parse_error"],
            }
            for r in parsed
        ]
    result = {}
    head = BOM_HEADER if name == "boms" else RULE_HEADER
    for r in parsed:
        data = r["data"]
        identity = (
            data.get("id")
            or (
                data.get("product_sku", ""),
                data.get("purpose", ""),
                data.get("kitchen_code", ""),
            )
            if name == "boms"
            else data.get("id") or data.get("action_code", "")
        )
        key = str(identity)
        if key not in result:
            result[key] = {"lines": [], "rows": [], "data": data, "parse_error": None}
        group = result[key]
        group["lines"].append(r["line"])
        group["rows"].append(r)
        if r["parse_error"]:
            group["parse_error"] = r["parse_error"]
        for col in [normalize_header(name, h) for h in head]:
            if data.get(col, "") != group["data"].get(col, ""):
                group["parse_error"] = (
                    "Header resep/aturan berbeda pada kelompok yang sama: " + col
                )
    return list(result.values())


def special(c, actor, name, group, action):
    data = group["data"]
    if name == "schedule_versions":
        values = values_for(c, actor, name, data)
        old = target(c, name, data, values)
        if action == "CREATE":
            need(not nonblank(data, "id"), "Kosongkan id untuk CREATE")
        else:
            need(old, "Versi jadwal tidak ditemukan")
        need(
            action not in {"DELETE", "DEACTIVATE"},
            "Riwayat jadwal dipertahankan; buat versi baru",
        )
        if (
            old
            and action != "CREATE"
            and not changes(old, {**old, **values})
            and action != "NEW_VERSION"
        ):
            return old, old, "UNCHANGED"
        params = {**(old or {}), **values}
        need(params.get("cutoff_day_offset", 1) == 1, "Batas pesanan tetap H-1")
        result = master.schedule(c, actor, params)
        return old, result, "NEW_VERSION" if old else "CREATE"
    if name == "boms":
        values = {}
        if nonblank(data, "product_sku"):
            values["product_id"] = lookup(
                c, "products", "sku", raw_value(data["product_sku"])
            )["id"]
        if nonblank(data, "purpose"):
            values["purpose"] = raw_value(data["purpose"])
        values["kitchen_id"] = (
            lookup(c, "kitchens", "code", raw_value(data["kitchen_code"]))["id"]
            if nonblank(data, "kitchen_code")
            and raw_value(data["kitchen_code"]) is not None
            else None
        )
    else:
        values = values_for(c, actor, name, data)
    old = target(c, name, data, values)
    if action == "CREATE":
        need(
            not nonblank(data, "id") and not old,
            "Resep/aturan sudah ada; gunakan UPDATE atau NEW_VERSION",
        )
    else:
        need(old, "Resep/aturan tidak ditemukan")
    if action in {"DELETE", "DEACTIVATE"}:
        result, operation = remove(c, actor, name, old)
        return old, result, operation
    if name == "boms":
        params = {**(old or {}), **values}
        params["output_quantity"] = dec(
            raw_value(data.get("output_quantity", "")), True
        )
        params["valid_from"] = dt.date.fromisoformat(
            raw_value(data.get("valid_from", ""))
        )
        params["valid_to"] = (
            dt.date.fromisoformat(raw_value(data["valid_to"]))
            if nonblank(data, "valid_to") and raw_value(data["valid_to"]) is not None
            else None
        )
        materials, byproducts = [], []
        for r in group["rows"]:
            a = r["data"]
            product = lookup(
                c, "products", "sku", raw_value(a.get("component_sku", ""))
            )
            quantity = dec(
                raw_value(a.get("quantity", "")),
                a.get("line_type", "material") != "byproduct",
            )
            typ = a.get("line_type") or "material"
            need(
                typ in {"material", "byproduct"},
                "line_type harus material atau byproduct",
            )
            uom_id = (
                lookup(c, "uoms", "code", raw_value(a["uom_code"]))["id"]
                if nonblank(a, "uom_code")
                else product["base_uom_id"]
            )
            if typ == "byproduct":
                need(
                    uom_id == product["base_uom_id"],
                    "Produk turunan memakai satuan dasar",
                )
                byproducts.append({"product_id": product["id"], "quantity": quantity})
            else:
                warehouse_id = (
                    lookup(c, "warehouses", "code", raw_value(a["warehouse_code"]))[
                        "id"
                    ]
                    if nonblank(a, "warehouse_code")
                    and raw_value(a["warehouse_code"]) is not None
                    else None
                )
                materials.append(
                    {
                        "product_id": product["id"],
                        "quantity": quantity,
                        "uom_id": uom_id,
                        "warehouse_id": warehouse_id,
                    }
                )
        params.update(lines=materials, byproducts=byproducts)
        if old and nonblank(data, "active"):
            need(
                typed("boms", "active", data["active"]) == old["active"],
                "Gunakan DEACTIVATE untuk menonaktifkan resep",
            )
        before = bom_rows(c, old) if old else []
        result = master.bom(c, actor, params)
        after = bom_rows(c, require(c, name, result["id"]))
        # IDs are allocation details; unchanged export must not create a new version.
        compare = lambda rs: [
            {k: clean(v) for k, v in row.items() if k not in {"id", "aksi", "active"}}
            for row in rs
        ]
        if old and action == "UPDATE" and compare(before) == compare(after):
            return {"recipe": before}, {"recipe": before}, "UNCHANGED"
        return (
            {"recipe": before} if old else None,
            {"recipe": after},
            "NEW_VERSION" if old else "CREATE",
        )
    params = {**(old or {}), **values}
    steps = []
    ordered = sorted(group["rows"], key=lambda r: int(r["data"].get("step_no") or 1))
    numbers = []
    for i, r in enumerate(ordered):
        a = r["data"]
        numbers.append(int(a.get("step_no") or i + 1))
        user_id = (
            lookup(c, "users", "username", raw_value(a["approver_user_username"]))["id"]
            if nonblank(a, "approver_user_username")
            and raw_value(a["approver_user_username"]) is not None
            else None
        )
        role_id = (
            lookup(c, "roles", "code", raw_value(a["approver_role_code"]))["id"]
            if nonblank(a, "approver_role_code")
            and raw_value(a["approver_role_code"]) is not None
            else None
        )
        steps.append(
            {
                "user_id": user_id,
                "role_id": role_id,
                "required_count": int(a.get("required_count") or 1),
                "allow_self_approval": typed(
                    "approval_steps",
                    "allow_self_approval",
                    a.get("allow_self_approval") or "false",
                ),
            }
        )
    need(numbers == list(range(1, len(steps) + 1)), "step_no harus berurutan mulai 1")
    params["steps"] = steps
    if old and nonblank(data, "active"):
        need(
            typed("approval_rules", "active", data["active"]) == old["active"],
            "Gunakan DEACTIVATE untuk menonaktifkan aturan",
        )
    before = rule_rows(c, old) if old else []
    result = master.rule(c, actor, params)
    after = rule_rows(c, require(c, name, result["id"]))
    compare = lambda rs: [
        {k: clean(v) for k, v in row.items() if k not in {"id", "aksi", "active"}}
        for row in rs
    ]
    if old and action == "UPDATE" and compare(before) == compare(after):
        return {"rule": before}, {"rule": before}, "UNCHANGED"
    return (
        {"rule": before} if old else None,
        {"rule": after},
        "NEW_VERSION" if old else "CREATE",
    )


def state_hash(c, name):
    dependencies = {name}
    if name == "boms":
        dependencies.update({"bom_lines", "bom_byproducts", "product_uoms"})
    if name == "approval_rules":
        dependencies.add("approval_steps")
    while True:
        before = set(dependencies)
        for table in list(dependencies):
            dependencies.update(
                f["ref"].split(".")[0]
                for f in MODEL[table]["fields"]
                if f["ref"] and f["name"] not in {"closed_by", "closing_document_id"}
            )
        if before == dependencies:
            break
    snapshot = {}
    for table in sorted(dependencies):
        items = sorted(rows(c, table), key=lambda r: r["id"])
        if table == "users":
            items = [
                {k: r[k] for k in ("id", "username", "active", "credential_version")}
                for r in items
            ]
        snapshot[table] = items
    return digest(snapshot)


def execute(c, actor, name, content, context, validation=False):
    parsed = parse(name, content)
    reports, seen = [], set()
    for group in grouped(name, parsed):
        data = group["data"]
        row = {
            "line": group["lines"][0],
            "line_numbers": group["lines"],
            "action": data.get("action", "").strip().upper(),
            "key": data.get("sku")
            or data.get("code")
            or data.get("product_sku")
            or data.get("action_code")
            or data.get("name")
            or data.get("id")
            or "",
            "changes": [],
        }
        transaction = c.begin_nested()
        try:
            need(not group["parse_error"], group["parse_error"])
            action = row["action"]
            need(
                action in {"CREATE", "UPDATE", "NEW_VERSION", "DEACTIVATE", "DELETE"},
                "Aksi tidak dikenal",
            )
            identity = raw_value(data["id"]) if nonblank(data, "id") else None
            if identity:
                need(identity not in seen, "Master yang sama muncul lebih dari sekali")
                seen.add(identity)
            before, after, operation = (
                special(c, actor, name, group, action)
                if name in SPECIAL
                else regular(c, actor, name, data, action, context)
            )
            row.update(
                status="valid", operation=operation, changes=changes(before, after)
            )
            if operation == "UNCHANGED":
                transaction.rollback()
            else:
                transaction.commit()
        except (
            BusinessError,
            ValueError,
            KeyError,
            TypeError,
            InvalidOperation,
            IntegrityError,
            DataError,
        ) as error:
            transaction.rollback()
            message = (
                error.message
                if isinstance(error, BusinessError)
                else (
                    "Data duplikat, masih dipakai, atau referensi wajib tidak valid"
                    if isinstance(error, (IntegrityError, DataError))
                    else str(error)
                )
            )
            row.update(status="error", operation="ERROR", error=message)
            if not validation:
                raise BusinessError(f"Baris {row['line']}: {message}", 409)
        reports.append(row)
    return reports, len(parsed)


def preview(c, actor, name, content):
    authorize(c, actor, name)
    fingerprint = state_hash(c, name)
    context = {"effective_at": now().isoformat()}
    transaction = c.begin_nested()
    try:
        reports, count = execute(c, actor, name, content, context, True)
    finally:
        transaction.rollback()
    summary = {
        k: sum(1 for r in reports if r["operation"] == k)
        for k in (
            "CREATE",
            "UPDATE",
            "NEW_VERSION",
            "DEACTIVATE",
            "DELETE",
            "UNCHANGED",
            "ERROR",
        )
    }
    result = {
        "valid": summary["ERROR"] == 0,
        "csv_rows": count,
        "records": len(reports),
        "summary": summary,
        "rows": reports,
        "preview_id": None,
    }
    if result["valid"]:
        token = uid()
        insert(
            c,
            "app_commands",
            {
                "id": "csv-preview:" + token,
                "fingerprint": fingerprint,
                "created_at": now(),
                "result": {
                    "actor_id": actor,
                    "table": name,
                    "status": "pending",
                    "expires_at": (now() + dt.timedelta(minutes=30)).isoformat(),
                    "content": content,
                    "context": context,
                },
            },
        )
        result["preview_id"] = token
    return result


def apply(c, actor, name, token):
    authorize(c, actor, name)
    receipt = get(c, "app_commands", "csv-preview:" + str(token))
    need(receipt, "Pratinjau tidak ditemukan; unggah file kembali", 404)
    plan = receipt["result"]
    need(
        plan["actor_id"] == actor and plan["table"] == name,
        "Pratinjau bukan milik pengguna/master ini",
        403,
    )
    if plan["status"] == "applied":
        return plan["applied_result"]
    need(
        as_utc(plan["expires_at"]) > now(),
        "Pratinjau kedaluwarsa; periksa file kembali",
        409,
    )
    need(
        state_hash(c, name) == receipt["fingerprint"],
        "Master berubah setelah pratinjau; unggah dan periksa ulang",
        409,
    )
    reports, count = execute(c, actor, name, plan["content"], plan["context"])
    result = {
        "status": "applied",
        "preview_id": token,
        "csv_rows": count,
        "records": len(reports),
        "summary": {
            k: sum(1 for r in reports if r["operation"] == k)
            for k in (
                "CREATE",
                "UPDATE",
                "NEW_VERSION",
                "DEACTIVATE",
                "DELETE",
                "UNCHANGED",
            )
        },
    }
    audit(c, actor, "csv_imports", token, "apply", after={"table": name, **result})
    update(
        c,
        "app_commands",
        receipt["id"],
        result={
            "actor_id": actor,
            "table": name,
            "status": "applied",
            "applied_result": result,
        },
    )
    return result
