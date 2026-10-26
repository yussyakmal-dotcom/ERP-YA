# Validasi build 0.1.0

Pemeriksaan dengan data fiktif, 26 Oktober 2026 WIB. Tidak membuat transaksi perusahaan nyata.

| Pemeriksaan | Hasil lokal |
| --- | --- |
| Regresi otomatis SQLite | 50 passed, satu peringatan library pengujian; 18,28 detik pada pemeriksaan final |
| Browser Backoffice | Setup, login, dashboard, tambah produk berhasil; tanpa JavaScript page error pada alur tersebut |
| Browser POS | Pair, login, buka shift, cloud dimatikan, jual barang, struk, tutup shift, antrean persisten berhasil |
| Rekonsiliasi browser POS | Kas awal 200.000 + penjualan 8.000 = tutup 208.000, selisih nol; tiga event antrean |
| Syntax JavaScript | Node check pada app.js, pos.js, settings.js |
| Docker/PostgreSQL lokal | Belum dijalankan di workspace; Docker tidak tersedia |

Suite meliputi PO hanya sekali/concurrent/final short/zero, transfer 100/98/2 dan lima resolusi, snapshot resep, konsumsi otomatis dan rollback kekurangan, putih telur nol biaya, produksi gagal, planner tanpa duplikasi/tambahan, DP/invoice/alokasi, harga/tender, stok minus/HPP, titipan, retur/refund kumulatif, approval/revisi/opname dan jurnal seimbang.

Pengujian API/sync meliputi sesi/CSRF, hash tersembunyi, penolakan tulis ledger, idempotency, dua kasir independen, retry/ACK, UUID berubah, overlay snapshot, restart antrean, batas mode, lock login, cache expired, tanda tangan event dan konflik periode tertutup. Pengujian commerce/otorisasi mencakup promo, pajak inclusive/exclusive, voucher eksklusif, poin, earned point reversal, pajak retur parsial sampai sen terakhir, invoice supplier dan batas nominal dari server.

Workflow CI menjalankan suite pada SQLite dan PostgreSQL 17. Job container juga memeriksa build image dan startup kedua mode dengan database PostgreSQL terpisah. Lihat tab Actions pada commit yang dipakai untuk hasil aktual; definisi workflow saja bukan bukti run lulus.

Belum diuji menyeluruh: 40 UAT perusahaan, audit keamanan independen, load/soak panjang, perangkat kasir fisik, callback bank, backup/restore PostgreSQL produksi, migrasi sistem lama dan deploy server perusahaan. Browser smoke memakai SQLite dan cloud sengaja dimatikan; hasilnya tidak membuktikan semua kondisi jaringan/perangkat.
