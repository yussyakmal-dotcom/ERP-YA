# Panduan pemasangan 0.1.0

Mulai dengan data uji dan selesaikan UAT sebelum penggantian sistem. Tanggal bisnis/jadwal menggunakan WIB; timestamp disimpan dalam UTC.

## Backoffice

Gunakan Python 3.12+, Git dan Docker dengan Compose v2. Dari direktori repositori:

```bash
python3 scripts/configure.py cloud --output .env.cloud
docker compose --env-file .env.cloud -f compose.cloud.yml config --quiet
docker compose --env-file .env.cloud -f compose.cloud.yml up -d --build --wait
docker compose --env-file .env.cloud -f compose.cloud.yml ps
```

Generator membuat password database dan token setup acak, tidak menimpa env yang sudah ada. Simpan aman; jangan commit env. Mengganti password env tidak otomatis mengganti password PostgreSQL pada volume lama.

Buka `http://localhost:8080`, masukkan `SETUP_TOKEN` dari `.env.cloud`, lalu buat administrator pertama dengan sandi minimal 12 karakter. Setup hanya sekali. `/healthz` memeriksa koneksi aplikasi/database; definisi API di `/openapi.json`.

Server mengikat port 8080 ke localhost. Pasang reverse proxy HTTPS menuju port tersebut dan set `COOKIE_SECURE=1` untuk akses HTTPS. DNS, sertifikat, firewall dan reverse proxy perusahaan belum diterapkan oleh repositori. Database tidak membuka port ke internet.

## Data awal

Setup membuat satu perusahaan, enam toko fisik, Dahlia virtual, sepuluh dapur, packing, gudang operasional/transit, satuan, bagan akun, metode pembayaran dan periode bulan berjalan. Verifikasi nama/kode lokasi. Harga, stok, jam jadwal dan resep contoh tidak diisikan.

Lengkapi lewat Master dan Pengaturan:

1. SKU, satuan/konversi/barcode, supplier/pelanggan, harga, rekening kas/bank dan pajak bila digunakan.
2. Rute dapur, resep produksi dan paket SO. SKU putih telur menjadi byproduct biaya nol dengan harga jual sendiri.
3. Jadwal pagi/siang/sore: jam cutoff H-1 dan pengiriman melalui versi jadwal.
4. Pengguna/peran, PIN supervisor dan aturan persetujuan. Gunakan pengaju dan penyetuju berbeda kecuali kebijakan perusahaan membolehkan self approval.
5. Perjanjian titipan, target minimum toko dan promosi/loyalty bila digunakan.
6. Stok awal melalui dokumen koreksi dengan alasan `opening`, approval lalu posting. Akun lawan persediaan adalah ekuitas awal.

Hak tindakan: `master`, `users`, `purchasing`, `sales`, `production`, `inventory`, `finance`, `approvals`, `pos`, `costs`, atau `*` untuk admin. Akses tidak dibatasi per toko/dapur; aksi tetap diperiksa server. Batas nominal approval dihitung dari dokumen server. Versi ini mendukung satu aturan aktif per tindakan, batas min/max, langkah berurutan dan jumlah penyetuju; kondisi JSON tambahan ditolak.

Isi tarif pajak berupa pecahan, misalnya `0.10` sebagai contoh format, bukan tarif bawaan. Hubungkan akun pajak yang sesuai. Kebijakan pajak POS/SO/pembelian ada di Pengaturan. Akuntan perusahaan perlu memverifikasi bagan akun dan hasil jurnal sebelum UAT keuangan.

## POS per kasir

Jalankan pada masing-masing komputer dengan salinan repositori sendiri:

```bash
python3 scripts/configure.py pos --output .env.pos
docker compose --env-file .env.pos -f compose.pos.yml up -d --build --wait
```

Di Backoffice, daftarkan Terminal kasir dan pilih toko yang benar. Simpan token yang hanya tampil sekali. Buka `http://localhost:8081`, masukkan URL HTTPS Backoffice dan token. Pair/sinkronisasi pertama wajib online. Login, kemudian buka shift.

Sesuai keputusan versi awal, gunakan URL berbasis domain HTTPS, misalnya `https://erp.example.com` (contoh). Jika hanya IP server berubah dengan layanan/domain tetap sama, perbarui DNS domain; alamat tersimpan di POS tetap digunakan setelah cache DNS diperbarui. Fitur mengganti URL/IP dari pengaturan lokal POS setelah pairing **ditunda ke versi berikutnya**. Lihat [keputusan alamat Backoffice](SYNC.md).

Kasir kedua memakai instalasi, volume dan token berbeda walau tokonya sama. Jangan menyalin database POS yang sudah dipasangkan ke kasir kedua. Jika dua instalasi diuji pada satu komputer, pakai direktori terpisah, `POS_PORT` berbeda dan project Compose berbeda (`-p pos-a`, `-p pos-b`).

Saat internet mati, Docker, server lokal, database, browser dan listrik tetap harus berjalan. Cache akun berlaku 72 jam secara default. Diskon/refund offline membutuhkan aturan `offline_allowed` dengan satu supervisor dan PIN. Voucher berkuota/penukaran poin membutuhkan cloud. Akumulasi poin dapat dicatat offline lalu dibukukan saat cloud menerima event.

Cetak struk memakai dialog browser. Atur printer/kertas pada mesin kasir dan uji scanner, printer serta cash drawer nyata. Pembayaran elektronik memerlukan bukti dan verifikasi petugas; belum ada payment gateway.

