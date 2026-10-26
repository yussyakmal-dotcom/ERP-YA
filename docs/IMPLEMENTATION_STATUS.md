# Cakupan implementasi 0.1.0

26 Oktober 2026 WIB. Build awal dapat dijalankan untuk UAT; belum siap mengganti seluruh sistem operasional. PRD/ERD v1.0 tetap target bisnis.

| Area | Tersedia di kode | Batas saat ini |
| --- | --- | --- |
| Pembelian | PO/approval, satu penerimaan final, tutup kekurangan, penolakan kedatangan, invoice, retur | Selisih harga invoice dari penerimaan ditolak; workflow koreksi harga belum tersedia |
| SO | Paket satu harga/komponen, H-1, DP, delivery parsial, invoice, cancel/refund, usulan tambahan terikat approval | Paket bertingkat, editor perubahan harga/pengurangan setelah konfirmasi belum tersedia |
| Produksi | Planner SO/permintaan/minimum, WO kompatibel, BOM snapshot, bahan otomatis, hasil/sisa/scrap/byproduct | Batch/expiry/FEFO tetap ditunda sesuai keputusan |
| Stok | Moving average, ledger, reservasi, transfer/transit, lima resolusi, opname delta | Migrasi massal dan rekonsiliasi stok sistem lama belum dilakukan |
| Titipan | Masuk/keluar ketika dijual POS, kartu fisik manual, settlement bersih retur | Barang supplier SO batal ditransfer petugas ke toko sebagai owned |
| POS | Katalog/barcode, harga, produk/kemasan terpisah, split tender, struk, shift/kas, retur/refund supervisor | Struk terminal lain diretur di Backoffice; belum ada pencarian lintas terminal langsung dari POS |
| Offline/sync | DB/outbox atomik, event berurutan, UUID/hash/HMAC, retry/ACK, overlay saldo, konflik | Full master snapshot; cache incremental dan uji beban cabang belum ada |
| Harga/pajak | Snapshot, diskon supervisor, promo global fixed/percent, pajak inclusive/exclusive POS/SO/beli | Promo per item/kombinasi kompleks dan faktur pajak elektronik belum ada |
| Voucher/loyalty | Cloud hold eksklusif, penukaran poin, accrual saat cloud replay, pembalikan earned points retur | Voucher/poin ditukar tidak otomatis diterbitkan kembali; perlu kebijakan perusahaan |
| Keuangan | Double entry, DP/kredit/refund/alokasi terpisah, beban, neraca saldo, close/reopen | P&L, neraca berformat final, aging dan laporan manajemen khusus belum selesai |
| Akses/approval | Pengguna/peran, langkah berurutan, revisi, nominal server, PIN offline, audit | Satu aturan aktif per tindakan; kondisi tambahan/cabang approval per nominal belum ada |
| UI | Dashboard, master/form transaksi, detail/audit, konflik, kasir lokal | Beberapa layar berbagi komponen; belum identik 1:1 semua wireframe. Retur Backoffice masih meminta referensi baris dokumen |
| Operasional | Docker/cloud dan Docker/POS, persistent volume, konfigurasi rahasia, runbook | TLS/server nyata, monitoring, backup otomatis dan migrasi belum disiapkan |

## Kebijakan build untuk UAT

- Minus hanya POS dengan alasan; HPP provisional diselesaikan ketika persediaan masuk.
- White egg masuk nol biaya; telur dibebankan hasil utama. Sisa layak kembali pada biaya pengeluaran semula.
- Mutasi titipan berpasangan tidak mengubah average cost owned atau menyelesaikan minus owned.
- Retur SO dilakukan setelah invoice. Nilai paket untuk kredit komponen dialokasikan berdasarkan jumlah unit komponen; akuntan perlu menguji dengan contoh perusahaan.
- Cache akun offline default 72 jam; maksimal lima gagal login/PIN, lock 15 menit. Perubahan master/akun baru efektif di POS setelah sync.
- Hold voucher/poin tidak kedaluwarsa otomatis karena penjualan offline mungkin belum terkirim; batalkan dari POS sebelum penjualan jika tidak digunakan.
- Retur membalik earned points proporsional. Jika sudah dibelanjakan, saldo dapat negatif dan accrual berikutnya menutupnya. Kebijakan penerbitan ulang manfaat belum diimplementasikan.
- Status pembayaran elektronik verified berasal dari verifikasi petugas, belum callback bank.
- Command tulis diserialisasi per instalasi untuk menjaga atomisitas; throughput belum dibuktikan melalui uji beban.
- Akun posting menggunakan kode COA awal. Kode akun tersebut harus dipertahankan; bagan akun/pemetaan perlu disahkan akuntan.

## Model fisik

104 entitas bisnis dari JSON/DBML, ditambah enam tabel infrastruktur di `app/db.py`: `app_sessions`, `app_tokens`, `app_commands`, `app_security`, `app_schema_versions`, `app_redemptions`. Tabel tambahan menyimpan sesi, hash token terminal, idempotency, percobaan autentikasi, versi schema, dan reservasi manfaat bersama; tidak mengganti model bisnis.

Ledger/jurnal tidak dibuka melalui CRUD master. Saldo dan snapshot periode merupakan cache turunan. Schema awal dibuat otomatis; migrasi antarversi harus disiapkan sebelum upgrade produksi.

## Syarat sebelum penggantian sistem

1. Isi data perusahaan, jam, harga, pajak, resep, saldo dan matriks approval; sahkan kebijakan keuangan/refund/manfaat.
2. Selesaikan workflow dan laporan yang belum tersedia pada tabel di atas.
3. Jalankan seluruh 40 skenario UAT pada data nyata yang diizinkan serta rekonsiliasi sistem lama. Test otomatis bukan persetujuan UAT.
4. Uji server dan setiap kasir, printer/scanner/drawer, listrik padam, dua kasir bersamaan, antrean panjang dan koneksi putus berkepanjangan.
5. Uji backup/restore, migrasi, keamanan, monitoring, TLS, pemulihan, serta rencana cutover dan rollback.
