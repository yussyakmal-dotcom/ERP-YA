"""Generate installation-specific secrets once; never overwrite an existing file."""

import argparse
import os
import secrets
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("mode", choices=["cloud", "pos"])
p.add_argument("--output", default=".env")
a = p.parse_args()
target = Path(a.output)
values = (
    {
        "CLOUD_DB_PASSWORD": secrets.token_urlsafe(36),
        "SETUP_TOKEN": secrets.token_urlsafe(32),
        "BACKOFFICE_BIND": "127.0.0.1",
        "COOKIE_SECURE": "0",
    }
    if a.mode == "cloud"
    else {
        "POS_DB_PASSWORD": secrets.token_urlsafe(36),
        "POS_PORT": "8081",
        "ALLOW_INSECURE_CLOUD": "0",
    }
)
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
except FileExistsError:
    raise SystemExit(
        f"{target} sudah ada. Tidak ditimpa agar kredensial dan volume tetap cocok."
    )
print(
    f"Konfigurasi {a.mode} tersimpan pada {target}. Simpan salinan aman; jangan commit file ini."
)
