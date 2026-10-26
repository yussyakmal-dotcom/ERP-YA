"""Consistent SQLite backup for development; PostgreSQL uses pg_dump (see runbook)."""

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("database")
p.add_argument("--directory", default="backups")
a = p.parse_args()
source = Path(a.database).resolve()
target = Path(a.directory)
target.mkdir(parents=True, exist_ok=True)
if not source.is_file():
    raise SystemExit("Database sumber tidak ditemukan")
dest = target / (
    source.stem + "-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".db"
)
with sqlite3.connect(source) as src, sqlite3.connect(dest) as dst:
    src.backup(dst)
dest.chmod(0o600)
print(dest)
