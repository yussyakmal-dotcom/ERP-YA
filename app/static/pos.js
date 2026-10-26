// POS screens use only local HTTP calls. The local server owns database commits.
async function refreshPosStatus() {
  const d = await api("/dashboard");
  const me = await api("/me");
  user = { ...user, ...me };
  const status = $("#pos-status");
  if (status) {
    const when = me.cache?.synced_at
      ? new Date(me.cache.synced_at).toLocaleTimeString("id-ID", {
          timeZone: "Asia/Jakarta",
        })
      : "belum sinkron";
    status.textContent = `${d.outbox_pending} antrean · sinkron terakhir ${when}`;
  }
}
async function posView() {
  const shifts = await data("pos_shifts", true);
  shift = shifts.find((s) => !s.closed_at && s.opened_by === user.id);
  $("#app").innerHTML =
    `<header class="pos-header"><div class="brand">YA / KASIR</div><span>${escape(user.name)} · ${escape(shift ? lookup("pos_terminals", shift.terminal_id) : "Terminal lokal")}</span><span class="badge warn" id="pos-status">Memeriksa antrean…</span><button id="logout">Keluar</button></header><nav class="pos-nav" id="pos-nav"></nav><main class="pos-main" id="pos-main"></main>`;
  for (const [id, l] of [
    ["jual", "Jual"],
    ["riwayat", "Riwayat & retur"],
    ["shift", "Shift kasir"],
    ["sync", "Sinkronisasi"],
  ])
    $("#pos-nav").append(
      button(l, () => {
        posTab = id;
        return posPage();
      }),
    );
  $("#logout").onclick = logout;
  await refreshPosStatus();
  await posPage();
}
async function posPage() {
  if (posTab === "jual") return catalog();
  if (posTab === "riwayat") {
    const p = $("#pos-main");
    p.innerHTML =
      '<h1>Riwayat penjualan</h1><p class="subtitle">Retur offline tersedia untuk struk lokal. Struk terminal lain memerlukan validasi di Backoffice.</p>';
    const rs = await data("pos_sales", true);
    await data("documents", true);
    p.append(
      table(
        "pos_sales",
        rs,
        ["id", "sold_at", "total", "offline"],
        async (r) => {
          const b = el("div");
          b.append(
            button("Cetak salinan", () => receipt(r.id, true)),
            button("Retur / refund", () => returnDialog(r)),
          );
          const ls = (await api("/tables/pos_sale_lines?pos_sale_id=" + r.id))
            .rows;
          b.append(
            table("pos_sale_lines", ls, [
              "product_id",
              "qty_input",
              "line_total",
              "stock_source",
            ]),
          );
          modal(rowName("pos_sales", r), b);
        },
      ),
    );
    return;
  }
  if (posTab === "sync") {
    const p = $("#pos-main");
    p.innerHTML =
      '<h1>Status penyimpanan dan sinkronisasi</h1><div class="notice warn">Tersimpan lokal berbeda dengan diterima cloud. Transaksi tidak dihapus saat koneksi terputus.</div>';
    p.append(
      button(
        "Coba sinkron sekarang",
        async () => {
          const r = await api("/sync/run", { method: "POST" });
          toast(
            r.status === "online"
              ? "Sinkronisasi selesai"
              : r.detail || r.status,
          );
          cache = {};
          await start();
        },
        true,
      ),
      table("sync_outbox", await data("sync_outbox", true), [
        "event_type",
        "local_sequence",
        "status",
        "attempt_count",
        "occurred_at",
      ]),
    );
    return;
  }
  return shiftPage();
}
async function shiftPage() {
  const p = $("#pos-main");
  p.innerHTML = `<h1>${shift ? "Shift berjalan" : "Buka shift"}</h1><p class="subtitle">Kas fisik dihitung terpisah dari pembayaran non-tunai.</p>`;
  const f = el("form", { className: "panel" });
  if (!shift) {
    f.innerHTML =
      '<label for="opening-cash">Kas awal *</label><input id="opening-cash" name="opening_cash" type="number" min="0" step="0.01" required><div class="form-footer"><button class="primary" type="submit">Buka shift</button></div>';
    f.onsubmit = async (e) => {
      e.preventDefault();
      try {
        await command("pos.open", {
          opening_cash: new FormData(f).get("opening_cash"),
        });
        posTab = "jual";
        await posView();
      } catch (err) {
        toast(err.message);
      }
    };
  } else {
    f.innerHTML =
      '<div class="form-grid"><div><label for="actual-cash">Kas aktual dihitung *</label><input id="actual-cash" name="actual_cash" type="number" min="0" step="0.01" required></div><div><label for="cash-reason">Alasan selisih / catatan</label><input id="cash-reason" name="reason"></div></div><div class="form-footer"><button class="primary" type="submit">Tutup shift</button></div>';
    f.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const r = await command("pos.close", {
          shift_id: shift.id,
          ...Object.fromEntries(new FormData(f)),
        });
        toast(
          "Shift ditutup. Kas diharapkan " +
            rupiah(r.expected_closing_cash) +
            "; selisih " +
            rupiah(r.variance),
        );
        shift = null;
        cart = [];
        await posView();
      } catch (err) {
        toast(err.message);
      }
    };
    p.append(button("Catat kas masuk / keluar", () => cashDialog()));
  }
  p.append(f);
}
async function catalog() {
  const p = $("#pos-main");
  if (!shift) {
    posTab = "shift";
    return shiftPage();
  }
  p.innerHTML =
    '<div class="pos-grid"><section><h1>Penjualan toko</h1><p class="subtitle">Produk dan kemasan mempunyai harga masing-masing.</p><input id="product-search" placeholder="Scan barcode, cari nama atau SKU…" aria-label="Cari atau scan produk"><div class="catalog" id="catalog"></div></section><aside class="panel cart" id="cart"></aside></div>';
  const products = (await data("products", true)).filter(
    (r) => r.active && r.is_saleable && !r.is_phantom,
  );
  await data("stock_balances", true);
  await data("consignment_agreements", true);
  await data("product_uoms", true);
  await data("price_list_items", true);
  function render(q = "") {
    const box = $("#catalog");
    box.replaceChildren();
    const terms = q.toLowerCase();
    const codes = (cache.product_uoms || [])
      .filter((u) => u.barcode === q)
      .map((u) => u.product_id);
    for (const r of products.filter(
      (r) =>
        (r.name + " " + r.sku).toLowerCase().includes(terms) ||
        codes.includes(r.id),
    )) {
      const b = el("button", { className: "product" });
      b.innerHTML = `<span class="glyph"></span><strong>${escape(r.name)}</strong><span class="price">${rupiah(sellingPrice(r))}</span><small>Stok lokal: ${escape((cache.stock_balances || []).find((s) => s.product_id === r.id)?.quantity || 0)} ${escape(lookup("uoms", r.base_uom_id))}</small>`;
      b.onclick = () => addProduct(r).catch((e) => toast(e.message));
      box.append(b);
    }
    if (!box.children.length)
      box.innerHTML = '<div class="empty">Produk tidak ditemukan.</div>';
  }
  render();
  $("#product-search").oninput = (e) => render(e.target.value);
  $("#product-search").onkeydown = async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const u = (cache.product_uoms || []).find(
        (u) => u.barcode === e.target.value,
      );
      if (u) {
        await addProduct(
          products.find((r) => r.id === u.product_id),
          u,
        );
        e.target.value = "";
        render();
      }
    }
  };
  renderCart();
}
function defaultPriceList() {
  return (
    (cache.price_lists || []).find((r) => r.is_default) ||
    cache.price_lists?.[0]
  );
}
function sellingPrice(p, u = null) {
  u =
    u ||
    (cache.product_uoms || []).find((r) => r.product_id === p.id && r.is_base);
  const prices = (cache.price_list_items || [])
    .filter(
      (r) =>
        r.price_list_id === defaultPriceList()?.id &&
        r.product_uom_id === u?.id &&
        new Date(r.valid_from) <= new Date() &&
        (!r.valid_to || new Date() <= new Date(r.valid_to)),
    )
    .sort((a, b) => b.valid_from.localeCompare(a.valid_from));
  return (
    prices[0]?.price ??
    Number(p.default_sale_price) * Number(u?.factor_to_base || 1)
  );
}
async function addProduct(p, u = null) {
  if (!p) return;
  u =
    u ||
    (cache.product_uoms || []).find((r) => r.product_id === p.id && r.is_base);
  const agreements = (cache.consignment_agreements || []).filter(
    (a) => a.product_id === p.id && a.active,
  );
  let source = "owned",
    agreement = null;
  if (agreements.length) {
    const box = el("div");
    box.innerHTML =
      "<p>Pilih sesuai asal barang fisik yang dijual. Stok owned dan titipan tidak saling menggantikan otomatis.</p>";
    for (const [label, s, a] of [
      ["Milik perusahaan", "owned", null],
      ...agreements.map((a) => [
        "Titipan · " + lookup("suppliers", a.supplier_id),
        "consignment",
        a,
      ]),
    ])
      box.append(
        button(label, () => {
          addToCart(p, u, s, a);
          $("#modal").close();
        }),
      );
    modal("Asal barang · " + p.name, box);
    return;
  }
  addToCart(p, u, source, agreement);
}
function addToCart(p, u, source, agreement) {
  let ln = cart.find(
    (a) =>
      a.product_id === p.id &&
      a.uom_id === u.uom_id &&
      a.stock_source === source &&
      a.agreement_id === agreement?.id,
  );
  if (ln) ln.quantity = Number(ln.quantity) + 1;
  else
    cart.push({
      product_id: p.id,
      uom_id: u.uom_id,
      quantity: 1,
      stock_source: source,
      agreement_id: agreement?.id,
      name: p.name,
      price: Number(sellingPrice(p, u)),
    });
  renderCart();
}
function renderCart() {
  const c = $("#cart");
  if (!c) return;
  c.innerHTML = "<h2>Keranjang</h2>";
  for (const [i, a] of cart.entries()) {
    const r = el("div", { className: "cart-line" });
    const label = el("span");
    label.innerHTML = `${escape(a.name)}<br><small>${escape(a.stock_source === "owned" ? "Milik perusahaan" : "Titipan")}</small>`;
    const q = el("input", {
      type: "number",
      min: "0.001",
      step: "any",
      value: a.quantity,
      ariaLabel: "Jumlah " + a.name,
    });
    q.onchange = () => {
      if (Number(q.value) > 0) a.quantity = q.value;
      renderCart();
    };
    r.append(
      label,
      q,
      el("strong", { textContent: rupiah(Number(a.quantity) * a.price) }),
      button("×", () => {
        cart.splice(i, 1);
        renderCart();
      }),
    );
    c.append(r);
  }
  const total = cart.reduce((n, a) => n + Number(a.quantity) * a.price, 0);
  c.append(
    el("div", {
      className: "cart-total",
      innerHTML: `<span>Total</span><span>${rupiah(total)}</span>`,
    }),
    el("p", {
      className: "muted",
      textContent:
        "Stok lokal dapat berbeda dari kasir lain. Voucher berkuota dan penukaran poin memerlukan validasi online.",
    }),
    button("Bayar " + rupiah(total), () => payDialog(total), true),
  );
  c.lastChild.classList.add("full");
  c.lastChild.disabled = !cart.length;
}
async function authorizationFields() {
  const grid = el("div", { className: "form-grid" });
  grid.dataset.auth = "1";
  grid.append(
    await inputField(F("user_id", "users")),
    await inputField(F("pin", null, { type: "password" })),
  );
  return grid;
}
async function payDialog(total) {
  const form = el("form");
  const totalDisplay = el("h1", { textContent: rupiah(total) });
  form.append(
    totalDisplay,
    el("p", {
      className: "muted",
      textContent:
        "Pembayaran elektronik memerlukan bukti valid. Harga, diskon dan pajak dihitung dari master lokal.",
    }),
  );
  const grid = el("div", { className: "form-grid" });
  for (const f of [
    F("customer_id", "customers", { optional: true }),
    F("promotion_id", "promotion_rules", {
      optional: true,
      label: "Promosi aktif",
    }),
    F("negative_reason", null, {
      label: "Alasan jika stok minus",
      optional: true,
    }),
    F("discount_amount", null, { type: "number", optional: true, value: 0 }),
    F("discount_reason", null, { optional: true }),
  ])
    grid.append(await inputField(f));
  form.append(grid);
  const benefit = el("details");
  benefit.innerHTML =
    "<summary>Voucher dan penukaran poin · perlu koneksi cloud</summary>";
  const benefitGrid = el("div", { className: "form-grid" });
  benefitGrid.append(
    await inputField(
      F("voucher_code", null, { label: "Kode voucher", optional: true }),
    ),
    await inputField(
      F("points", null, {
        label: "Poin ditukar",
        type: "number",
        optional: true,
        value: 0,
      }),
    ),
  );
  benefit.append(benefitGrid);
  form.append(benefit);
  let hold = null,
    quoteTotal = total;
  const holdInfo = el("p", { className: "muted" });
  benefit.append(holdInfo);
  const section = await arrayEditor(
    "tenders",
    "Metode pembayaran (boleh dibagi)",
    [
      F("method_id", "payment_methods"),
      F("cash_bank_account_id", "cash_bank_accounts"),
      F("amount_applied", null, { type: "number" }),
      F("amount_received", null, { type: "number", optional: true }),
      F("provider_reference", null, { optional: true }),
    ],
    [
      {
        method_id: cache.payment_methods.find((m) => m.is_cash)?.id,
        cash_bank_account_id: cache.cash_bank_accounts?.[0]?.id,
        amount_applied: String(total),
        amount_received: String(total),
      },
    ],
  );
  form.append(section);
  const sup = el("details");
  sup.innerHTML =
    "<summary>Persetujuan supervisor untuk diskon khusus</summary>";
  const auth = await authorizationFields();
  auth.querySelectorAll("input,select").forEach((i) => (i.required = false));
  sup.append(auth);
  form.append(sup);
  const err = el("div", { className: "error-text", role: "alert" }),
    foot = el("div", { className: "form-footer" }),
    save = el("button", {
      type: "submit",
      className: "primary",
      textContent: "Selesaikan pembayaran",
    });
  foot.append(save);
  form.append(err, foot);
  function parameters() {
    return {
      shift_id: shift.id,
      price_list_id: defaultPriceList()?.id,
      ...readInputs(grid),
      ...(hold ? { redemption_id: hold.id } : {}),
      lines: cart.map((a) => ({
        ...a,
        negative_reason: readInputs(grid).negative_reason,
      })),
    };
  }
  async function requote() {
    const q = await api("/pos/quote", {
      method: "POST",
      body: JSON.stringify(parameters()),
    });
    quoteTotal = Number(q.total);
    totalDisplay.textContent = rupiah(q.total);
    if (section.querySelectorAll(".line-row").length === 1) {
      section.querySelector("[name=amount_applied]").value = q.total;
      section.querySelector("[name=amount_received]").value = q.total;
    }
    return q;
  }
  grid.addEventListener("change", () =>
    requote().catch((e) => (err.textContent = e.message)),
  );
  benefit.append(
    button("Validasi dan reservasi voucher / poin", async () => {
      if (hold) throw Error("Reservasi sudah tersedia untuk keranjang ini");
      hold = await api("/pos/redemptions", {
        method: "POST",
        body: JSON.stringify({ ...parameters(), ...readInputs(benefitGrid) }),
      });
      holdInfo.textContent =
        "Potongan " +
        rupiah(hold.amount) +
        " telah direservasi. Selesaikan penjualan atau batalkan reservasi.";
      grid
        .querySelectorAll(
          "[name=customer_id],[name=promotion_id],[name=discount_amount]",
        )
        .forEach((i) => (i.disabled = true));
      await requote();
    }),
    button("Batalkan reservasi", async () => {
      if (!hold) return;
      await api("/pos/redemptions/" + hold.id + "/release", { method: "POST" });
      hold = null;
      holdInfo.textContent = "Reservasi dibatalkan.";
      grid
        .querySelectorAll("input,select")
        .forEach((i) => (i.disabled = false));
      await requote();
    }),
  );
  const key = crypto.randomUUID();
  form.onsubmit = async (e) => {
    e.preventDefault();
    save.disabled = true;
    err.textContent = "";
    try {
      const tenders =
        quoteTotal === 0
          ? []
          : [...section.querySelectorAll(".line-row")]
              .map(readInputs)
              .map((t) => ({
                ...t,
                verification_status: t.provider_reference ? "verified" : "cash",
              }));
      const p = {
        ...parameters(),
        tenders,
        authorization: readInputs(auth),
        offline: !navigator.onLine,
      };
      const r = await command("pos.sale", p, key);
      cart = [];
      $("#modal").close();
      await posView();
      toast(
        "Struk tersimpan lokal. Sinkronisasi berjalan ketika cloud tersedia.",
      );
      await receipt(r.id);
    } catch (e) {
      err.textContent = e.message;
    } finally {
      save.disabled = false;
    }
  };
  modal("Pembayaran", form);
  await requote();
}
async function receipt(id, copy = false) {
  await data("documents", true);
  const sale = (await data("pos_sales", true)).find((s) => s.id === id);
  const ls = (await api("/tables/pos_sale_lines?pos_sale_id=" + id)).rows;
  const tenders = (await api("/tables/pos_tenders?pos_sale_id=" + id)).rows;
  const b = el("div", { className: "receipt" });
  b.innerHTML = `<div class="receipt-head"><h2>YUSSY AKMAL</h2><p>${escape(lookup("pos_terminals", sale.terminal_id))}<br>${escape(lookup("documents", id))}${copy ? "<br>SALINAN" : ""}<br>${new Date(sale.sold_at).toLocaleString("id-ID", { timeZone: "Asia/Jakarta" })}</p></div><table>${ls.map((a) => `<tr><td>${escape(lookup("products", a.product_id))}<br>${escape(a.qty_input)} × ${rupiah(a.unit_price_input)}</td><td>${rupiah(a.line_total)}</td></tr>`).join("")}</table><p>Total: <strong>${rupiah(sale.total)}</strong></p>${tenders.map((t) => `<p>${escape(lookup("payment_methods", t.method_id))}: ${rupiah(t.amount_received)}<br>Kembalian: ${rupiah(t.change_amount)}</p>`).join("")}<p class="receipt-head">Terima kasih telah berbelanja.</p>`;
  const box = el("div");
  box.append(
    b,
    button("Cetak struk", () => window.print()),
  );
  box.lastChild.className = "no-print";
  modal(copy ? "Salinan struk" : "Penjualan tersimpan lokal", box);
}
async function returnDialog(sale) {
  if (!shift) throw Error("Buka shift untuk memproses refund");
  const ls = (await api("/tables/pos_sale_lines?pos_sale_id=" + sale.id)).rows;
  cache.pos_sale_lines = ls;
  for (const r of ls) r.code = lookup("products", r.product_id);
  const f = el("form");
  const grid = el("div", { className: "form-grid" });
  for (const d of [
    F("reason"),
    F("method_id", "payment_methods"),
    F("cash_bank_account_id", "cash_bank_accounts"),
  ])
    grid.append(await inputField(d));
  f.append(grid);
  const lines = await arrayEditor(
    "lines",
    "Barang dikembalikan",
    [
      F("line_id", "pos_sale_lines"),
      F("quantity", null, { type: "number" }),
      F("condition", null, { choices: ["good", "damaged"] }),
    ],
    [{}],
  );
  f.append(lines, el("h3", { textContent: "Supervisor yang menyetujui" }));
  const auth = await authorizationFields();
  f.append(auth);
  const err = el("div", { className: "error-text" }),
    foot = el("div", { className: "form-footer" });
  foot.append(
    el("button", {
      type: "submit",
      className: "primary",
      textContent: "Posting retur dan refund",
    }),
  );
  f.append(err, foot);
  const key = crypto.randomUUID();
  f.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await command(
        "pos.return",
        {
          ...readInputs(grid),
          source_document_id: sale.id,
          shift_id: shift.id,
          authorization: readInputs(auth),
          lines: [...lines.querySelectorAll(".line-row")].map(readInputs),
        },
        key,
      );
      $("#modal").close();
      await posView();
      toast("Retur dan refund tersimpan lokal");
    } catch (e) {
      err.textContent = e.message;
    }
  };
  modal("Retur dan refund POS", f);
}
async function cashDialog() {
  const f = el("form");
  const g = el("div", { className: "form-grid" });
  for (const x of [
    F("kind", null, { choices: ["in", "out", "deposit"] }),
    F("amount", null, { type: "number" }),
    F("reason"),
  ])
    g.append(await inputField(x));
  f.append(g);
  const foot = el("div", { className: "form-footer" });
  foot.append(
    el("button", {
      type: "submit",
      className: "primary",
      textContent: "Catat kas",
    }),
  );
  f.append(foot);
  f.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await command("pos.cash", { shift_id: shift.id, ...readInputs(g) });
      $("#modal").close();
      toast("Gerakan kas dicatat");
    } catch (e) {
      toast(e.message);
    }
  };
  modal("Kas masuk / keluar", f);
}
