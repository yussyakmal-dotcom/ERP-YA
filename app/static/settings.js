async function policyDialog() {
  const f = el("form"),
    g = el("div", { className: "form-grid" });
  for (const d of [
    F("pos_tax_id", "taxes", { optional: true, label: "Pajak POS" }),
    F("so_tax_id", "taxes", { optional: true, label: "Pajak Sales Order" }),
    F("purchase_tax_id", "taxes", { optional: true, label: "Pajak pembelian" }),
    F("spend_per_point", null, {
      type: "number",
      label: "Belanja untuk satu poin",
      value: 0,
    }),
    F("point_value", null, {
      type: "number",
      label: "Nilai rupiah satu poin",
      value: 0,
    }),
  ])
    g.append(await inputField(d));
  f.append(
    el("div", {
      className: "notice",
      textContent:
        "Tarif dan akun diatur pada master Pajak. Nilai nol pada loyalty menonaktifkan kebijakan tersebut. Nilai ini harus disetujui perusahaan.",
    }),
    g,
  );
  const footer = el("div", { className: "form-footer" });
  footer.append(
    el("button", {
      type: "submit",
      className: "primary",
      textContent: "Simpan kebijakan",
    }),
  );
  f.append(footer);
  f.onsubmit = async (e) => {
    e.preventDefault();
    try {
      const p = readInputs(g);
      await command("settings.save", {
        key: "tax_policy",
        value: {
          pos_tax_id: p.pos_tax_id || null,
          so_tax_id: p.so_tax_id || null,
          purchase_tax_id: p.purchase_tax_id || null,
        },
      });
      await command("settings.save", {
        key: "loyalty_policy",
        value: {
          spend_per_point: p.spend_per_point,
          point_value: p.point_value,
        },
      });
      $("#modal").close();
      toast("Kebijakan disimpan. Sinkronkan kasir agar menerima versi baru.");
    } catch (e) {
      toast(e.message);
    }
  };
  modal("Pajak dan loyalty", f);
}
