"use strict";
const $ = (s) => document.querySelector(s),
  el = (t, c) => Object.assign(document.createElement(t), c || {});
const escape = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const rupiah = (v) =>
  new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 2,
  }).format(Number(v || 0));
const today = () =>
  new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Jakarta" });
let user = null,
  mode = "backoffice",
  model = null,
  page = "dashboard",
  selected = null,
  currentRows = [],
  cache = {},
  cart = [],
  shift = null,
  posTab = "jual",
  searchTimer,
  automaticRefresh;
const names = {
  products: "Produk",
  product_uoms: "Konversi satuan",
  uoms: "Satuan",
  categories: "Kategori",
  suppliers: "Supplier",
  customers: "Pelanggan",
  warehouses: "Gudang",
  outlets: "Toko dan outlet",
  kitchens: "Dapur",
  product_kitchen_routes: "Rute dapur",
  replenishment_policies: "Target stok toko",
  price_lists: "Daftar harga",
  price_list_items: "Harga produk",
  consignment_agreements: "Perjanjian titipan",
  payment_methods: "Metode pembayaran",
  cash_bank_accounts: "Kas dan bank",
  chart_of_accounts: "Bagan akun",
  taxes: "Pajak",
  fiscal_periods: "Periode keuangan",
  documents: "Dokumen",
  purchase_orders: "Purchase Order",
  goods_receipts: "Penerimaan final PO",
  sales_orders: "Sales Order",
  production_orders: "Perintah produksi",
  transfer_orders: "Transfer antar lokasi",
  transfer_discrepancies: "Selisih transit",
  stock_balances: "Stok dan reservasi",
  stock_movements: "Kartu mutasi",
  inventory_adjustments: "Opname / koreksi stok",
  store_requests: "Permintaan toko",
  demand_lines: "Perencanaan kebutuhan",
  boms: "Resep dan paket",
  schedule_versions: "Jadwal dan cutoff",
  users: "Pengguna",
  roles: "Peran dan hak",
  approval_requests: "Pusat persetujuan",
  approval_rules: "Aturan persetujuan",
  payments: "Pembayaran dan DP",
  customer_deposits: "Saldo DP",
  refunds: "Refund",
  returns: "Retur barang",
  purchase_invoices: "Faktur supplier",
  sales_invoices: "Invoice pelanggan",
  consignment_settlements: "Settlement titipan",
  expenses: "Beban periode",
  journal_entries: "Jurnal",
  journal_lines: "Rincian jurnal",
  sync_inbox: "Transaksi diterima cloud",
  sync_conflicts: "Konflik sinkronisasi",
  pos_terminals: "Terminal kasir",
  pos_sales: "Riwayat penjualan",
  pos_shifts: "Shift kasir",
  sync_outbox: "Antrean lokal",
  approval_actions: "Keputusan persetujuan",
  production_materials: "Pengeluaran bahan",
  production_outputs: "Hasil produksi",
  production_failures: "Produk gagal",
  production_material_returns: "Sisa bahan layak",
  bom_byproducts: "Produk turunan",
  credit_notes: "Hak kredit",
  deposit_applications: "Alokasi DP",
  audit_logs: "Audit",
  production_schedules: "Nama jadwal",
  promotion_rules: "Promosi",
  vouchers: "Voucher",
  loyalty_accounts: "Akun loyalty",
  loyalty_entries: "Mutasi loyalty",
  stock_reservations: "Reservasi",
  account_period_balances: "Saldo periode",
};
const labels = {
  id: "Identitas",
  code: "Kode",
  sku: "SKU",
  name: "Nama",
  kind: "Jenis",
  status: "Status",
  active: "Aktif",
  business_date: "Tanggal bisnis",
  document_no: "Nomor dokumen",
  document_type: "Jenis dokumen",
  revision: "Revisi",
  customer_id: "Pelanggan",
  supplier_id: "Supplier",
  warehouse_id: "Gudang",
  from_warehouse_id: "Gudang asal",
  to_warehouse_id: "Gudang tujuan",
  receiving_warehouse_id: "Gudang penerima",
  fulfillment_warehouse_id: "Gudang packing",
  outlet_id: "Outlet asal",
  delivery_date: "Tanggal kirim",
  schedule_version_id: "Versi jadwal",
  schedule_id: "Jadwal",
  price_list_id: "Daftar harga",
  quantity: "Jumlah",
  product_id: "Produk",
  uom_id: "Satuan",
  base_uom_id: "Satuan dasar",
  unit_price: "Harga satuan",
  default_sale_price: "Harga jual dasar",
  default_purchase_cost: "Biaya beli dasar",
  is_saleable: "Dapat dijual",
  is_purchasable: "Dapat dibeli",
  is_manufacturable: "Dapat diproduksi",
  is_phantom: "Paket SO",
  intermediate_type: "Jenis intermediate",
  kitchen_id: "Dapur",
  raw_warehouse_id: "Gudang bahan",
  output_warehouse_id: "Gudang hasil",
  is_default: "Rute / daftar utama",
  factor_to_base: "Faktor ke satuan dasar",
  barcode: "Barcode",
  is_base: "Satuan dasar",
  allow_sale: "Boleh dijual",
  allow_purchase: "Boleh dibeli",
  allow_decimal: "Boleh pecahan",
  dimension: "Dimensi",
  category_id: "Kategori",
  version: "Versi",
  original_total: "Nilai pesan",
  actual_total: "Nilai diterima",
  quantity: "Jumlah",
  reserved_quantity: "Reservasi",
  inventory_value: "Nilai persediaan",
  avg_cost: "Biaya rata-rata",
  qty_delta: "Mutasi jumlah",
  qty_disputed: "Selisih awal",
  qty_resolved: "Selesai",
  total: "Total",
  subtotal: "Subtotal",
  reason: "Alasan",
  notes: "Catatan",
  contact: "Kontak",
  phone: "Telepon",
  order_date: "Tanggal pesan",
  expected_date: "Perkiraan tiba",
  created_at: "Dibuat",
  sales_order_id: "Sales Order",
  purchase_order_id: "Purchase Order",
  goods_receipt_id: "Penerimaan barang",
  source_document_id: "Dokumen asal",
  approval_document_id: "Dokumen persetujuan",
  cutoff_time: "Jam batas H-1",
  delivery_time: "Jam pengiriman",
  effective_from: "Mulai berlaku",
  effective_to: "Akhir berlaku",
  valid_from: "Berlaku mulai",
  valid_to: "Berlaku sampai",
  purpose: "Tujuan",
  output_quantity: "Hasil standar",
  good_quantity: "Hasil utama layak",
  failed_quantity: "Jumlah gagal",
  failure_reason: "Alasan gagal",
  material_id: "Pengeluaran bahan",
  action_code: "Tindakan",
  offline_allowed: "Boleh disetujui offline",
  role_id: "Peran penyetuju",
  user_id: "Pengguna",
  username: "Nama pengguna",
  password: "Sandi",
  pin: "PIN supervisor",
  required_count: "Jumlah penyetuju",
  allow_self_approval: "Boleh menyetujui sendiri",
  min_amount: "Nilai minimum",
  max_amount: "Nilai maksimum",
  amount: "Nilai",
  method_id: "Metode pembayaran",
  cash_bank_account_id: "Rekening",
  reference: "Referensi / bukti",
  deposit_id: "Uang muka",
  invoice_id: "Faktur / invoice",
  document_id: "Dokumen",
  line_id: "Baris dokumen",
  component_id: "Komponen SO",
  receipt_line_id: "Baris penerimaan",
  unit_cost: "Biaya satuan",
  counted_quantity: "Fisik saat hitung",
  baseline_quantity: "Saldo saat hitung",
  unit_cost_base: "Harga supplier / satuan dasar",
  condition: "Kondisi",
  resolution_type: "Hasil pemeriksaan",
  confirmed_at_source: "Barang terkonfirmasi di sumber",
  evidence: "Bukti pemeriksaan",
  min_qty: "Stok minimum",
  target_qty: "Target stok",
  order_multiple: "Kelipatan",
  source_warehouse_id: "Sumber pemenuhan",
  required_date: "Tanggal kebutuhan",
  origin: "Sumber",
  supplier_invoice_no: "Nomor faktur supplier",
  due_date: "Jatuh tempo",
  period_from: "Periode awal",
  period_to: "Periode akhir",
  account_id: "Akun",
  description: "Keterangan",
  recipient_name: "Penerima",
  supplier_reference: "Surat jalan supplier",
  side: "Jenis retur",
  channel: "Kanal",
  terms: "Ketentuan",
  settlement_terms: "Ketentuan settlement",
  payment_terms_days: "Tempo (hari)",
  price: "Harga",
  product_uom_id: "Produk / satuan",
  start_date: "Tanggal awal",
  end_date: "Tanggal akhir",
  account_type: "Jenis akun",
  normal_balance: "Saldo normal",
  is_postable: "Boleh diposting",
  parent_id: "Induk",
  permissions: "Hak tindakan",
  closed_at: "Ditutup",
  cutoff_day_offset: "Hari cutoff",
  planned_qty_base: "Target produksi",
  actual_good_qty_base: "Hasil layak",
  material_net_cost: "Biaya bahan bersih",
  qty_required: "Kebutuhan",
  qty_base: "Jumlah dasar",
  stock_source: "Asal stok",
  local_sequence: "Urutan lokal",
  occurred_at: "Waktu asli",
  event_type: "Kejadian",
  payload_hash: "Jejak integritas",
  attempt_count: "Percobaan kirim",
  last_success_at: "Sinkron terakhir",
  amount_applied: "Nilai dibayar",
  amount_received: "Uang diterima",
  actual_cash: "Kas aktual",
  opening_cash: "Kas awal",
  verification_status: "Status verifikasi",
  provider_reference: "Referensi penyedia",
  sales_group_name: "Kelompok penjualan",
};
const title = (k) => labels[k] || names[k] || k.replaceAll("_", " ");
function toast(s) {
  $("#toast").textContent = s;
  $("#toast").style.display = "block";
  setTimeout(() => ($("#toast").style.display = "none"), 5500);
}
async function api(path, options = {}) {
  const h = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (user?.csrf) h["X-CSRF-Token"] = user.csrf;
  const r = await fetch("/api" + path, { ...options, headers: h });
  let d;
  try {
    d = await r.json();
  } catch {
    d = { detail: "Respons tidak dapat dibaca" };
  }
  if (!r.ok) {
    if (r.status === 401 && path != "/login" && path != "/me" && user) {
      user = null;
      setTimeout(() => init(), 0);
    }
    throw Error(
      typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail),
    );
  }
  return d;
}
async function command(name, p, key = crypto.randomUUID()) {
  return api("/commands/" + name, {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify(p),
  });
}
async function data(name, force = false) {
  if (!cache[name] || force) {
    try {
      let list = [],
        offset = 0;
      while (true) {
        const result = await api(
          "/tables/" + name + "?limit=500&offset=" + offset,
        );
        list.push(...result.rows);
        offset += result.rows.length;
        if (offset >= result.total || !result.rows.length) break;
      }
      cache[name] = list;
    } catch {
      cache[name] = [];
    }
  }
  return cache[name];
}
function rowName(t, r) {
  if (!r) return "—";
  if (t === "schedule_versions") {
    const s = (cache.production_schedules || []).find(
      (x) => x.id === r.schedule_id,
    );
    return `${s?.name || "Jadwal"} v${r.version} · H-1 ${r.cutoff_time} → ${r.delivery_time}`;
  }
  if (t === "product_uoms") {
    return lookup("products", r.product_id) + " / " + lookup("uoms", r.uom_id);
  }
  if (r.document_no) return r.document_no;
  if (r.sku) return r.sku + " · " + r.name;
  if (r.name) return (r.code ? r.code + " · " : "") + r.name;
  const d = (cache.documents || []).find((x) => x.id === r.id);
  if (d) return d.document_no;
  return r.code || r.username || r.action_code || r.id?.slice(0, 8) || "—";
}
function lookup(t, id) {
  return rowName(
    t,
    (cache[t] || []).find((r) => r.id === id),
  );
}
function cell(t, key, v) {
  if (v == null) return "—";
  if (key === "status")
    return `<span class="badge ${["draft", "pending", "conflict", "partial", "retry"].includes(v) ? "warn" : ""}">${escape(v)}</span>`;
  if (typeof v === "boolean") return v ? "Ya" : "Tidak";
  const f = model?.tables[t]?.fields.find((a) => a.name === key);
  if (f?.ref) {
    const rt = f.ref.split(".")[0];
    return escape(lookup(rt, v));
  }
  if (typeof v === "object") return escape(JSON.stringify(v));
  if (/amount|price|cost|total|value|cash|debit|credit/.test(key))
    return escape(rupiah(v));
  return escape(v);
}
function button(text, fn, primary = false) {
  const b = el("button", {
    textContent: text,
    className: primary ? "primary" : "",
  });
  b.onclick = () => Promise.resolve(fn()).catch((e) => toast(e.message));
  return b;
}
function table(t, rs, cols = null, click = null) {
  cols =
    cols ||
    (rs.length
      ? Object.keys(rs[0])
          .filter(
            (k) => !["id", "created_at", "posted_by", "created_by"].includes(k),
          )
          .slice(0, 7)
      : []);
  const box = el("div", { className: "table-wrap" });
  if (!rs.length) {
    box.innerHTML =
      '<div class="empty">Belum ada data. Buat dokumen baru atau ubah pencarian.</div>';
    return box;
  }
  const tb = el("table");
  tb.innerHTML = `<thead><tr>${cols.map((k) => `<th>${escape(title(k))}</th>`).join("")}</tr></thead>`;
  const body = el("tbody");
  for (const r of rs) {
    const tr = el("tr");
    tr.innerHTML = cols.map((k) => `<td>${cell(t, k, r[k])}</td>`).join("");
    if (click) {
      tr.tabIndex = 0;
      tr.onclick = () =>
        Promise.resolve(click(r)).catch((e) => toast(e.message));
      tr.onkeydown = (e) => {
        if (e.key === "Enter") tr.click();
      };
    }
    body.append(tr);
  }
  tb.append(body);
  box.append(tb);
  return box;
}
function modal(name, content) {
  const m = $("#modal-content");
  m.replaceChildren();
  const top = el("div", { className: "modal-top" });
  top.append(
    el("h2", { textContent: name }),
    button("×", () => $("#modal").close()),
  );
  m.append(top, content);
  if (!$("#modal").open) $("#modal").showModal();
}
function renderLogin(state) {
  $("#app").innerHTML =
    `<div class="login"><aside class="login-brand"><div class="brand">YUSSY AKMAL</div><div class="brand-sub">BAKERY · OPERATIONS</div><h1>Dari dapur,<br>hingga setiap toko.</h1><p>Ruang kerja untuk pesanan, produksi, persediaan, dan penjualan.</p></aside><main class="login-panel"><form class="login-form" id="login-form"><h2>${state.initialized ? "Selamat datang kembali" : mode === "pos" ? "Pasangkan kasir" : "Siapkan perusahaan"}</h2><p class="muted">${state.initialized ? (mode === "pos" ? "POS lokal · masuk dengan akun tersinkron." : "Backoffice · operasional Yussy Akmal.") : mode === "pos" ? "Gunakan URL Backoffice dan token terminal dari administrator." : "Buat administrator pertama. Sandi minimal 12 karakter."}</p><div id="login-fields"></div><div class="error-text" id="login-error" role="alert"></div><button type="submit" class="primary">${state.initialized ? "Masuk" : mode === "pos" ? "Pasangkan terminal" : "Mulai setup"}</button></form></main></div>`;
  const fields = state.initialized
    ? [
        ["username", "Nama pengguna", "text"],
        ["password", "Sandi", "password"],
      ]
    : mode === "pos"
      ? [
          ["cloud_url", "URL Backoffice", "url"],
          ["token", "Token terminal", "password"],
        ]
      : [
          ["username", "Nama pengguna admin", "text"],
          ["password", "Sandi baru", "password"],
          ["setup_token", "Token setup (jika disetel)", "password"],
        ];
  for (const [n, l, t] of fields) {
    const d = el("div", { className: "field" });
    d.innerHTML = `<label for="login-${n}">${l}</label><input id="login-${n}" name="${n}" type="${t}" ${n === "setup_token" ? "" : "required"} autocomplete="${n === "password" ? (state.initialized ? "current-password" : "new-password") : "off"}">`;
    $("#login-fields").append(d);
  }
  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.target.querySelector("button[type=submit]");
    b.disabled = true;
    try {
      const p = Object.fromEntries(new FormData(e.target));
      if (state.initialized) {
        user = await api("/login", { method: "POST", body: JSON.stringify(p) });
        await start();
      } else {
        await api(mode === "pos" ? "/pos/pair" : "/bootstrap", {
          method: "POST",
          body: JSON.stringify(p),
        });
        await init();
      }
    } catch (err) {
      $("#login-error").textContent = err.message;
    } finally {
      b.disabled = false;
    }
  };
}
const menus = [
  ["dashboard", "Ringkasan"],
  ["sales_orders", "Penjualan SO"],
  ["purchase_orders", "Pembelian"],
  ["transfer_orders", "Gudang & transit"],
  ["production_orders", "Produksi"],
  ["approval_requests", "Persetujuan"],
  ["payments", "Keuangan"],
  ["reports", "Laporan"],
  ["products", "Master"],
  ["sync_conflicts", "Sinkronisasi"],
  ["settings", "Pengaturan"],
];
function shell() {
  const root = $("#app");
  root.innerHTML = `<aside class="sidebar"><div class="brand">YA</div><div class="brand-sub">BACKOFFICE</div><nav class="nav"></nav><div class="side-foot">Yussy Akmal<br>Semua lokasi · WIB</div></aside><div class="workspace"><header class="topbar"><span>Yussy Akmal / <strong id="breadcrumb"></strong></span><div class="right"><small>Backoffice cloud</small><span>${escape(user.name)}</span><button id="logout">Keluar</button></div></header><main class="main" id="main"></main></div>`;
  for (const [id, l] of menus) {
    const b = button(l, () => navigate(id));
    b.dataset.page = id;
    $(".nav").append(b);
  }
  $("#logout").onclick = logout;
}
async function logout() {
  await api("/logout", { method: "POST" });
  user = null;
  clearInterval(automaticRefresh);
  cache = {};
  await init();
}
async function start() {
  model = await api("/model");
  await Promise.all(
    [
      "products",
      "uoms",
      "warehouses",
      "outlets",
      "kitchens",
      "suppliers",
      "customers",
      "documents",
      "production_schedules",
      "schedule_versions",
      "price_lists",
      "payment_methods",
      "cash_bank_accounts",
      "chart_of_accounts",
      "roles",
      "users",
    ].map((t) => data(t, true)),
  );
  if (mode === "pos") {
    await posView();
    clearInterval(automaticRefresh);
    automaticRefresh = setInterval(
      () => refreshPosStatus().catch(() => {}),
      15000,
    );
  } else {
    shell();
    await navigate("dashboard");
  }
}
async function navigate(id) {
  page = id;
  selected = null;
  $("#breadcrumb").textContent =
    names[id] || menus.find((a) => a[0] === id)?.[1] || title(id);
  $(".nav")
    ?.querySelectorAll("button")
    .forEach((b) => b.classList.toggle("active", b.dataset.page === id));
  if (id === "dashboard") return dashboard();
  if (id === "settings") return settings();
  if (id === "reports") return reports();
  return listing(id);
}
async function dashboard() {
  const d = await api("/dashboard");
  const m = $("#main");
  m.innerHTML =
    '<h1>Ringkasan operasional</h1><p class="subtitle">Prioritaskan pekerjaan yang perlu tindakan hari ini.</p>';
  const cards = el("div", { className: "cards" });
  for (const [k, n, to] of [
    ["open_orders", "SO belum selesai", "sales_orders"],
    ["approvals", "Persetujuan tertunda", "approval_requests"],
    ["transit_cases", "Kasus selisih transit", "transfer_discrepancies"],
    ["negative_stock", "Stok minus / provisional", "stock_balances"],
  ]) {
    const c = el("div", { className: "metric" });
    c.innerHTML = `<small>${n}</small><strong>${d[k]}</strong><small>Buka rincian →</small>`;
    c.onclick = () => navigate(to);
    cards.append(c);
  }
  m.append(cards);
  const p = el("div", { className: "panel" });
  p.innerHTML =
    '<h2>Mulai bekerja</h2><p class="muted">Semua Sales Order dan pembayaran pesanan berada di Backoffice. Penerimaan toko juga dilakukan di sini.</p>';
  const actions = el("div", { className: "toolbar" });
  for (const [label, cmd] of [
    ["Buat SO", "so.create"],
    ["Buat PO", "po.create"],
    ["Buat transfer", "transfer.create"],
    ["Permintaan toko", "store.request"],
  ])
    actions.append(button(label, () => commandForm(cmd), cmd === "so.create"));
  p.append(actions);
  m.append(p);
  const tips = el("div", { className: "notice warn" });
  tips.textContent =
    "Sebelum transaksi: lengkapi jadwal H-1, harga, resep, stok awal dan aturan persetujuan. Nilai perusahaan tidak diisi dengan contoh otomatis.";
  m.append(tips);
}
const groups = {
  sales_orders: [
    "sales_orders",
    "deliveries",
    "sales_invoices",
    "customer_deposits",
    "deposit_applications",
  ],
  purchase_orders: [
    "purchase_orders",
    "goods_receipts",
    "purchase_invoices",
    "suppliers",
    "consignment_agreements",
    "consignment_settlements",
  ],
  transfer_orders: [
    "transfer_orders",
    "transfer_discrepancies",
    "stock_balances",
    "stock_movements",
    "stock_reservations",
    "inventory_adjustments",
    "returns",
  ],
  production_orders: [
    "production_orders",
    "demand_lines",
    "store_requests",
    "replenishment_policies",
    "boms",
    "production_outputs",
    "production_material_returns",
    "production_failures",
  ],
  payments: [
    "payments",
    "customer_deposits",
    "credit_notes",
    "refunds",
    "expenses",
    "journal_entries",
    "fiscal_periods",
    "account_period_balances",
  ],
  products: [
    "products",
    "product_uoms",
    "categories",
    "uoms",
    "product_kitchen_routes",
    "customers",
    "suppliers",
    "price_lists",
    "price_list_items",
    "promotion_rules",
    "vouchers",
    "warehouses",
    "outlets",
    "kitchens",
    "payment_methods",
    "cash_bank_accounts",
    "chart_of_accounts",
    "taxes",
  ],
  sync_conflicts: [
    "sync_conflicts",
    "sync_inbox",
    "pos_terminals",
    "pos_sales",
    "pos_shifts",
  ],
  approval_requests: [
    "approval_requests",
    "approval_actions",
    "approval_rules",
  ],
};
const createActions = {
  sales_orders: ["Buat SO", "so.create"],
  purchase_orders: ["Buat PO", "po.create"],
  transfer_orders: ["Buat transfer", "transfer.create"],
  store_requests: ["Buat permintaan", "store.request"],
  inventory_adjustments: ["Catat hitungan", "stock.adjust"],
  boms: ["Buat versi resep", "bom.version"],
  schedule_versions: ["Buat versi jadwal", "schedule.version"],
  users: ["Tambah pengguna", "user.save"],
  approval_rules: ["Atur persetujuan", "approval.rule"],
  payments: ["Catat pembayaran / DP", "payment.create"],
  expenses: ["Catat beban", "expense.create"],
  returns: ["Catat retur", "return.create"],
  purchase_invoices: ["Buat faktur supplier", "purchase.invoice"],
  consignment_settlements: ["Buat settlement", "consignment.settle"],
  pos_terminals: ["Daftarkan terminal", "terminal.register"],
};
async function listing(t, offset = 0, q = "") {
  const m = $("#main");
  m.replaceChildren();
  m.append(
    el("h1", { textContent: names[t] || title(t) }),
    el("p", {
      className: "subtitle",
      textContent:
        "Pilih baris untuk melihat detail, riwayat, dan tindakan yang tersedia.",
    }),
  );
  const group = Object.values(groups).find((a) => a.includes(t));
  if (group) {
    const tabs = el("div", { className: "toolbar" });
    for (const it of group) {
      const b = button(names[it] || title(it), () => listing(it));
      b.classList.toggle("primary", it === t);
      tabs.append(b);
    }
    m.append(tabs);
  }
  const tools = el("div", { className: "toolbar" });
  const search = el("input", {
    placeholder: "Cari nomor, nama, atau SKU…",
    value: q,
    ariaLabel: "Cari data",
  });
  search.oninput = () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => listing(t, 0, search.value), 500);
  };
  tools.append(search, el("span", { className: "spacer" }));
  if (createActions[t])
    tools.append(
      button(createActions[t][0], () => commandForm(createActions[t][1]), true),
    );
  else if (model.editable.includes(t))
    tools.append(
      button("Tambah " + (names[t] || title(t)), () => masterForm(t), true),
    );
  if (t === "demand_lines")
    tools.append(
      button("Buat WO dari pilihan", () => planDialog(), true),
      button("Usulan minimum stok", async () =>
        modal(
          "Usulan stok minimum",
          table(t, await api("/replenishment"), [
            "product_id",
            "warehouse_id",
            "net_position",
            "open_request",
            "suggested_quantity",
          ]),
        ),
      ),
    );
  if (t === "production_orders")
    tools.append(button("Lihat kebutuhan", () => listing("demand_lines")));
  tools.append(button("Ekspor CSV", () => exportCSV(t, currentRows)));
  m.append(tools);
  const result = await api(
    `/tables/${t}?limit=50&offset=${offset}&q=${encodeURIComponent(q)}`,
  );
  currentRows = result.rows;
  cache[t] = result.rows;
  const panel = el("div", { className: "panel flush" });
  let cols;
  if (
    [
      "sales_orders",
      "purchase_orders",
      "production_orders",
      "transfer_orders",
    ].includes(t)
  ) {
    for (const r of result.rows) {
      const d = (cache.documents || []).find((d) => d.id === r.id);
      r.document_no = d?.document_no || r.id.slice(0, 8);
      r.status = d?.status || "—";
    }
    cols = [
      "document_no",
      ...Object.keys(result.rows[0] || {})
        .filter(
          (k) => !["id", "created_at", "document_no", "status"].includes(k),
        )
        .slice(0, 4),
      "status",
    ];
  }
  panel.append(table(t, result.rows, cols, (r) => detail(t, r)));
  const pager = el("div", { className: "pager" });
  pager.append(
    button("←", () => listing(t, Math.max(0, offset - 50), q)),
    el("small", {
      textContent: `${offset + 1}–${Math.min(offset + 50, result.total)} dari ${result.total}`,
    }),
    button("→", () => listing(t, offset + 50, q)),
  );
  panel.append(pager);
  m.append(panel);
}
function exportCSV(t, rs) {
  const cols = rs.length ? Object.keys(rs[0]) : [];
  const safe = (v) =>
    '"' +
    String(typeof v === "object" ? JSON.stringify(v) : (v ?? ""))
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const csv =
    "\uFEFF" +
    [cols.map(title), ...rs.map((r) => cols.map((k) => r[k]))]
      .map((a) => a.map(safe).join(","))
      .join("\r\n");
  const a = el("a", {
    href: URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    ),
    download: t + ".csv",
  });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const detailActions = {
  purchase_orders: [
    ["Konfirmasi PO", "po.confirm"],
    ["Terima sekali dan tutup PO", "po.receive"],
    ["Catat kedatangan ditolak", "po.reject"],
  ],
  sales_orders: [
    ["Konfirmasi SO", "so.confirm"],
    ["Usulkan penambahan", "so.propose_revision"],
    ["Terapkan usulan disetujui", "so.revise"],
    ["Siapkan pengiriman", "so.deliver"],
    ["Buat invoice", "so.invoice"],
    ["Batalkan SO", "so.cancel"],
  ],
  production_orders: [
    ["Mulai produksi", "wo.start"],
    ["Catat hasil produksi", "wo.complete"],
  ],
  transfer_orders: [
    ["Kirim ke transit", "transfer.dispatch"],
    ["Terima aktual", "transfer.receive"],
  ],
  transfer_discrepancies: [["Penyelesaian selisih", "transit.resolve"]],
  inventory_adjustments: [["Posting koreksi", "stock.post_adjustment"]],
  returns: [["Posting retur", "return.post"]],
  fiscal_periods: [
    ["Pemeriksaan", "checks"],
    ["Tutup periode", "period.close"],
    ["Buka kembali", "period.reopen"],
  ],
  approval_requests: [["Setujui / tolak", "approval.decide"]],
  customer_deposits: [
    ["Alokasikan DP", "deposit.apply"],
    ["Refund DP", "refund.create"],
  ],
  sync_conflicts: [
    ["Buat dokumen tinjauan", "sync.review"],
    ["Posting penyelesaian", "sync.resolve"],
  ],
  demand_lines: [["Reservasi stok", "stock.reserve"]],
  credit_notes: [
    ["Alokasikan kredit", "credit.apply"],
    ["Realisasi refund", "refund.create"],
  ],
};
async function detail(t, r) {
  selected = { table: t, row: r };
  const box = el("div");
  const nav = el("div", { className: "detail-nav" });
  for (const [label, cmd] of detailActions[t] || []) {
    nav.append(
      button(
        label,
        () =>
          cmd === "checks"
            ? api("/periods/" + r.id + "/checks").then((v) =>
                modal(
                  "Kesiapan periode",
                  table("fiscal_periods", v, ["code", "count", "passed"]),
                ),
              )
            : commandForm(cmd, { id: r.id, contextTable: t, contextRow: r }),
        cmd === "po.receive" || cmd === "so.confirm",
      ),
    );
  }
  if (model.editable.includes(t)) {
    nav.append(
      button("Ubah master", () => masterForm(t, r)),
      button("Nonaktifkan / hapus draft master", async () => {
        if (
          confirm(
            "Nonaktifkan data ini? Data yang pernah digunakan tetap tersimpan.",
          )
        ) {
          await api("/master/" + t + "/" + r.id, { method: "DELETE" });
          $("#modal").close();
          cache = {};
          await start();
        }
      }),
    );
  }
  const d = (cache.documents || []).find((x) => x.id === r.id);
  if (d) {
    nav.append(
      button("Ajukan persetujuan", () =>
        commandForm("approval.request", { id: r.id }),
      ),
      button("Riwayat / audit", async () => {
        const a = (
          await api("/tables/audit_logs?limit=100&document_id=" + r.id)
        ).rows;
        modal(
          "Riwayat dokumen",
          table("audit_logs", a, ["action", "actor_id", "occurred_at"]),
        );
      }),
    );
  }
  box.append(nav);
  const dl = el("dl", { className: "detail-grid" });
  for (const [k, v] of Object.entries(r)) {
    if (k === "id") continue;
    const div = el("div");
    div.innerHTML = `<dt>${escape(title(k))}</dt><dd>${cell(t, k, v)}</dd>`;
    dl.append(div);
  }
  box.append(dl);
  const map = {
    purchase_orders: ["purchase_order_lines", "purchase_order_id"],
    sales_orders: ["sales_order_lines", "sales_order_id"],
    production_orders: ["production_materials", "production_order_id"],
    transfer_orders: ["transfer_lines", "transfer_id"],
    goods_receipts: ["goods_receipt_lines", "receipt_id"],
    boms: ["bom_lines", "bom_id"],
    returns: ["return_lines", "return_id"],
    journal_entries: ["journal_lines", "journal_id"],
    pos_sales: ["pos_sale_lines", "pos_sale_id"],
  };
  if (map[t]) {
    const [tt, key] = map[t];
    const a = (await api(`/tables/${tt}?${key}=${r.id}&limit=500`)).rows;
    cache[tt] = a;
    box.append(el("h3", { textContent: "Rincian" }), table(tt, a));
  }
  modal(rowName(t, r), box);
}
const F = (name, ref = null, opts = {}) => ({ name, ref, ...opts });
const forms = {
  "so.create": {
    fields: [
      F("customer_id", "customers"),
      F("outlet_id", "outlets"),
      F("delivery_date", null, { type: "date" }),
      F("schedule_version_id", "schedule_versions"),
      F("fulfillment_warehouse_id", "warehouses"),
      F("price_list_id", "price_lists"),
    ],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
      F("unit_price", null, { type: "number" }),
    ],
  },
  "po.create": {
    fields: [
      F("supplier_id", "suppliers"),
      F("receiving_warehouse_id", "warehouses"),
      F("sales_order_id", "sales_orders", { optional: true }),
      F("expected_date", null, { type: "date", optional: true }),
    ],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
      F("unit_price", null, { type: "number" }),
    ],
  },
  "po.receive": {
    notice:
      "Penerimaan final hanya sekali. Kekurangan ditutup; kedatangan berikutnya dikembalikan ke supplier.",
    fields: [F("supplier_reference")],
    dynamic: "purchase_order_lines",
    lineFields: [
      F("line_id", "purchase_order_lines"),
      F("quantity", null, { type: "number" }),
      F("reason", null, { optional: true }),
    ],
  },
  "po.reject": {
    fields: [F("reason")],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
    ],
    arrayName: "items",
  },
  "so.revise": {
    notice:
      "Terapkan tepat jumlah dalam usulan terbaru yang sudah disetujui. Hanya kebutuhan selisih yang ditambahkan.",
    fields: [],
  },
  "so.propose_revision": {
    notice:
      "Jumlah dan total usulan dicatat untuk diperiksa penanggung jawab produksi.",
    fields: [F("reason")],
    dynamic: "sales_order_lines",
    lineFields: [
      F("line_id", "sales_order_lines"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "so.deliver": {
    fields: [F("recipient_name")],
    dynamic: "sales_order_components",
    lineFields: [
      F("component_id", "sales_order_components"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "so.cancel": {
    notice:
      "Tinjau reservasi, WO, DP dan PO. Barang supplier yang sudah diterima tetap owned dan dapat ditransfer ke toko.",
    fields: [F("reason")],
  },
  "wo.complete": {
    fields: [
      F("good_quantity", null, { type: "number" }),
      F("failed_quantity", null, { type: "number", optional: true }),
      F("failure_reason", null, { optional: true }),
    ],
    arrays: [
      [
        "material_returns",
        "Sisa bahan layak",
        [
          F("material_id", "production_materials"),
          F("quantity", null, { type: "number" }),
          F("warehouse_id", "warehouses"),
        ],
      ],
      [
        "byproducts",
        "Produk turunan · biaya masuk nol",
        [
          F("product_id", "products"),
          F("quantity", null, { type: "number" }),
          F("warehouse_id", "warehouses"),
        ],
      ],
    ],
  },
  "transfer.create": {
    fields: [
      F("from_warehouse_id", "warehouses"),
      F("to_warehouse_id", "warehouses"),
      F("notes", null, { optional: true }),
    ],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
      F("demand_id", "demand_lines", { optional: true }),
    ],
  },
  "transfer.receive": {
    notice:
      "Hanya jumlah aktual yang menambah stok tujuan. Sisa tetap di transit dan menjadi kasus selisih.",
    dynamic: "transfer_lines",
    lineFields: [
      F("line_id", "transfer_lines"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "transit.resolve": {
    fields: [
      F("resolution_type", null, {
        choices: [
          "in_transit",
          "returned",
          "damaged",
          "lost",
          "dispatch_error",
        ],
      }),
      F("quantity", null, { type: "number" }),
      F("confirmed_at_source", null, { type: "checkbox", optional: true }),
      F("evidence", null, { optional: true }),
      F("notes"),
    ],
  },
  "store.request": {
    fields: [
      F("warehouse_id", "warehouses"),
      F("required_date", null, { type: "date" }),
      F("schedule_version_id", "schedule_versions"),
    ],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "stock.adjust": {
    notice:
      "Saldo saat hitung dan waktu hitung harus benar. Mutasi setelah hitung tetap dipertahankan saat koreksi diposting.",
    fields: [
      F("warehouse_id", "warehouses"),
      F("counted_at", null, { type: "datetime-local", optional: true }),
      F("reason"),
    ],
    lines: [
      F("product_id", "products"),
      F("baseline_quantity", null, { type: "number" }),
      F("counted_quantity", null, { type: "number" }),
      F("unit_cost", null, { type: "number" }),
    ],
  },
  "schedule.version": {
    fields: [
      F("schedule_id", "production_schedules"),
      F("cutoff_time", null, { type: "time" }),
      F("delivery_time", null, { type: "time" }),
      F("effective_from", null, { type: "date" }),
    ],
  },
  "bom.version": {
    fields: [
      F("product_id", "products"),
      F("purpose", null, { choices: ["production", "package"] }),
      F("kitchen_id", "kitchens", { optional: true }),
      F("output_quantity", null, { type: "number" }),
      F("valid_from", null, { type: "date" }),
    ],
    lines: [
      F("product_id", "products"),
      F("quantity", null, { type: "number" }),
      F("warehouse_id", "warehouses", { optional: true }),
    ],
    arrays: [
      [
        "byproducts",
        "Produk turunan · biaya nol",
        [F("product_id", "products"), F("quantity", null, { type: "number" })],
      ],
    ],
  },
  "approval.rule": {
    fields: [
      F("action_code", null, {
        choices: [
          "purchase",
          "stock_adjustment",
          "transit_resolution",
          "production_addition",
          "production_loss",
          "cancellation",
          "return",
          "refund",
          "period_close",
          "period_reopen",
          "sync_correction",
          "pos_discount",
          "pos_refund",
          "pos_cancel",
        ],
      }),
      F("min_amount", null, { type: "number", optional: true }),
      F("max_amount", null, { type: "number", optional: true }),
      F("offline_allowed", null, { type: "checkbox" }),
    ],
    lines: [
      F("role_id", "roles", { optional: true }),
      F("user_id", "users", { optional: true }),
      F("required_count", null, { type: "number", value: 1 }),
      F("allow_self_approval", null, { type: "checkbox" }),
    ],
    arrayName: "steps",
  },
  "approval.request": {
    fields: [
      F("action_code", null, {
        choices: [
          "purchase",
          "stock_adjustment",
          "transit_resolution",
          "production_addition",
          "production_loss",
          "cancellation",
          "return",
          "refund",
          "period_close",
          "period_reopen",
          "sync_correction",
        ],
      }),
      F("reason"),
    ],
  },
  "approval.decide": {
    fields: [
      F("decision", null, { choices: ["approve", "reject"] }),
      F("reason"),
    ],
  },
  "payment.create": {
    fields: [
      F("purpose", null, {
        choices: ["deposit", "customer_payment", "supplier_payment"],
      }),
      F("customer_id", "customers", { optional: true }),
      F("supplier_id", "suppliers", { optional: true }),
      F("sales_order_id", "sales_orders", { optional: true }),
      F("amount", null, { type: "number" }),
      F("method_id", "payment_methods"),
      F("cash_bank_account_id", "cash_bank_accounts"),
      F("reference", null, { optional: true }),
    ],
    arrays: [
      [
        "allocations",
        "Alokasi pembayaran faktur",
        [F("document_id", "documents"), F("amount", null, { type: "number" })],
      ],
    ],
  },
  "deposit.apply": {
    fields: [
      F("deposit_id", "customer_deposits"),
      F("invoice_id", "sales_invoices"),
      F("amount", null, { type: "number" }),
    ],
  },
  "credit.apply": {
    fields: [
      F("credit_note_id", "credit_notes"),
      F("invoice_id", "documents"),
      F("amount", null, { type: "number" }),
    ],
  },
  "refund.create": {
    fields: [
      F("approval_document_id", "documents"),
      F("return_id", "returns", { optional: true }),
      F("deposit_id", "customer_deposits", { optional: true }),
      F("credit_note_id", "credit_notes", { optional: true }),
      F("amount", null, { type: "number" }),
      F("method_id", "payment_methods"),
      F("cash_bank_account_id", "cash_bank_accounts"),
      F("reference", null, { optional: true }),
      F("reason"),
    ],
  },
  "expense.create": {
    fields: [
      F("supplier_id", "suppliers", { optional: true }),
      F("account_id", "chart_of_accounts"),
      F("amount", null, { type: "number" }),
      F("cash_bank_account_id", "cash_bank_accounts"),
      F("description"),
    ],
  },
  "purchase.invoice": {
    fields: [
      F("goods_receipt_id", "goods_receipts"),
      F("supplier_invoice_no"),
      F("due_date", null, { type: "date", optional: true }),
    ],
    lines: [
      F("receipt_line_id", "goods_receipt_lines"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "consignment.settle": {
    fields: [
      F("supplier_id", "suppliers"),
      F("period_from", null, { type: "date" }),
      F("period_to", null, { type: "date" }),
    ],
  },
  "return.create": {
    fields: [
      F("source_document_id", "documents"),
      F("side", null, { choices: ["customer", "supplier"] }),
      F("warehouse_id", "warehouses"),
      F("supplier_id", "suppliers", { optional: true }),
      F("customer_id", "customers", { optional: true }),
      F("reason"),
    ],
    lines: [
      F("line_id", null, { label: "Identitas baris dokumen asal" }),
      F("quantity", null, { type: "number" }),
      F("condition", null, { choices: ["good", "damaged"] }),
    ],
  },
  "period.close": {
    fields: [
      F("exception_document_id", "documents", { optional: true }),
      F("reason", null, { optional: true }),
    ],
  },
  "period.reopen": { fields: [F("approval_document_id", "documents")] },
  "stock.reserve": {
    fields: [
      F("demand_id", "demand_lines"),
      F("warehouse_id", "warehouses"),
      F("quantity", null, { type: "number" }),
    ],
  },
  "sync.review": { fields: [F("conflict_id", "sync_conflicts")] },
  "sync.resolve": {
    fields: [
      F("conflict_id", "sync_conflicts"),
      F("posting_date", null, { type: "date", optional: true }),
      F("reason"),
    ],
  },
  "terminal.register": { fields: [F("code"), F("outlet_id", "outlets")] },
  "user.save": {
    fields: [
      F("username"),
      F("name"),
      F("password", null, { type: "password" }),
      F("pin", null, { type: "password", optional: true }),
    ],
    multi: ["role_ids", "roles"],
  },
};
async function inputField(f, value) {
  const div = el("div");
  const lab = el("label", {
    textContent: (f.label || title(f.name)) + (f.optional ? "" : " *"),
  });
  const id = "f-" + crypto.randomUUID();
  lab.htmlFor = id;
  let inp;
  if (f.ref || f.choices) {
    inp = el("select", { id, name: f.name });
    inp.append(el("option", { value: "", textContent: "Pilih…" }));
    const opts = f.choices
      ? f.choices.map((v) => ({ id: v, label: v }))
      : await data(f.ref);
    for (const r of opts) {
      const opt = el("option", {
        value: r.id,
        textContent: r.label || rowName(f.ref, r),
      });
      inp.append(opt);
    }
  } else {
    inp = el("input", { id, name: f.name, type: f.type || "text" });
    if (f.type === "number") {
      inp.step = "any";
      inp.min = "0";
    }
    if (f.type === "date") inp.value = today();
  }
  inp.required = !f.optional && f.type !== "checkbox";
  if (f.type === "checkbox") {
    inp.checked = Boolean(value ?? f.value ?? f.name === "active");
    div.className = "check";
    div.append(inp, lab);
  } else {
    if (value !== undefined && value !== null)
      inp.value =
        f.type === "datetime-local"
          ? new Date(value)
              .toLocaleString("sv-SE", { timeZone: "Asia/Jakarta" })
              .replace(" ", "T")
              .slice(0, 16)
          : value;
    else if (f.value !== undefined) inp.value = f.value;
    div.append(lab, inp);
  }
  return div;
}
function readInputs(container) {
  const p = {};
  for (const i of container.querySelectorAll(
    ":scope > div > input,:scope > div > select,:scope > div > textarea",
  )) {
    if (i.type === "checkbox") p[i.name] = i.checked;
    else if (i.value !== "")
      p[i.name] = i.type === "number" ? i.value : i.value;
  }
  return p;
}
async function arrayEditor(name, label, fields, initial = []) {
  const section = el("section", { className: "section" });
  section.dataset.array = name;
  section.innerHTML = `<h3>${escape(label)}</h3>`;
  const linebox = el("div");
  async function add(values = {}) {
    const row = el("div", { className: "line-row" });
    row.style.gridTemplateColumns = `repeat(${Math.min(fields.length, 5)},minmax(90px,1fr)) auto`;
    for (const f of fields) row.append(await inputField(f, values[f.name]));
    row.append(button("×", () => row.remove()));
    linebox.append(row);
  }
  section.append(
    linebox,
    button("+ Tambah baris", () => add()),
  );
  for (const v of initial) await add(v);
  return section;
}
async function commandForm(cmd, context = {}) {
  const conf = forms[cmd] || { fields: [] };
  const form = el("form");
  const error = el("div", { className: "error-text", role: "alert" });
  if (conf.notice)
    form.append(
      el("div", { className: "notice warn", textContent: conf.notice }),
    );
  const grid = el("div", { className: "form-grid" });
  for (const f of conf.fields || [])
    grid.append(await inputField(f, context[f.name]));
  form.append(grid);
  let init = [];
  let fields = conf.lines || conf.lineFields;
  if (conf.dynamic) {
    const tt = conf.dynamic;
    let rs = [];
    if (tt === "sales_order_components") {
      const sol = (
        await api("/tables/sales_order_lines?sales_order_id=" + context.id)
      ).rows;
      for (const ln of sol)
        rs.push(
          ...(
            await api(
              "/tables/sales_order_components?sales_order_line_id=" + ln.id,
            )
          ).rows,
        );
    } else {
      const key = {
        purchase_order_lines: "purchase_order_id",
        sales_order_lines: "sales_order_id",
        transfer_lines: "transfer_id",
      }[tt];
      rs = (await api(`/tables/${tt}?${key}=${context.id}&limit=500`)).rows;
    }
    cache[tt] = rs;
    for (const r of rs) {
      r._label = lookup("products", r.product_id);
      r.code = r._label;
      init.push({
        [tt === "sales_order_components" ? "component_id" : "line_id"]: r.id,
        quantity: String(
          r.qty_input ?? r.qty_required_base ?? r.qty_dispatched ?? 0,
        ),
      });
    }
  }
  if (fields)
    form.append(
      await arrayEditor(
        conf.arrayName || "lines",
        conf.arrayName === "steps" ? "Langkah persetujuan" : "Rincian",
        fields,
        init.length ? init : [{}],
      ),
    );
  for (const [n, l, fs] of conf.arrays || [])
    form.append(await arrayEditor(n, l, fs));
  if (conf.multi) {
    const [n, t] = conf.multi;
    const section = el("div", { className: "section" });
    section.innerHTML = "<h3>Peran pengguna</h3>";
    for (const r of await data(t)) {
      const lab = el("label", { className: "check" });
      lab.innerHTML = `<input type="checkbox" name="${n}" value="${escape(r.id)}"> ${escape(rowName(t, r))}`;
      section.append(lab);
    }
    form.append(section);
  }
  const footer = el("div", { className: "form-footer" });
  const submit = el("button", {
    type: "submit",
    className: "primary",
    textContent: "Simpan / jalankan",
  });
  footer.append(
    button("Batal", () => $("#modal").close()),
    submit,
  );
  form.append(error, footer);
  let key = crypto.randomUUID();
  let lastBody = "";
  form.onsubmit = async (e) => {
    e.preventDefault();
    const p = { ...readInputs(grid) };
    if (context.id) p.id = context.id;
    if (context.contextTable === "sync_conflicts") p.conflict_id = context.id;
    if (context.contextTable === "demand_lines" && cmd === "stock.reserve")
      p.demand_id = context.id;
    for (const s of form.querySelectorAll("[data-array]"))
      p[s.dataset.array] = [...s.querySelectorAll(".line-row")].map(readInputs);
    if (conf.multi)
      p[conf.multi[0]] = [
        ...form.querySelectorAll(`[name="${conf.multi[0]}"]:checked`),
      ].map((i) => i.value);
    const body = JSON.stringify(p);
    if (lastBody && body !== lastBody) key = crypto.randomUUID();
    lastBody = body;
    if (
      [
        "po.receive",
        "so.cancel",
        "transfer.dispatch",
        "stock.post_adjustment",
        "period.close",
        "return.post",
      ].includes(cmd) &&
      !confirm(
        conf.notice || "Posting tindakan ini? Riwayat dokumen akan dicatat.",
      )
    )
      return;
    submit.disabled = true;
    error.textContent = "";
    try {
      const result = await command(cmd, p, key);
      $("#modal").close();
      cache = {};
      await start();
      if (result.token) {
        const box = el("div");
        box.innerHTML =
          "<p>Simpan token ini untuk pemasangan POS. Token hanya ditampilkan sekali.</p>";
        const pre = el("pre", { textContent: result.token });
        box.append(pre);
        modal("Terminal berhasil didaftarkan", box);
      } else toast("Tindakan berhasil disimpan");
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  };
  modal(
    createActions[context.contextTable]?.[0] ||
      cmd.split(".").map(title).join(" · "),
    form,
  );
}
async function masterForm(t, r = null) {
  const spec = model.tables[t];
  const fs = spec.fields.filter(
    (f) =>
      ![
        "id",
        "created_at",
        "closed_at",
        "closed_by",
        "closing_document_id",
      ].includes(f.name),
  );
  const form = el("form");
  const grid = el("div", { className: "form-grid" });
  for (const f of fs) {
    const ref = f.ref?.split(".")[0];
    const type =
      f.type === "boolean"
        ? "checkbox"
        : f.type === "date"
          ? "date"
          : f.type === "time"
            ? "time"
            : f.type === "timestamptz"
              ? "datetime-local"
              : f.type.startsWith("decimal") ||
                  ["int", "bigint"].includes(f.type)
                ? "number"
                : "text";
    const item = await inputField(
      F(f.name, ref, { type, optional: f.nullable }),
      r?.[f.name],
    );
    if (f.type === "jsonb") {
      const i = item.querySelector("input");
      i.value = JSON.stringify(r?.[f.name] || {});
      i.dataset.json = "1";
    }
    grid.append(item);
  }
  form.append(grid);
  const err = el("div", { className: "error-text" });
  const foot = el("div", { className: "form-footer" });
  const sub = el("button", {
    type: "submit",
    className: "primary",
    textContent: "Simpan master",
  });
  foot.append(sub);
  form.append(err, foot);
  form.onsubmit = async (e) => {
    e.preventDefault();
    sub.disabled = true;
    try {
      const p = readInputs(grid);
      for (const i of grid.querySelectorAll("[data-json]"))
        p[i.name] = JSON.parse(i.value);
      await api("/master/" + t + (r ? "/" + r.id : ""), {
        method: r ? "PATCH" : "POST",
        body: JSON.stringify(p),
      });
      $("#modal").close();
      cache = {};
      await start();
      await listing(t);
      toast("Master tersimpan");
    } catch (e) {
      err.textContent = e.message;
    } finally {
      sub.disabled = false;
    }
  };
  modal((r ? "Ubah " : "Tambah ") + (names[t] || title(t)), form);
}
async function planDialog() {
  const ds = (await api("/tables/demand_lines?status=open&limit=500")).rows;
  const box = el("div");
  box.innerHTML =
    "<p>Pilih kebutuhan produksi yang kompatibel. Komponen pembelian dibuat PO tersendiri.</p>";
  for (const d of ds) {
    const label = el("label", { className: "check" });
    label.innerHTML = `<input type="checkbox" value="${escape(d.id)}">${escape(lookup("products", d.product_id))} · ${escape(d.qty_required)}`;
    box.append(label);
  }
  box.append(
    button(
      "Buat WO",
      async () => {
        const ids = [...box.querySelectorAll("input:checked")].map(
          (x) => x.value,
        );
        await command("wo.plan", { demand_ids: ids });
        $("#modal").close();
        await data("documents", true);
        await listing("production_orders");
      },
      true,
    ),
  );
  modal("Perencanaan produksi", box);
}
async function settings() {
  const m = $("#main");
  m.innerHTML =
    '<h1>Pengaturan operasional</h1><p class="subtitle">Isi nilai perusahaan dan aturan yang dapat berubah tanpa mengubah kode.</p>';
  const p = el("div", { className: "panel toolbar" });
  for (const t of [
    "schedule_versions",
    "users",
    "roles",
    "approval_rules",
    "pos_terminals",
    "fiscal_periods",
  ])
    p.append(button(names[t], () => listing(t)));
  m.append(p);
  const n = el("div", { className: "notice" });
  n.textContent =
    "H-1 tetap berlaku. Jam pagi, siang dan sore diisi melalui versi jadwal. Staf dapat bekerja lintas toko/dapur; hak tindakan mengikuti peran.";
  m.append(
    n,
    button("Pajak dan loyalty", () => policyDialog()),
  );
}
async function reports() {
  const m = $("#main");
  m.innerHTML =
    '<h1>Laporan dan penelusuran</h1><p class="subtitle">Buka rincian transaksi atau ekspor data terfilter.</p>';
  const groups = el("div", { className: "toolbar" });
  for (const t of [
    "pos_sales",
    "sales_orders",
    "stock_movements",
    "stock_balances",
    "transfer_discrepancies",
    "production_outputs",
    "production_failures",
    "purchase_invoices",
    "journal_entries",
    "audit_logs",
  ])
    groups.append(button(names[t], () => listing(t)));
  m.append(groups);
  const box = el("form", { className: "panel" });
  box.innerHTML =
    '<h2>Neraca saldo / dasar laporan keuangan</h2><div class="form-grid"><div><label for="report-start">Tanggal awal</label><input id="report-start" type="date" name="start" required></div><div><label for="report-end">Tanggal akhir</label><input id="report-end" type="date" name="end" required></div></div><div class="form-footer"><button type="submit" class="primary">Tampilkan</button></div>';
  m.append(box);
  const result = el("div", { className: "panel" });
  m.append(result);
  box.onsubmit = async (e) => {
    e.preventDefault();
    try {
      const p = new FormData(box);
      const rows = await api(
        "/reports/trial-balance?start=" +
          p.get("start") +
          "&end=" +
          p.get("end"),
      );
      result.replaceChildren(
        table("chart_of_accounts", rows, [
          "code",
          "name",
          "opening",
          "debit",
          "credit",
          "closing",
        ]),
        button("Ekspor CSV", () => exportCSV("neraca-saldo", rows)),
      );
    } catch (e) {
      toast(e.message);
    }
  };
}

async function init() {
  try {
    const s = await api("/bootstrap");
    mode = s.mode;
    if (!s.initialized) {
      renderLogin(s);
      return;
    }
    try {
      user = await api("/me");
      await start();
    } catch {
      user = null;
      renderLogin(s);
    }
  } catch (e) {
    $("#app").innerHTML =
      '<div class="loading">Aplikasi belum dapat dihubungi. Muat ulang setelah server tersedia.</div>';
  }
}
window.addEventListener("DOMContentLoaded", () => init());
