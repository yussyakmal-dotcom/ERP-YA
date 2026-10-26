"""The published logical model drives both database installations.

Operational writes are serialized per installation for the first release. PostgreSQL
uses a transaction advisory lock; SQLite uses BEGIN IMMEDIATE for local development.
This prioritizes auditable atomic commands over speculative parallel throughput.
"""

import contextlib
import datetime as dt
import json
import os
import re
import threading
import uuid
from zoneinfo import ZoneInfo
from decimal import Decimal
from pathlib import Path
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    create_engine,
    event,
    select,
    text,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "schema/ERD_Model_Yussy_Akmal_v1.0.json").read_text())
metadata = MetaData()
TABLES = {}


def type_for(s):
    if s == "uuid":
        return String(36)
    if s in ("int", "bigint"):
        return Integer()
    if s == "boolean":
        return Boolean()
    if s == "jsonb":
        return JSON()
    if s == "date":
        return Date()
    if s == "time":
        return Time()
    if s == "timestamptz":
        return DateTime(timezone=True)
    if s.startswith("decimal"):
        a, b = map(int, re.findall(r"\d+", s))
        return Numeric(a, b)
    if s.startswith(("varchar", "char")):
        return String(int(re.search(r"\d+", s)[0]))
    return Text()


for name, spec in MODEL.items():
    cols = []
    for f in spec["fields"]:
        args = [f["name"], type_for(f["type"])]
        if f["ref"]:
            args.append(ForeignKey(f["ref"]))
        cols.append(Column(*args, primary_key=f["pk"], nullable=f["nullable"]))
    TABLES[name] = Table(
        name,
        metadata,
        *cols,
        *[
            UniqueConstraint(*keys, name="uq_" + name + "_" + str(i))
            for i, keys in enumerate(spec["unique"])
        ],
    )

# Infrastructure tables extend, rather than replace, the 104 business entities.
Table(
    "app_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id"), nullable=False),
    Column("csrf", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
Table(
    "app_tokens",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("terminal_id", String(36), ForeignKey("pos_terminals.id"), nullable=False),
    Column("active", Boolean, nullable=False),
)
Table(
    "app_commands",
    metadata,
    Column("id", String(160), primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("result", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Table(
    "app_security",
    metadata,
    Column("id", String(150), primary_key=True),
    Column("failures", Integer, nullable=False),
    Column("blocked_until", DateTime(timezone=True)),
)
Table(
    "app_schema_versions",
    metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)
Table(
    "app_redemptions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("sale_id", String(36), unique=True, nullable=False),
    Column("terminal_id", String(36), ForeignKey("pos_terminals.id"), nullable=False),
    Column("actor_id", String(36), ForeignKey("users.id"), nullable=False),
    Column("voucher_id", String(36), ForeignKey("vouchers.id")),
    Column("loyalty_account_id", String(36), ForeignKey("loyalty_accounts.id")),
    Column("customer_id", String(36), ForeignKey("customers.id")),
    Column("points", Numeric(20, 4), nullable=False),
    Column("amount", Numeric(20, 4), nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
TABLES.update({k: v for k, v in metadata.tables.items() if k not in TABLES})


def uid():
    return str(uuid.uuid4())


def now():
    return dt.datetime.now(dt.timezone.utc)


def clean(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: clean(a) for k, a in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(a) for a in v]
    return v


class Database:
    def __init__(self, url=None):
        url = url or os.getenv("DATABASE_URL", "sqlite:///./data/erp.db")
        if not isinstance(url, str):
            url = url.render_as_string(hide_password=False)
        if url.startswith("sqlite") and ":memory:" not in url:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(
                parents=True, exist_ok=True
            )
        kw = {"future": True, "pool_pre_ping": True, "hide_parameters": True}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = create_engine(url, **kw)
        self.lock = threading.RLock()
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def sqlite_setup(c, _):
                c.execute("PRAGMA foreign_keys=ON")
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA busy_timeout=30000")

        with self.write() as c:
            metadata.create_all(c)
            if not c.execute(select(TABLES["app_schema_versions"])).first():
                c.execute(
                    TABLES["app_schema_versions"]
                    .insert()
                    .values(version=1, applied_at=now())
                )

    @contextlib.contextmanager
    def write(self):
        with self.lock, self.engine.connect() as c:
            try:
                if self.engine.dialect.name == "sqlite":
                    c.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    c.begin()
                    c.execute(text("SELECT pg_advisory_xact_lock(496001)"))
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    @contextlib.contextmanager
    def read(self):
        with self.engine.connect() as c:
            yield c


def coerce(col, v):
    if v is None:
        return None
    if isinstance(col.type, DateTime):
        if isinstance(v, str):
            v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if v.tzinfo is None:
                v = v.replace(tzinfo=ZoneInfo("Asia/Jakarta"))
        elif v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        return v.astimezone(dt.timezone.utc)
    if isinstance(col.type, Date):
        return dt.date.fromisoformat(v) if isinstance(v, str) else v
    if isinstance(col.type, Time):
        return dt.time.fromisoformat(v) if isinstance(v, str) else v
    if isinstance(col.type, Numeric):
        return Decimal(str(v))
    if isinstance(col.type, Integer):
        return int(v)
    if isinstance(col.type, Boolean):
        if not isinstance(v, bool):
            raise ValueError("Nilai boolean harus true/false")
    return v


def insert(c, name, values):
    t = TABLES[name]
    values = dict(values)
    if "id" in t.c:
        values.setdefault("id", uid())
    if "created_at" in t.c:
        values.setdefault("created_at", now())
    unknown = set(values) - set(t.c.keys())
    if unknown:
        raise ValueError(f"Field tidak dikenal pada {name}: {sorted(unknown)}")
    values = {k: coerce(t.c[k], v) for k, v in values.items()}
    c.execute(t.insert().values(**values))
    return values


def get(c, name, id):
    return (
        c.execute(select(TABLES[name]).where(TABLES[name].c.id == id))
        .mappings()
        .first()
    )


def rows(c, name, **filters):
    q = select(TABLES[name])
    for k, v in filters.items():
        q = q.where(TABLES[name].c[k] == v)
    return [dict(r) for r in c.execute(q).mappings()]


def update(c, table_name, record_id, **values):
    t = TABLES[table_name]
    c.execute(
        t.update()
        .where(t.c.id == record_id)
        .values(**{k: coerce(t.c[k], v) for k, v in values.items()})
    )
