# Sinkronisasi POS dan Backoffice

Addendum spesifikasi v1.0, 26 Oktober 2026 WIB. Dokumen ini mencatat arah koneksi, pengaturan interval, dan susunan container yang dibahas setelah build awal.

## Koneksi selalu dimulai POS

Backoffice menyediakan API HTTPS yang dapat dijangkau kasir. Seluruh koneksi sinkronisasi dimulai oleh aplikasi POS; POS tidak memerlukan IP publik atau port forwarding. Backoffice membalas melalui koneksi yang dibuka POS.

| Permintaan dari POS | Tujuan |
| --- | --- |
| `POST /api/sync/events` | Unggah antrean aktivitas shift, penjualan, pembayaran, kas dan retur/refund |
| `GET /api/sync/snapshot` | Unduh master, harga, aturan dan saldo stok toko terbaru |

Penjualan dan antreannya disimpan dalam transaksi database lokal yang sama. POS mengirim berurutan dengan identitas event unik, Backoffice memvalidasi/membukukan, lalu membalas setelah commit. Pengiriman ulang event yang sudah diterima mengembalikan hasil yang sama. Saldo stok resmi dihitung dari transaksi gabungan setiap kasir, bukan penimpaan dengan saldo lokal.

## Interval melalui pengaturan aplikasi

Pada implementasi ini administrator membuka **POS → Sinkronisasi → Interval sinkronisasi otomatis**. Tersedia pilihan cepat:

| Nilai | Jeda |
| --- | --- |
| 15 detik | 15 detik |
| 60 detik | 1 menit |
| 600 detik | 10 menit |

Input juga menerima angka bulat 1–86400 detik. Nilai awal 15 detik digunakan sebelum terminal mempunyai konfigurasi tersimpan.

Pengaturan disimpan per mesin pada `settings`, key `pos_sync_policy`, field `interval_seconds`. Setiap perubahan berversi dan diaudit. Perubahan memerlukan hak `users` atau `*`, sesi valid dan CSRF. Kasir dengan hak `pos` dapat melihat interval tetapi tidak mengubahnya. Endpoint lokal: `GET` dan `PUT /api/pos/sync-settings`.

Nilai bertahan setelah aplikasi/komputer dimulai ulang dan tidak ditimpa snapshot cloud. Jadwal otomatis dihitung ulang ketika pengaturan disimpan, tanpa restart. Siklus yang sedang berjalan diselesaikan dahulu; jeda berikutnya dihitung setelah siklus selesai. Mengurangi interval panjang tidak membuat worker menunggu seluruh interval lama. Tombol **Coba sinkron sekarang** tetap memulai proses langsung dari POS tanpa menunggu interval otomatis.

Pada interval 600 detik, laporan cloud dan stok yang diterima kasir lain dapat tertunda sekitar satu interval ditambah waktu proses/jaringan. Ketika internet putus, antrean tetap berada dalam database lokal. POS mencoba kembali sesuai interval setelah percobaan sebelumnya selesai. Dua kasir offline belum mengetahui transaksi satu sama lain melalui rancangan cloud ini.

## Jumlah container Docker

| Instalasi | Container aplikasi | Container database | Jumlah |
| --- | --- | --- | --- |
| Backoffice di cloud | Backoffice/API | PostgreSQL pusat | 2 |
| Setiap komputer kasir | POS | PostgreSQL lokal POS | 2 |

Satu Backoffice dan satu kasir berarti **4 container**. Satu Backoffice dan dua kasir berarti **6 container**. Rumus: `2 + (2 × jumlah mesin kasir)`.

Compose cloud dan Compose POS berjalan pada host masing-masing. Setiap database memakai volume persisten sendiri. Dua mesin kasir di toko yang sama memakai identitas terminal dan database yang berbeda; aplikasi POS mengirim transaksi ke Backoffice melalui API.

## Pemeriksaan perubahan interval

Pengujian mencakup pilihan 15/60/600, penyimpanan setelah restart, isolasi antar terminal, snapshot cloud tidak menimpa interval, audit dan penolakan akses/angka tidak valid. Pengujian worker mengubah jeda aktif 600 detik menjadi 1 detik lalu kembali 600 tanpa restart, serta memeriksa sinkron manual saat interval panjang. Browser smoke mengubah interval menjadi 600 ketika server cloud dimatikan, memuat ulang halaman, lalu memastikan nilainya tetap tersimpan dan antrean transaksi tetap utuh.
