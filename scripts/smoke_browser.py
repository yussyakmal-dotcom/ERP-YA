"""Development-only browser flow. Requires requirements-dev and Playwright.

Run: CHROMIUM_EXECUTABLE=/path/to/chromium python scripts/smoke_browser.py
No real business data is read: all databases and users are temporary fixtures.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright
from tests.conftest import env
from app.main import create_app
from app.core import set_setting
from app.services import sync


def serve(app, port):
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return server, thread
        time.sleep(0.05)
    raise RuntimeError("Preview server failed to start")


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    e = env.__wrapped__(root)
    e.stock(e.bread, e.wh["T01"], 10, 3000)
    cloud = create_app(
        e.db.engine.url.render_as_string(hide_password=False), start_worker=False
    )
    local = create_app(
        "sqlite:///" + str(root / "pos.db"), mode="pos", start_worker=False
    )
    cloudserver, cloudthread = serve(cloud, 8765)
    posserver, posthread = serve(local, 8766)
    with sync_playwright() as p:
        kw = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--single-process",
                "--disable-gpu",
            ],
        }
        if os.getenv("CHROMIUM_EXECUTABLE"):
            kw["executable_path"] = os.environ["CHROMIUM_EXECUTABLE"]
        browser = p.chromium.launch(**kw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto("http://127.0.0.1:8766")
        page.locator("[name=cloud_url]").fill("http://127.0.0.1:8765")
        page.locator("[name=token]").fill(e.terminal["token"])
        page.get_by_role("button", name="Pasangkan terminal").click()
        page.get_by_role("heading", name="Selamat datang kembali").wait_for()
        page.locator("[name=username]").fill("admin")
        page.locator("[name=password]").fill("correct-admin-password")
        page.get_by_role("button", name="Masuk", exact=True).click()
        page.locator("[name=opening_cash]").fill("200000")
        page.get_by_role("button", name="Buka shift", exact=True).click()
        page.locator(".product").filter(
            has=page.get_by_text("ROTI", exact=True)
        ).click()
        # Cloud is down; the remaining interaction must use only the local server.
        cloudserver.should_exit = True
        cloudthread.join(timeout=5)
        page.get_by_role("button", name="Bayar Rp", exact=False).click()
        page.locator("#modal [name=amount_received]").fill("10000")
        page.get_by_role("button", name="Selesaikan pembayaran").click()
        page.locator(".receipt").wait_for()
        assert "Rp8.000" in "".join(page.locator(".receipt").inner_text().split())
        page.screenshot(path=str(root / "receipt.png"))
        page.locator(".modal-top button").click()
        page.get_by_role("button", name="Shift kasir", exact=True).click()
        page.locator("[name=actual_cash]").fill("208000")
        page.get_by_role("button", name="Tutup shift", exact=True).click()
        page.get_by_role("button", name="Sinkronisasi", exact=True).click()
        page.get_by_role(
            "heading", name="Status penyimpanan dan sinkronisasi"
        ).wait_for()
        page.get_by_role("button", name="600 detik", exact=True).click()
        page.get_by_role("button", name="Simpan interval", exact=True).click()
        page.get_by_text("Interval tersimpan: 600 detik.", exact=False).wait_for()
        page.reload()
        page.get_by_role("button", name="Sinkronisasi", exact=True).click()
        page.locator("[name=interval_seconds]").wait_for()
        assert page.locator("[name=interval_seconds]").input_value() == "600"
        from app.db import rows

        with local.state.db.read() as c:
            assert len(rows(c, "pos_sales")) == 1
            assert len(rows(c, "sync_outbox")) == 3
            assert rows(c, "pos_shifts")[0]["variance"] == 0
            assert sync.sync_policy(c)["interval_seconds"] == 600
        if os.getenv("BROWSER_QA_OUTPUT"):
            dest = Path(os.environ["BROWSER_QA_OUTPUT"])
            dest.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(dest / "pos-pending.png"))
        browser.close()
        assert not errors, errors
    posserver.should_exit = True
    posthread.join(timeout=5)
print(
    "Browser smoke passed: pair, login, open shift, sell with cloud down, receipt, close shift, durable queue, persistent sync interval changed offline."
)
