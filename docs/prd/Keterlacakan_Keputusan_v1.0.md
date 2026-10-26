# Keterlacakan Keputusan ERP Yussy Akmal
Versi 1.0 | 25 Oktober 2026

Nomor bagian mengacu PRD. D01-D18 mengikuti klarifikasi pengguna; D19 mengikuti sumber awal yang tidak diganti; D20 mencakup keputusan Docker dan rancangan persistensi. Detail teknis tambahan ditandai sebagai rancangan pada PRD/ERD.

| ID | Keputusan | Bagian PRD | Entitas utama | Uji |
| --- | --- | --- | --- | --- |
| D01 | Seluruh sistem satu perusahaan | 01-02 | companies, documents | U38-U40 |
| D02 | PO hanya satu receive; kedatangan susulan ditolak | 08 | purchase_orders, goods_receipts, supplier_arrival_rejections | U01-U02 |
| D03 | Stok transit dan selisih wajib tercatat | 13 | transfer_orders, transfer_receipts, transfer_discrepancies, transfer_resolutions | U08-U10 |
| D04 | Batch dan kedaluwarsa ditunda | 01,14 | Tidak ada lot/expiry entity versi pertama | Review konfigurasi |
| D05 | Titipan POS diakui saat terjual | 09 | consignment_agreements, consignment_sales, stock_movements | U06-U07 |
| D06 | Barang supplier SO memakai PO per SO | 08-10 | purchase_orders.sales_order_id, purchase_order_lines.demand_id | U03 |
| D07 | SO batal barang supplier ke toko sebagai owned | 09,15 | stock_reservations, transfer_orders, pos_sale_lines.stock_source | U04-U05 |
| D08 | DP, retur, refund sejak awal | 10,15-16 | customer_deposits, deposit_applications, returns, credit_notes, refunds | U22-U25,U36 |
| D09 | Permintaan toko dan minimum stok | 11 | store_requests, replenishment_policies, demand_lines | U14 |
| D10 | Paket SO satu harga; POS per barang dan kemasan | 06,10 | sales_order_lines, sales_order_components, pos_sale_lines | U15-U16 |
| D11 | Bahan sesuai BOM; sisa layak dikembalikan | 12 | production_materials, production_material_returns | U17-U19 |
| D12 | Biaya telur ke utama; putih telur biaya masuk nol | 12,14 | bom_byproducts, production_outputs | U20-U21 |
| D13 | Jam jadwal dalam tabel, cutoff H-1 | 10 | production_schedules, schedule_versions | U11-U12 |
| D14 | Tambahan setelah WO memerlukan approval produksi | 04,10-11 | approval_requests, production_orders.parent_wo_id, wo_demand_allocations | U13,U32 |
| D15 | Tabel persetujuan; staf tidak dibatasi lokasi | 04 | users, roles, user_roles, approval_rules, approval_steps | U32-U33 |
| D16 | Supervisor boleh otorisasi saat offline | 04,06 | approval_actions, approval_rules.offline_allowed | U30,U32 dan uji policy offline |
| D17 | Semua SO beserta pembayaran di backoffice | 05,10,16 | sales_orders, sales_invoices, customer_deposits, payments | U22-U23 |
| D18 | Dua mesin kasir masing-masing POS lokal dan sync | 05-07,18 | pos_terminals, sync_outbox, sync_inbox, sync_checkpoints | U26-U29 |
| D19 | Rata-rata tertimbang; POS boleh minus | 06,14 | stock_movements, negative_stock_cases, inventory_cost_adjustments | U18,U31 |
| D20 | Docker dengan database persisten | 18-19 | Migrasi dan volume, bukan tabel khusus | U29,U38,U40 |