## Sinkronisasi dan alur khusus

POS memulai seluruh koneksi sinkronisasi ke API cloud. Interval default 15 detik dapat diubah administrator pada POS → Sinkronisasi → Interval sinkronisasi otomatis. Pilihan cepat tersedia untuk 15, 60, dan 600 detik; angka bulat lain 1–86400 detik juga diterima. Pengaturan berlaku per mesin kasir, tersimpan pada database lokal, bertahan setelah restart dan tidak ditimpa pembaruan master dari cloud. Perubahan menghitung ulang jadwal tanpa restart; satu siklus yang sedang berjalan diselesaikan terlebih dahulu. Interval adalah jeda setelah siklus sebelumnya selesai. Tombol Coba sinkron sekarang tetap tersedia untuk menjalankan sinkronisasi manual kapan saja.

Layar Sinkronisasi membedakan tersimpan lokal dan diterima cloud. ACK setelah cloud commit, retry tidak menambah penjualan kedua kali. Jika putus koneksi, jangan menghapus volume. Pilih Coba sinkron sekarang setelah koneksi pulih. Lihat [SYNC.md](SYNC.md) untuk arah koneksi, konsekuensi interval, dan jumlah container.

Event konflik menghentikan urutan berikutnya. Untuk event periode tertutup: buat dokumen tinjauan dari Konflik sinkronisasi, buka dokumennya pada daftar Dokumen, ajukan tindakan `sync_correction`, selesaikan approval, lalu posting penyelesaian pada periode terbuka. Payload asli dan nomor struk tetap tersimpan. Payload rusak atau versi event tidak dikenal tidak dipulihkan lewat koreksi tanggal ini.

- PO diterima sekali; seluruh baris termasuk nol harus diisi. Kekurangan ditutup. Kedatangan berikutnya dicatat sebagai penolakan tanpa stok/utang.
- SO tambahan: Usulkan penambahan → isi jumlah baru/alasan → approval produksi → Terapkan usulan disetujui. Jumlah berbeda ditolak; planner membuat kebutuhan selisih saja.
- Transfer 100/98 meninggalkan 2 di transit. Resolusi penurunan transit memerlukan approval dan bukti.
- Barang supplier dari SO batal yang sudah diterima tetap owned di packing. Petugas mentransfernya ke toko untuk dijual sebagai owned.
- Retur SO memerlukan invoice pengiriman terlebih dahulu. Kredit, alokasi, dan refund merupakan dokumen terpisah.
- Kartu titipan fisik tetap manual; pilih sumber titipan saat POS menjual agar pengakuan masuk/keluar berpasangan.

## Backup dan restore

Cadangkan Backoffice **dan setiap database POS**; backup cloud tidak memuat antrean yang belum terkirim. Contoh shell Linux, jalankan dari repositori:

```bash
mkdir -p backups
docker compose --env-file .env.cloud -f compose.cloud.yml exec -T database pg_dump -U erp -d erp_ya -Fc > backups/cloud.dump
docker compose --env-file .env.pos -f compose.pos.yml exec -T database pg_dump -U erp -d erp_ya_pos -Fc > backups/pos.dump
```

Periksa exit code dan ukuran file. Pada operasional gunakan nama unik bertanggal dan kode terminal, akses terbatas, salinan terenkripsi di perangkat berbeda. Cadangkan env dan volume file juga. Belum ada layanan backup terjadwal otomatis.

Uji restore pada instalasi terisolasi dengan database kosong, tidak tersambung operasi. Contoh cloud untuk **database uji kosong**:

```bash
docker compose --env-file .env.cloud -f compose.cloud.yml up -d database
docker compose --env-file .env.cloud -f compose.cloud.yml exec -T database pg_restore -U erp -d erp_ya --no-owner --no-privileges < backups/cloud.dump
docker compose --env-file .env.cloud -f compose.cloud.yml up -d backoffice
```

Verifikasi login, stok, jurnal, transaksi terakhir dan antrean setelah restore. Jangan menghidupkan salinan POS hasil restore bersamaan dengan terminal asli dengan identitas sama. `docker compose down -v` menghapus volume; jangan dipakai untuk instalasi yang datanya harus disimpan.

## Pengembangan tanpa Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Pada shell kedua, jalankan POS dengan database berbeda:

```bash
source .venv/bin/activate
APP_MODE=pos DATABASE_URL=sqlite:///./data/pos-a.db ALLOW_INSECURE_CLOUD=1 uvicorn app.main:app --host 127.0.0.1 --port 8081
```

Pair ke `http://127.0.0.1:8080` hanya untuk pengembangan. `ALLOW_INSECURE_CLOUD=1` tidak dipakai untuk cloud nyata. SQLite dapat dibackup dengan `python scripts/backup.py data/erp.db`.

`TEST_DATABASE_URL` hanya menunjuk database PostgreSQL uji bernama akhiran `_test`; fixture menghapus seluruh tabel pada database uji. Jalankan `python -m pytest -q`.

Browser smoke opsional: pasang Playwright dan Chromium pada lingkungan pengembangan, lalu `python scripts/smoke_browser.py`. Data fiktif sementara, port 8765/8766. `CHROMIUM_EXECUTABLE` dapat menunjuk binary Chromium yang tersedia.

Versi ini membuat schema awal dan mencatat versi, belum mempunyai migrasi antarversi produksi. Sebelum upgrade struktur database nyata, siapkan backup terverifikasi dan migrasi eksplisit; simpan commit aplikasi yang cocok dengan backup.
