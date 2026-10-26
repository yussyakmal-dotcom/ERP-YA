# Validasi build 0.1.0

Pemeriksaan dengan data fiktif, 26 Oktober 2026 WIB. Tidak membuat transaksi perusahaan nyata.

| Pemeriksaan | Hasil lokal |
| --- | --- |
| Regresi otomatis SQLite | 55 passed, satu peringatan library pengujian; 22,59 detik setelah penambahan pengaturan interval |
| Browser Backoffice | Setup, login, dashboard, tambah produk berhasil; tanpa JavaScript page error pada alur tersebut |
| Browser POS | Pair, login, buka shift, cloud dimatikan, jual barang, struk, tutup shift, antrean persisten berhasil |
| Rekonsiliasi browser POS | Kas awal 200.000 + penjualan 8.000 = tutup 208.000, selisih nol; tiga event antrean |
| Syntax JavaScript | Node check pada app.js, pos.js, settings.js |
| Docker/PostgreSQL lokal | Belum dijalankan di workspace; Docker tidak tersedia |

Suite meliputi PO hanya sekali/concurrent/final short/zero, transfer 100/98/2 dan lima resolusi, snapshot resep, konsumsi otomatis dan rollback kekurangan, putih telur nol biaya, produksi gagal, planner tanpa duplikasi/tambahan, DP/invoice/alokasi, harga/tender, stok minus/HPP, titipan, retur/refund kumulatif, approval/revisi/opname dan jurnal seimbang.

Pengujian API/sync meliputi sesi/CSRF, hash tersembunyi, penolakan tulis ledger, idempotency, dua kasir independen, retry/ACK, UUID berubah, overlay snapshot, restart antrean, batas mode, lock login, cache expired, tanda tangan event dan konflik periode tertutup. Pengujian commerce/otorisasi mencakup promo, pajak inclusive/exclusive, voucher eksklusif, poin, earned point reversal, pajak retur parsial sampai sen terakhir, invoice supplier batas nominal dari server, jadwal H-1 dan tanggal produksi WIB, waktu struk yang tetap sama saat replay, serta beberapa WO dalam satu perintah idempoten.

Workflow CI menjalankan suite pada SQLite dan PostgreSQL 17. Job container juga memeriksa build image dan startup kedua mode dengan database PostgreSQL terpisah. Lihat tab Actions pada commit yang dipakai untuk hasil aktual; definisi workflow saja bukan bukti run lulus.

Belum diuji menyeluruh: 40 UAT perusahaan, audit keamanan independen, load/soak panjang, perangkat kasir fisik, callback bank, backup/restore PostgreSQL produksi, migrasi sistem lama dan deploy server perusahaan. Browser smoke memakai SQLite dan cloud sengaja dimatikan; hasilnya tidak membuktikan semua kondisi jaringan/perangkat.

## CI build awal

[Run 40257733670](https://github.com/yussyakmal-dotcom/ERP-YA/actions/runs/40257733670), commit `801981c8bcf764a6de5b24e06b50768ca2578154`, selesai sukses pada 26 Oktober 2026.

| Job | Hasil |
| --- | --- |
| SQLite | 52 test lulus; syntax tiga berkas JavaScript lulus |
| PostgreSQL 17 | 52 test lulus pada database uji terpisah |
| Containers | Build image sukses; Backoffice dan POS masing-masing hidup dengan PostgreSQL/volume sendiri dan endpoint health sukses |

Job container memeriksa build/startup, bukan UAT bisnis lengkap melalui Docker. Bukti POS offline berasal dari browser smoke lokal; batas pemeriksaan di atas tetap berlaku.

## Pengaturan interval sinkronisasi

Tambahan 26 Oktober 2026: interval otomatis per POS dapat diubah dari aplikasi tanpa restart, termasuk 15, 60, dan 600 detik. Suite lokal bertambah menjadi **55 test lulus**. Pengujian memeriksa penyimpanan per terminal/restart, snapshot cloud tidak menimpa interval, audit, akses administrator, validasi, penjadwalan ulang saat worker aktif, dan sinkron manual saat interval panjang.

Browser smoke kembali lulus dengan server cloud dimatikan: penjualan/struk/tutup shift dan tiga event antrean tetap utuh; administrator mengganti interval ke 600 detik dari layar POS, memuat ulang halaman, lalu nilai 600 tetap tersimpan. Hasil CI build awal di atas merujuk commit sebelum tambahan ini; hasil CI perubahan interval tercatat di bawah.

### CI pengaturan interval

[Run 40261299260](https://github.com/yussyakmal-dotcom/ERP-YA/actions/runs/40261299260), commit `5c1ec05257278f56cc92beff0891bbd0b001eab3`, selesai sukses pada 26 Oktober 2026. SQLite dan PostgreSQL 17 masing-masing **55 test lulus**; build/startup kedua mode Docker dan pemeriksaan syntax JavaScript juga lulus. Pengujian Docker tetap sebatas build/startup; batas UAT perusahaan/perangkat fisik di atas tidak berubah.
