# Spesifikasi UI ERP Bakery Yussy Akmal v1.0
25 Oktober 2026 | Rancangan berdasarkan PRD/ERD v1.0

## Status dan cakupan
Desain usulan statis: 30 layar Backoffice, 8 layar POS, 6 alur. Semua data transaksi/harga contoh adalah ilustrasi. Identitas merek belum final. Tidak ada backend, transaksi nyata, atau klaim UAT telah lulus.

## Aturan lintas layar
- Backoffice: seluruh SO/DP/pelunasan/refund SO, pembelian, produksi, gudang, keuangan, master dan pengaturan. POS: penjualan toko, shift, retur/refund POS, persetujuan lokal dan status sinkronisasi.
- Tidak ada pembatasan lokasi staf. Hak tindakan dan melihat biaya tetap sesuai peran.
- UI menampilkan WIB; jumlah dengan satuan eksplisit; uang IDR. Tidak ada batch/expiry.
- Daftar/detail memiliki pencarian, filter, paginasi, status, audit, lampiran dan dokumen terkait. Status filter tidak boleh mengubah hak akses.
- Field berlabel * wajib. Tombol posting memvalidasi ulang di server/lokal sesuai pemilik transaksi; tombol UI bukan batas otorisasi.
- Transaksi posted tidak dapat dihapus. Perubahan material memerlukan revisi dan approval baru.
- Layar empty/loading/error/no-access/stale-revision/offline/pending/success harus tersedia. Retry transaksi memakai identitas semula.
- Jadwal tanpa jam lengkap tidak boleh diaktifkan. Jam dan nama approver tidak ditebak oleh desain.

## Navigasi dan pola layar turunan
Master pendukung (supplier, pelanggan, lokasi, satuan, rekening, pajak, terminal) menggunakan pola daftar BO-02 dan formulir BO-25/30. Variasi faktur, retur, dan pembayaran dijelaskan pada layar terkait. Wireframe mewakili layar utama; dialog dan field kondisional mengikuti kontrak di bawah.

## BO-01 - Ringkasan operasional
Modul: Dashboard
Tujuan: Prioritaskan pekerjaan yang perlu tindakan hari ini.

### Isi dan aksi
- Aksi: Lihat persetujuan; Buka selisih transit.

### Perilaku dan validasi
- **Filter lintas lokasi**: Pilihan toko dan dapur adalah filter tampilan, bukan pembatasan akses staf. Angka dapat dibuka sampai dokumen sumber.
- **Peringatan yang dapat ditindaklanjuti**: Selisih transit, pesanan mendekati kirim, dan terminal belum sinkron dipisahkan. Data cloud menampilkan waktu pemutakhiran.
- **Tindakan berikutnya**: Klik kartu membuka daftar terfilter. Tugas persetujuan hanya muncul bagi peran yang berhak.

### Pemetaan
- Lanjut ke: BO-02, BO-15, BO-24
- Entitas: `documents`, `stock_balances`, `approval_requests`, `sync_conflicts`
- UAT PRD: Kontrol navigasi dan hak tindakan

## BO-02 - Sales Order
Modul: Penjualan SO
Tujuan: Semua pesanan pelanggan dikelola melalui backoffice.

### Isi dan aksi
- Cari pesanan: Nomor SO / nama pelanggan
- Tanggal kirim: 26 - 27 Okt 2026
- Jadwal: Semua jadwal
- Status: Semua status
- Kolom: Pesanan / pelanggan, Kirim / jadwal, Nilai, Status.
- Aksi: Ekspor daftar; Buat SO.

### Perilaku dan validasi
- **Daftar dan detail**: Klik baris membuka BO-04. Filter outlet asal dan pelanggan tersedia dalam filter lanjutan.
- **Pesanan tambahan**: Label tambahan setelah WO membedakan kebutuhan revisi dari kebutuhan semula. Approval mengikuti penanggung jawab produksi.
- **Batas kanal**: Menu SO dan pembayaran SO tidak tersedia di aplikasi POS.

### Pemetaan
- Lanjut ke: BO-03, BO-04
- Entitas: `sales_orders`, `sales_order_lines`, `documents`
- UAT PRD: U11, U13

## BO-03 - Buat pesanan pelanggan
Modul: Penjualan SO
Tujuan: Paket tampil satu harga; komponen menjadi dasar pemenuhan.

### Isi dan aksi
- Pelanggan *: Pelanggan A
- Outlet asal *: Dahlia
- Tanggal pesan: 25 Okt 2026
- Tanggal kirim *: 26 Okt 2026
- Jadwal *: Pagi - versi tersimpan
- Alamat / instruksi: Alamat pengiriman pelanggan
- Kolom: Item pesanan, Jumlah, Harga satuan, Total.
- Aksi: Simpan draft; Konfirmasi SO.
- Pesan utama: H-1 wajib. Jam cutoff dan kirim mengikuti konfigurasi jadwal; bukan isian bebas kasir.

### Perilaku dan validasi
- **Komponen paket**: Panel komponen berisi produk dapur, produk supplier, dan kemasan. Snapshot dibuat saat konfirmasi; paket bertingkat ditolak.
- **Validasi sebelum konfirmasi**: Tanggal harus setelah tanggal pesan; satu SO satu jadwal. Jadwal tanpa jam lengkap tidak dapat digunakan. Tambahan setelah WO masuk approval.
- **Aksi dan transisi**: Simpan draft tidak memesan stok. Konfirmasi yang lolos validasi membuat kebutuhan; DP tetap dicatat melalui BO-04.

### Pemetaan
- Lanjut ke: BO-04, BO-09
- Entitas: `sales_orders`, `sales_order_lines`, `sales_order_components`, `schedule_versions`, `demand_lines`
- UAT PRD: U11, U12, U13, U15

## BO-04 - Detail SO dan pembayaran
Modul: Penjualan SO
Tujuan: SO-1026-012 / Pelanggan A / 100 snack box

### Isi dan aksi
- Aksi: Catat DP / pelunasan; Siapkan pengiriman.

### Perilaku dan validasi
- **Pembayaran di satu tempat**: Tab Pembayaran memisahkan DP diterima, alokasi ke invoice, pelunasan, dan refund. DP tidak otomatis menjadi pendapatan.
- **Dokumen saling terhubung**: Tab Pemenuhan menautkan WO, PO khusus SO, reservasi, dan delivery. Paket dijual satu harga; komponen tidak menambah omzet lagi.
- **Perubahan setelah konfirmasi**: Revisi menyimpan versi sebelumnya. Perubahan setelah WO memerlukan approval dan hanya menambah kebutuhan selisih.

### Pemetaan
- Lanjut ke: BO-05, BO-12, BO-20
- Entitas: `sales_orders`, `customer_deposits`, `deposit_applications`, `sales_invoices`, `payments`, `deliveries`
- UAT PRD: U13, U15, U22

## BO-05 - Pembatalan SO dan refund
Modul: Penjualan SO
Tujuan: Tinjau dampak pembatalan sebelum mengajukan persetujuan.

### Isi dan aksi
- Dokumen asal *: SO-1026-012
- Alasan *: Pelanggan membatalkan acara
- Saldo DP tersedia: Rp1.000.000
- Refund diajukan *: Rp1.000.000
- Barang supplier diterima: 40 pcs di packing
- Tujuan pengalihan: Toko tujuan - pilih
- Kolom: Objek terdampak, Posisi sekarang, Tindak lanjut.
- Aksi: Kembali ke SO; Ajukan pembatalan.
- Pesan utama: Utang supplier tetap berlaku. Setelah delivery, gunakan retur penjualan; jangan hapus SO.

### Perilaku dan validasi
- **Konfirmasi berdampak**: Dialog akhir merangkum refund, reservasi, WO, dan PO. Tidak ada pengembalian bahan otomatis untuk WO yang sudah berjalan.
- **Barang untuk dijual di toko**: Buat transfer setelah pembatalan disetujui. Barang diterima toko sebagai stok milik perusahaan; POS tidak mengakuinya sebagai titipan baru.
- **Refund terpisah**: Persetujuan batal tidak berarti uang telah dikirim. BO-20 mencatat realisasi dana dan bukti pembayaran.

### Pemetaan
- Lanjut ke: BO-13, BO-20, BO-22
- Entitas: `sales_orders`, `approval_requests`, `refunds`, `transfer_orders`, `stock_reservations`
- UAT PRD: U04, U05, U23

## BO-06 - Purchase Order
Modul: Pembelian
Tujuan: PO reguler atau PO khusus pemenuhan satu Sales Order.

### Isi dan aksi
- Jenis PO *: Khusus SO
- Sales Order *: SO-1026-012
- Supplier *: Supplier A
- Gudang penerima: Packing - terkunci untuk SO
- Tanggal dokumen *: 25 Okt 2026
- Status: Draft
- Kolom: Barang supplier, Jumlah pesan, Satuan, Referensi.
- Aksi: Simpan draft; Ajukan / konfirmasi PO.
- Pesan utama: PO khusus SO hanya terhubung ke satu SO. Komponen pembelian tidak dibuat WO.

### Perilaku dan validasi
- **Daftar dan pencarian**: Daftar PO memakai pola BO-02 dengan filter supplier, jenis, SO, dan status penerimaan. Detail menampilkan jumlah pesan dan aktual terpisah.
- **Kontrol persetujuan**: Tombol konfirmasi mengikuti aturan approval. Perubahan nilai atau baris membatalkan persetujuan revisi sebelumnya.
- **Penerimaan**: Setelah PO confirmed, penerimaan hanya melalui BO-07 satu kali. Retur supplier tidak membuka PO kembali.

### Pemetaan
- Lanjut ke: BO-07, BO-22
- Entitas: `purchase_orders`, `purchase_order_lines`, `approval_requests`
- UAT PRD: U01, U03, U32

## BO-07 - Penerimaan final PO
Modul: Pembelian
Tujuan: PO-1026-031 / Tepung terigu / Supplier B

### Isi dan aksi
- PO: PO-1026-031
- Gudang tujuan: CDC
- Tanggal terima *: 25 Okt 2026
- Surat jalan supplier *: SJ-SUP-001
- Kolom: Barang, Pesan, Aktual terima *, Kurang ditutup.
- Aksi: Simpan draft; Terima dan tutup PO.
- Pesan utama: Satu kali penerimaan: sisa 5 dus ditutup. Barang berikutnya untuk PO ini harus dikembalikan.

### Perilaku dan validasi
- **Dialog sebelum posting**: Tampilkan: pesan 10 dus, diterima 5, kekurangan ditutup 5. Persetujuan sadar pengguna diperlukan melalui tombol Terima 5 dan tutup PO.
- **Validasi jumlah**: Tidak boleh lebih dari pesan. Semua baris harus diisi, termasuk nol beralasan. Jika seluruh baris nol, catat penolakan tanpa penerimaan.
- **Sesudah berhasil**: Status menjadi Selesai - kurang ditutup. Tombol receive diganti Lihat penerimaan dan Catat kedatangan ditolak. Konflik dua petugas tidak membuat penerimaan kedua.

### Pemetaan
- Lanjut ke: BO-08, BO-20
- Entitas: `goods_receipts`, `goods_receipt_lines`, `purchase_orders`
- UAT PRD: U01, U02

## BO-08 - Kedatangan ditolak
Modul: Pembelian
Tujuan: Catat bukti kedatangan setelah PO selesai diterima.

### Isi dan aksi
- PO asal *: PO-1026-031 / sudah selesai
- Tanggal kedatangan *: 26 Okt 2026
- Barang / jumlah *: Tepung terigu / 5 dus
- Alasan: PO sudah diterima final
- Tindakan: Dikembalikan ke supplier
- Bukti *: Foto surat jalan / tanda terima
- Kolom: Riwayat penerimaan, Diterima, Kekurangan ditutup, Status.
- Aksi: Kembali ke PO; Simpan penolakan.
- Pesan utama: Catatan ini tidak menambah stok atau utang dan tidak membuka penerimaan baru.

### Perilaku dan validasi
- **Tujuan layar**: Petugas mencatat kejadian fisik yang perlu audit. Tidak ada tombol Terima sisa.
- **Dokumen terkait**: Tautkan foto, petugas, waktu kedatangan, dan bukti pengembalian. Catatan dapat dibuka dari detail PO.
- **Bedakan dengan retur**: Barang belum pernah diakui memakai penolakan ini. Barang yang sudah diterima memakai retur supplier BO-19.

### Pemetaan
- Lanjut ke: BO-06, BO-19
- Entitas: `supplier_arrival_rejections`, `attachments`, `purchase_orders`
- UAT PRD: U01, U36

## BO-09 - Perencanaan kebutuhan
Modul: Produksi
Tujuan: Gabungkan kebutuhan tanpa menghitung permintaan dua kali.

### Isi dan aksi
- Tanggal produksi: 26 Okt 2026
- Jadwal: Pagi
- Dapur: Semua dapur
- Sumber kebutuhan: SO + toko + minimum stok
- Kolom: SKU / sumber, Kebutuhan bersih, Pemenuhan, Alokasi.
- Aksi: Tinjau alokasi; Buat WO / PO terpilih.
- Pesan utama: Stok tersedia, reservasi, transit, dan kebutuhan terbuka diperhitungkan sebelum usulan dibuat.

### Perilaku dan validasi
- **Penggabungan WO**: Gabung hanya SKU, dapur, versi BOM, tanggal, dan jadwal yang kompatibel. Detail alokasi tetap menunjukkan setiap demand asal.
- **Bukan posting otomatis**: Usulan minimum stok menjadi draft untuk ditinjau. Permintaan toko yang sudah terlayani tidak dibuat dua kali.
- **Pesanan tambahan**: Sesudah WO dibuat, tambahan tampil terpisah dengan status Menunggu approval. Hanya selisih disetujui yang masuk WO tambahan.

### Pemetaan
- Lanjut ke: BO-10, BO-06, BO-17
- Entitas: `demand_lines`, `wo_demand_allocations`, `production_orders`, `store_request_lines`, `replenishment_policies`
- UAT PRD: U13, U14, U17

## BO-10 - Perintah produksi
Modul: Produksi
Tujuan: WO-1026-008 / Dapur 01 / Roti A

### Isi dan aksi
- Target hasil: 100 pcs
- Versi resep: BOM Roti A / v3
- Tanggal / jadwal: 26 Okt 2026 / Pagi
- Status: Siap dimulai
- Kolom: Bahan snapshot, Kebutuhan, Sumber, Ketersediaan.
- Aksi: Lihat alokasi demand; Mulai produksi.
- Pesan utama: Mulai produksi mengeluarkan seluruh bahan otomatis sesuai snapshot BOM. Stok bahan tidak boleh minus.

### Perilaku dan validasi
- **Pemeriksaan sebelum mulai**: Tampilkan bahan yang kurang dan tautan pemenuhan. Satu bahan tidak cukup membatalkan seluruh start; tidak ada pemakaian parsial diam-diam.
- **Snapshot dan tambahan**: Resep master yang berubah tidak mengubah WO ini. Bahan di luar BOM harus melalui revisi/koreksi terotorisasi.
- **Setelah dimulai**: Tombol berubah menjadi Catat penyelesaian. Pengeluaran bahan tertaut dan tidak dapat diedit sebagai saldo langsung.

### Pemetaan
- Lanjut ke: BO-11, BO-25
- Entitas: `production_orders`, `production_materials`, `boms`, `bom_lines`, `wo_demand_allocations`
- UAT PRD: U17, U18

## BO-11 - Penyelesaian produksi
Modul: Produksi
Tujuan: Catat hasil aktual, sisa layak, produk gagal, dan turunan.

### Isi dan aksi
- Aksi: Simpan draft hasil; Selesaikan produksi.

### Perilaku dan validasi
- **Empat kelompok pencatatan**: Hasil utama 96 pcs, gagal 4 pcs, sisa tepung layak 0,5 kg, dan putih telur 3 kg adalah data ilustrasi. Setiap kelompok punya tujuan dan satuan sendiri.
- **Biaya putih telur nol**: Kolom biaya hasil turunan terkunci Rp0. Seluruh biaya telur tetap pada produk utama. Harga jual diatur di master harga, bukan di penyelesaian WO.
- **Validasi penyelesaian**: Sisa layak tidak melebihi pengeluaran asal. Bila hasil utama nol, minta approval kerugian produksi. Hasil kurang menyisakan demand terbuka.

### Pemetaan
- Lanjut ke: BO-13, BO-09
- Entitas: `production_outputs`, `production_material_returns`, `production_failures`, `production_materials`
- UAT PRD: U19, U20, U21

## BO-12 - Packing dan pengiriman SO
Modul: Penjualan SO
Tujuan: Pesanan paket diperiksa melalui komponen fisiknya.

### Isi dan aksi
- Sales Order *: SO-1026-012
- Gudang sumber: Packing
- Rencana kirim: 26 Okt 2026 / Pagi
- Tujuan: Alamat pelanggan
- Kolom: Komponen, Dibutuhkan, Tersedia / reserved, Kirim sekarang.
- Aksi: Cetak daftar packing; Posting pengiriman.
- Pesan utama: Paket SO tetap satu harga. Pengurangan stok mengikuti komponen; tidak ada stok paket fiktif.

### Perilaku dan validasi
- **Pengiriman sebagian**: Tampilkan jumlah tersisa per baris dan komponen. Tidak boleh melebihi kebutuhan tersisa atau stok yang sah.
- **Pemeriksaan packing**: Komponen dibeli berasal dari PO khusus SO; komponen produksi berasal dari hasil yang sudah diterima packing.
- **Dokumen sesudah posting**: Cetak surat jalan dan tautkan delivery, invoice, dan saldo pembayaran pada BO-04. Koreksi setelah delivery melalui retur.

### Pemetaan
- Lanjut ke: BO-04, BO-19
- Entitas: `deliveries`, `delivery_lines`, `sales_order_components`, `stock_reservations`
- UAT PRD: U03, U15, U22

## BO-13 - Kirim transfer antar lokasi
Modul: Gudang & transit
Tujuan: TR-1026-044 / Packing ke Toko 01

### Isi dan aksi
- Gudang asal *: Packing
- Gudang tujuan *: Toko 01
- Tanggal kirim *: 26 Okt 2026
- Petugas / kendaraan: Petugas pengiriman
- Kolom: Barang, Tersedia, Jumlah kirim *, Alokasi.
- Aksi: Simpan draft; Kirim ke transit.
- Pesan utama: Saat dikirim: stok asal berkurang, stok transit bertambah. Stok toko belum bertambah.

### Perilaku dan validasi
- **Pilih rute yang sah**: Premik melalui CDC; WIP bisa antardapur; produk final melalui packing. Rute retur/koreksi tetap tersedia sesuai dokumen asal.
- **Validasi stok**: Stok tidak boleh minus dan reservasi milik pesanan lain tidak boleh dipakai. Validasi ulang saat posting.
- **Bukti pengiriman**: Setelah dispatch, tampilkan surat jalan dan status Dalam perjalanan. Jumlah terkirim tidak diedit; koreksi lewat selisih tertaut.

### Pemetaan
- Lanjut ke: BO-14, BO-15
- Entitas: `transfer_orders`, `transfer_lines`, `stock_movements`
- UAT PRD: U08

## BO-14 - Terima transfer di toko
Modul: Gudang & transit
Tujuan: TR-1026-044 / Roti A / Packing ke Toko 01

### Isi dan aksi
- Jumlah dikirim: 100 pcs
- Sudah diterima: 0 pcs
- Sisa di transit: 100 pcs
- Diterima sekarang *: 98 pcs
- Kolom: Barang, Terima aktual, Sisa transit, Tindak lanjut.
- Aksi: Simpan draft; Terima 98 pcs.
- Pesan utama: 98 pcs masuk stok toko. Dua pcs tetap di transit sampai penyelesaian dicatat.

### Perilaku dan validasi
- **Berjalan di backoffice**: Petugas toko memakai backoffice untuk penerimaan. Aplikasi POS tidak mempunyai modul penerimaan gudang.
- **Penerimaan berikutnya**: Transfer boleh diterima bertahap sampai sisa transit habis. Aturan receive sekali hanya berlaku untuk PO supplier.
- **Lebih dari sisa transit**: Jumlah di atas sisa ditolak dengan pesan yang jelas. Kelebihan fisik dicatat sebagai kasus pemeriksaan, bukan stok otomatis.

### Pemetaan
- Lanjut ke: BO-15, BO-16
- Entitas: `transfer_receipts`, `transfer_receipt_lines`, `transfer_discrepancies`
- UAT PRD: U08

## BO-15 - Penyelesaian selisih transit
Modul: Gudang & transit
Tujuan: SEL-1026-006 / TR-1026-044 / 2 pcs belum selesai

### Isi dan aksi
- Aksi: Simpan tindak lanjut; Ajukan penyelesaian.

### Perilaku dan validasi
- **Masih dalam perjalanan**: Simpan penanggung jawab dan tanggal tindak lanjut. Status kasus tetap terbuka, dua pcs tetap transit.
- **Perubahan stok perlu bukti**: Kembali packing membutuhkan konfirmasi tiba. Salah kirim membutuhkan bukti hitung dan koreksi tertaut. Rusak/hilang mengikuti approval kerugian.
- **Terima kemudian**: Buka penerimaan tambahan BO-14. Penyelesaian sebagian diperbolehkan sampai jumlah seluruh keputusan sama dengan sisa kasus.

### Pemetaan
- Lanjut ke: BO-14, BO-22
- Entitas: `transfer_discrepancies`, `transfer_resolutions`, `approval_requests`, `stock_movements`
- UAT PRD: U08, U09, U10

## BO-16 - Stok dan kartu mutasi
Modul: Gudang & transit
Tujuan: Saldo, reservasi, dan transit ditampilkan terpisah.

### Isi dan aksi
- Gudang: Toko 01
- SKU: Roti A
- Rentang tanggal: 25 - 26 Okt 2026
- Sumber stok: Milik perusahaan
- Kolom: Waktu / sumber, Masuk, Keluar, Saldo / status.
- Aksi: Lihat valuasi; Ekspor kartu stok.
- Pesan utama: Contoh: stok layak 78 pcs, reservasi 10 pcs, tersedia 68 pcs. Transit adalah lokasi terpisah.

### Perilaku dan validasi
- **Bisa ditelusuri**: Klik dokumen sumber untuk melihat baris transaksi dan jurnal. Filter biaya hanya terlihat bagi pengguna yang memiliki hak.
- **Anomali POS**: Saldo negatif ditandai bersama HPP provisional dan penyesuaian tertaut. Gudang dan produksi tetap tidak boleh minus.
- **Titipan dan kedaluwarsa**: Barang titipan belum terjual ada di kartu manual, bukan saldo owned. Tidak ada filter batch atau tanggal kedaluwarsa versi pertama.

### Pemetaan
- Lanjut ke: BO-18, BO-28
- Entitas: `stock_balances`, `stock_movements`, `stock_reservations`, `negative_stock_cases`, `inventory_cost_adjustments`
- UAT PRD: U06, U31

## BO-17 - Permintaan toko dan minimum stok
Modul: Produksi
Tujuan: Usulan tambahan menuju target dihitung setelah kebutuhan terbuka.

### Isi dan aksi
- Toko *: Toko 01
- Tanggal dibutuhkan *: 26 Okt 2026
- Jadwal *: Pagi
- Sumber: Permintaan toko / usulan minimum
- Kolom: SKU, Posisi bersih, Minimum / target, Usulan baru.
- Aksi: Simpan draft; Kirim permintaan.
- Pesan utama: Posisi bersih memasukkan stok tersedia, transit, dan pemenuhan terbuka yang relevan. Buka rincian perhitungan.

### Perilaku dan validasi
- **Toko tidak mengelola di POS**: Permintaan dibuat dari backoffice. Pilihan toko tidak membatasi akses staf ke toko lain.
- **Cegah duplikasi**: Jika 80 pcs sudah menjadi permintaan terbuka, penghitungan berikutnya tidak mengusulkan 80 pcs lagi.
- **Pengaturan kebijakan**: Tab Kebijakan menyimpan minimum, target, kelipatan dan sumber. Nilai pada wireframe hanyalah contoh, bukan konfigurasi final.

### Pemetaan
- Lanjut ke: BO-09
- Entitas: `store_requests`, `store_request_lines`, `replenishment_policies`, `demand_lines`
- UAT PRD: U14

## BO-18 - Opname dan koreksi stok
Modul: Gudang & transit
Tujuan: Hitungan fisik menjadi koreksi yang tertelusur.

### Isi dan aksi
- Gudang *: Toko 01
- Waktu hitung *: 26 Okt 2026 / 10:00 WIB
- Alasan *: Opname rutin
- Bukti: Lembar hitung fisik
- Kolom: SKU, Saldo saat hitung, Fisik, Selisih.
- Aksi: Simpan hitungan; Ajukan koreksi.
- Pesan utama: Mutasi sesudah waktu hitung direkonsiliasi sebelum posting. Jangan menimpa saldo sekarang dengan jumlah fisik lama.

### Perilaku dan validasi
- **Koreksi bukan edit saldo**: Simpan basis hitung, waktu, mutasi setelah hitung, dan koreksi final. Approval mengikuti nilai/kuantitas sesuai tabel.
- **Reservasi dan stok tersedia**: Jika koreksi mengganggu reservasi, arahkan ke penyelesaian reservasi terlebih dahulu. Pengurangan tidak boleh membuat stok minus.
- **Dokumen posted**: Dokumen yang sudah posted hanya dapat dikoreksi melalui dokumen pembalik/terkait, bukan dihapus.

### Pemetaan
- Lanjut ke: BO-22, BO-16
- Entitas: `inventory_adjustments`, `inventory_adjustment_lines`, `stock_movements`, `approval_requests`
- UAT PRD: U32, U37

## BO-19 - Retur barang
Modul: Pembelian / penjualan
Tujuan: Pilih transaksi asal sebelum mencatat barang kembali.

### Isi dan aksi
- Jenis retur *: Ke supplier
- Dokumen asal *: GR-1026-019
- Pihak terkait: Supplier B
- Gudang sumber *: CDC
- Alasan *: Kualitas tidak sesuai
- Penyelesaian nilai: Kredit supplier
- Kolom: Barang asal, Diterima / dijual, Pernah retur, Retur sekarang.
- Aksi: Simpan draft; Ajukan / posting retur.
- Pesan utama: Jumlah kumulatif retur tidak boleh melebihi transaksi asal. Retur supplier tidak membuka PO untuk receive ulang.

### Perilaku dan validasi
- **Dua varian backoffice**: Retur supplier merujuk goods receipt; retur pelanggan SO merujuk delivery/invoice. Retur POS dilakukan pada PS-06.
- **Kondisi barang**: Retur pelanggan meminta kondisi layak/rusak dan disposisi. Hanya barang layak masuk stok jual; barang rusak mengikuti kerugian/klaim.
- **Nilai dan uang terpisah**: Posting retur menautkan kredit. Refund atau kompensasi faktur dicatat terpisah di BO-20; batas hak pengembalian diperiksa.

### Pemetaan
- Lanjut ke: BO-20, BO-22
- Entitas: `returns`, `return_lines`, `credit_notes`, `credit_applications`, `refunds`
- UAT PRD: U24, U25, U36

## BO-20 - Pembayaran dan refund
Modul: Keuangan
Tujuan: Alokasikan pembayaran hanya ke saldo yang masih terbuka.

### Isi dan aksi
- Jenis transaksi *: Penerimaan DP pelanggan
- Pelanggan / supplier *: Pelanggan A
- Referensi *: SO-1026-012
- Metode / rekening *: Transfer / rekening perusahaan
- Jumlah *: Rp1.000.000
- Bukti / referensi *: Nomor referensi pembayaran
- Kolom: Dokumen tujuan, Saldo terbuka, Alokasi, Sesudah alokasi.
- Aksi: Simpan draft; Posting pembayaran.
- Pesan utama: DP, pelunasan, invoice, dan refund SO seluruhnya di backoffice. Satu penerimaan tidak dihitung dua kali.

### Perilaku dan validasi
- **Varian transaksi**: Penerimaan DP, pelunasan pelanggan, bayar supplier, dan realisasi refund menggunakan field sesuai jenis. Pilihan jenis tidak boleh mengubah dokumen asal diam-diam.
- **Batas alokasi**: Nilai tidak boleh melampaui pembayaran dan saldo dokumen. Refund dibatasi hak pengembalian setelah kredit/kompensasi dan refund sebelumnya.
- **Bukti keberhasilan**: Sesudah posting tampil nomor pembayaran, alokasi, jurnal, dan tautan dokumen. Kegagalan kirim tidak boleh menyebabkan posting ganda.

### Pemetaan
- Lanjut ke: BO-04, BO-21, BO-29
- Entitas: `payments`, `payment_allocations`, `customer_deposits`, `deposit_applications`, `refunds`, `refund_allocations`
- UAT PRD: U22, U23

## BO-21 - Tutup periode
Modul: Keuangan
Tujuan: Pemeriksaan harus selesai atau mendapat pengecualian terotorisasi.

### Isi dan aksi
- Periode: Oktober 2026
- Status: Terbuka
- Pemeriksaan terakhir: Belum dijalankan
- Periode sesudahnya: Belum ditutup
- Kolom: Pemeriksaan, Hasil contoh, Status, Tindakan.
- Aksi: Jalankan pemeriksaan; Ajukan tutup periode.
- Pesan utama: Buka kembali memerlukan approval. Tidak boleh membuka periode lama ketika periode sesudahnya sudah ditutup.

### Perilaku dan validasi
- **Checklist lengkap**: Termasuk draft belum posted, penerimaan belum ditagih, saldo DP dan pengecualian lain. Tampilkan pemilik tindak lanjut dan bukti persetujuan.
- **Event offline terlambat**: Tanggal transaksi asli dipertahankan. Posting pada periode terbuka mengikuti otorisasi koreksi, bukan mengubah jurnal lama.
- **Setelah ditutup**: Layar menjadi baca saja dan menunjukkan snapshot saldo. Tombol Buka kembali muncul hanya jika hak dan prasyarat terpenuhi.

### Pemetaan
- Lanjut ke: BO-24, BO-22, BO-29
- Entitas: `fiscal_periods`, `account_period_balances`, `journal_entries`, `approval_requests`
- UAT PRD: U34, U35, U39

## BO-22 - Pusat persetujuan
Modul: Persetujuan
Tujuan: Tinjau dokumen, dampak, dan revisi yang diajukan.

### Isi dan aksi
- Aksi: Tolak dengan alasan; Setujui revisi ini.

### Perilaku dan validasi
- **Peran menentukan tindakan**: Akses staf lintas toko/dapur tetap tersedia. Hak menyetujui ditentukan tabel tindakan, nilai, langkah, dan penyetuju.
- **Revisi terikat approval**: Perubahan material membatalkan persetujuan sebelumnya. Jika orang lain mengubah dokumen saat dibuka, minta muat ulang dan tinjau ulang.
- **Audit keputusan**: Simpan identitas penyetuju, waktu, alasan, dan metode otorisasi. Rancangan awal melarang persetujuan sendiri kecuali aturan eksplisit.

### Pemetaan
- Lanjut ke: BO-26, BO-07, BO-15
- Entitas: `approval_rules`, `approval_steps`, `approval_requests`, `approval_actions`, `audit_logs`
- UAT PRD: U13, U32, U33

## BO-23 - Jadwal dan batas pesanan
Modul: Pengaturan
Tujuan: Pagi, siang, dan sore memakai versi konfigurasi.

### Isi dan aksi
- Zona waktu: Asia/Jakarta / WIB
- Aturan hari: H-1 - tetap
- Tanggal mulai berlaku *: Pilih tanggal
- Status versi: Draft konfigurasi
- Kolom: Jadwal, Jam batas H-1 *, Jam pengiriman *, Status.
- Aksi: Simpan draft; Aktifkan versi.
- Pesan utama: Nilai jam belum ditentukan pengguna. Aktivasi hanya setelah semua jam wajib valid.

### Perilaku dan validasi
- **Tidak hardcode**: Jam cutoff dan kirim bisa diubah melalui tabel. Hari tetap H-1 sesuai keputusan bisnis.
- **Snapshot pesanan**: SO terkonfirmasi mempertahankan jadwal lama. Pesanan baru menggunakan versi yang berlaku.
- **Pesan validasi**: Jadwal Pagi belum lengkap. Isi jam batas dan jam kirim sebelum aktivasi. Jangan mengganti isian kosong dengan jam perkiraan.

### Pemetaan
- Lanjut ke: BO-03
- Entitas: `production_schedules`, `schedule_versions`, `sales_orders`
- UAT PRD: U11, U12

## BO-24 - Monitor sinkronisasi POS
Modul: Sinkronisasi
Tujuan: Pantau setiap terminal; transaksi lokal tidak boleh hilang.

### Isi dan aksi
- Toko: Semua toko
- Status: Semua
- Tanggal bisnis: 26 Okt 2026
- Pencarian: Terminal / nomor struk
- Kolom: Terminal / lokasi, Sinkron terakhir, Antrean / konflik, Status.
- Aksi: Lihat rekonsiliasi; Buka konflik.
- Pesan utama: Antrean terminal offline adalah status terakhir yang diterima cloud. Jumlah lokal terbaru baru diketahui setelah tersambung.

### Perilaku dan validasi
- **Dua terminal independen**: Setiap terminal memiliki identitas dan antrean sendiri. Cloud menggabungkan kejadian; jangan menimpa saldo toko dengan saldo lokal.
- **Tinjau konflik**: Drawer menampilkan struk asli, alasan, versi kebijakan, dan tindakan terotorisasi. Tidak ada tombol Hapus transaksi agar antrean bersih.
- **Rekonsiliasi harian**: Bandingkan jumlah struk, nilai tender, event diterima, dan dokumen posted per terminal. Tandai periode tertutup atau payload berbeda.

### Pemetaan
- Lanjut ke: BO-21, BO-29
- Entitas: `pos_terminals`, `sync_inbox`, `sync_checkpoints`, `sync_conflicts`
- UAT PRD: U26, U27, U28, U29, U35, U40

## BO-25 - Produk dan resep
Modul: Master
Tujuan: SKU, satuan, rute dapur, dan BOM berversi.

### Isi dan aksi
- Aksi: Simpan draft versi; Aktifkan versi BOM.

### Perilaku dan validasi
- **Master produk**: Field utama: SKU, nama, kategori, satuan dasar, barcode per satuan, dapat dijual/dibeli/diproduksi, jenis premik/WIP/paket dan aktif.
- **Konversi dan BOM**: Faktor satuan per SKU; resep menyimpan hasil standar, gudang bahan, dapur dan hasil turunan. Versi baru tidak mengubah transaksi lama.
- **Putih telur dan paket**: Putih telur adalah SKU tersendiri. Penerimaan sebagai turunan berbiaya nol; harga jual terpisah. Paket SO bersifat phantom dan tidak boleh bersarang.

### Pemetaan
- Lanjut ke: BO-09, BO-10, BO-30
- Entitas: `products`, `product_uoms`, `product_kitchen_routes`, `boms`, `bom_lines`, `bom_byproducts`
- UAT PRD: U15, U17, U20

## BO-26 - Pengguna dan matriks akses
Modul: Pengaturan
Tujuan: Hak tindakan mengikuti peran; akses tidak dibatasi toko atau dapur.

### Isi dan aksi
- Pengguna: Staf operasional
- Peran *: Pilih satu / beberapa peran
- Status akun: Aktif
- Kebijakan offline: Sesuai peran dan masa berlaku
- Kolom: Tindakan, Melihat, Mengerjakan, Menyetujui.
- Aksi: Lihat audit perubahan; Simpan konfigurasi.
- Pesan utama: Tidak ada pembatasan staf berdasarkan toko/dapur. Terminal tetap memiliki gudang penjualan yang ditetapkan.

### Perilaku dan validasi
- **Matriks persetujuan**: Tab Aturan berisi tindakan, rentang nilai/kuantitas, urutan langkah, peran/pengguna, masa berlaku dan izin offline.
- **PIN supervisor**: Pengaturan PIN dilakukan aman dan tidak pernah ditampilkan kembali. POS menerima kebijakan berversi, bukan PIN polos.
- **Perubahan sensitif**: Hak melihat biaya, posting, diskon, dan buka periode dipisahkan. Audit menyimpan nilai sebelum/sesudah dan pelaku.

### Pemetaan
- Lanjut ke: BO-22, PS-05
- Entitas: `users`, `roles`, `user_roles`, `approval_rules`, `approval_steps`, `pos_terminals`
- UAT PRD: U32, U33

## BO-27 - Titipan dan settlement supplier
Modul: Pembelian
Tujuan: Kewajiban berdasarkan penjualan bersih, bukan stok fisik manual.

### Isi dan aksi
- Supplier *: Supplier titipan A
- Periode *: 1 - 25 Okt 2026
- Toko: Toko 01
- Status settlement: Draft
- Kolom: Barang titipan, Terjual, Retur, Bersih / kewajiban.
- Aksi: Lihat rincian struk; Posting settlement.
- Pesan utama: Contoh harga supplier Rp5.000/pcs. Fisik belum terjual tetap di kartu manual, bukan penerimaan sistem.

### Perilaku dan validasi
- **Perjanjian supplier**: Tab Perjanjian memuat SKU, toko, harga supplier, masa berlaku dan aturan settlement. Harga disimpan sebagai snapshot ketika POS menjual.
- **Pemisahan sumber barang**: Barang supplier dari SO batal yang sudah diterima adalah owned. Jangan masukkan lagi ke settlement titipan.
- **Retur setelah dibayar**: Buat kredit/klaim supplier tertaut. Nilai settlement tidak ditimpa dan penjualan yang sama tidak dibayar dua kali.

### Pemetaan
- Lanjut ke: BO-20, PS-03
- Entitas: `consignment_agreements`, `consignment_sales`, `consignment_settlements`, `consignment_settlement_lines`
- UAT PRD: U05, U06, U07, U25

## BO-28 - Laporan dan penelusuran
Modul: Laporan
Tujuan: Setiap angka terhubung ke transaksi sumber.

### Isi dan aksi
- Aksi: Ekspor XLSX / PDF; Buka rincian.

### Perilaku dan validasi
- **Kelompok laporan**: Penjualan; persediaan/transit/valuasi; produksi; pembelian; keuangan; kontrol dan audit. Gunakan tanggal bisnis dan filter kanal/lokasi.
- **Angka tidak berganda**: Omzet paket tidak ditambah omzet komponennya. Kuantitas gram, pcs, dan ml tidak dijumlahkan menjadi satu total.
- **Hak dan snapshot**: Biaya hanya bagi peran berhak. Gunakan harga/pajak transaksi asal. Label waktu pembaruan membantu membaca data POS yang belum sinkron.

### Pemetaan
- Lanjut ke: BO-16, BO-24, BO-29
- Entitas: `documents`, `journal_entries`, `journal_lines`, `stock_movements`, `pos_sales`, `sales_invoices`
- UAT PRD: U15, U31, U39

## BO-29 - Faktur, beban, dan jurnal
Modul: Keuangan
Tujuan: Dokumen posted ditelusuri dan dikoreksi melalui reversal.

### Isi dan aksi
- Aksi: Lihat dokumen sumber; Posting dokumen.

### Perilaku dan validasi
- **Varian faktur**: Faktur supplier merujuk penerimaan bersih; kumulatif tagihan tidak boleh melebihi penerimaan. Invoice pelanggan merujuk penjualan/pengiriman yang sah.
- **Beban periode**: Tab Beban mencatat jasa, tenaga kerja, dan overhead sebagai beban periode. Tidak dialokasikan sebagai biaya produk dalam versi pertama.
- **Jurnal dan koreksi**: Debit wajib sama dengan kredit. Setelah posted, aksi edit/hapus diganti Buat koreksi. COA, pajak dan pemetaan akun tetap konfigurasi perusahaan.

### Pemetaan
- Lanjut ke: BO-20, BO-21, BO-28
- Entitas: `purchase_invoices`, `purchase_invoice_lines`, `sales_invoices`, `expenses`, `journal_entries`, `journal_lines`, `chart_of_accounts`, `taxes`
- UAT PRD: U22, U36, U39

## BO-30 - Harga, promosi, dan master pendukung
Modul: Master
Tujuan: Pengaturan harga per kanal dan periode berlaku.

### Isi dan aksi
- Daftar harga: Semua daftar / ringkasan
- Masa berlaku: Pilih tanggal mulai / akhir
- Kanal: Semua kanal
- Status: Draft
- Kolom: SKU, Satuan, Harga jual contoh, Aturan kanal.
- Aksi: Buat daftar harga; Buka daftar terpilih.
- Pesan utama: Harga di layar hanya contoh. Perubahan harga tidak menghitung ulang transaksi yang sudah diposting.

### Perilaku dan validasi
- **Promosi dan loyalty**: Tab Promosi menyimpan diskon, voucher, dan loyalty. POS offline boleh memakai promosi lokal; penukaran saldo bersama/voucher berkuota perlu online.
- **Master lain**: Pola daftar-detail berlaku untuk supplier, pelanggan, lokasi, UOM, rekening, pajak, metode pembayaran, dan terminal. Nonaktifkan data yang telah digunakan.
- **Harga per kanal**: Buka satu daftar untuk mengedit kanal, periode, dan harga. Aktivasi membuat versi baru untuk disinkronkan; tampilkan status terminal yang belum menerima versi itu.

### Pemetaan
- Lanjut ke: BO-25, BO-24, PS-02
- Entitas: `price_lists`, `price_list_items`, `promotion_rules`, `vouchers`, `loyalty_accounts`, `suppliers`, `customers`, `payment_methods`
- UAT PRD: U12, U16

## PS-01 - Masuk dan buka shift
Modul: POS lokal
Tujuan: Toko 01 / Terminal K01 / aplikasi lokal

### Isi dan aksi
- Aksi: Periksa printer; Buka shift.

### Perilaku dan validasi
- **Identitas terminal**: Toko dan gudang berasal dari registrasi terminal, bukan dipilih bebas setiap penjualan. Kasir masuk dengan akun miliknya.
- **Satu shift aktif**: Kas awal wajib. Jika ada shift aktif, arahkan Lanjutkan shift alih-alih membuat shift kedua.
- **Saat offline**: Akun dan kebijakan lokal harus masih valid. Jika login offline tidak dapat diverifikasi, tampilkan alasan dan langkah pemulihan tanpa menghapus data.

### Pemetaan
- Lanjut ke: PS-02, PS-08
- Entitas: `pos_terminals`, `pos_shifts`, `users`
- UAT PRD: U29, U40

## PS-02 - Penjualan kasir
Modul: POS lokal
Tujuan: Scan, pilih barang, lalu terima pembayaran.

### Isi dan aksi
- Aksi: Tahan keranjang; Bayar Rp30.000.

### Perilaku dan validasi
- **Produk dan kemasan terpisah**: Contoh keranjang: roti 2 x Rp8.000, risol 2 x Rp6.000, kemasan Rp2.000. Total Rp30.000 sebelum diskon/pajak terkonfigurasi.
- **Status selalu terlihat**: Tampilkan koneksi, sinkron terakhir, antrean, terminal, dan shift. Stok lokal diberi label perkiraan saat offline; penjualan minus perlu alasan.
- **Batas POS**: Tidak ada menu SO, DP SO, pembelian, produksi, atau penerimaan toko. Pilihan sumber muncul bila SKU punya owned dan titipan.

### Pemetaan
- Lanjut ke: PS-03, PS-04, PS-05
- Entitas: `pos_sales`, `pos_sale_lines`, `pos_shifts`, `stock_balances`
- UAT PRD: U05, U16, U26, U31

## PS-03 - Pilih sumber barang
Modul: POS lokal
Tujuan: SKU yang sama dapat berasal dari stok owned atau titipan.

### Isi dan aksi
- Aksi: Kembali ke keranjang; Gunakan sumber terpilih.

### Perilaku dan validasi
- **Pilihan eksplisit**: Kasir memilih berdasarkan asal barang fisik. Jangan otomatis mengubah owned menjadi titipan ketika stok terlihat habis.
- **Owned dari SO batal**: Barang ini sudah diakui saat penerimaan PO. Penjualan hanya mengurangi stok dan mencatat penjualan; tidak membentuk utang supplier baru.
- **Titipan**: Sistem mencatat masuk dan terjual bersamaan. Jika perjanjian/harga supplier tidak tersedia lokal, pilihan titipan dinonaktifkan dengan alasan.

### Pemetaan
- Lanjut ke: PS-02, BO-27
- Entitas: `pos_sale_lines`, `consignment_agreements`, `consignment_sales`
- UAT PRD: U05, U06, U07

## PS-04 - Pembayaran dan struk
Modul: POS lokal
Tujuan: Selesaikan penjualan lokal sebelum mencetak struk.

### Isi dan aksi
- Aksi: Kembali ke keranjang; Selesaikan pembayaran.

### Perilaku dan validasi
- **Split tender**: Satu penjualan boleh beberapa metode. Jumlah pembayaran harus memenuhi total; kembalian hanya dari bagian tunai.
- **Pembayaran elektronik**: Mode offline tidak berarti QRIS/kartu otomatis terverifikasi. Minta bukti/status valid atau tawarkan tunai; jangan menampilkan sukses palsu.
- **Sesudah commit lokal**: Tampilkan nomor struk unik terminal dan status Tersimpan lokal. Cetak gagal memberi Cetak ulang - Salinan; jangan membuat penjualan kedua.

### Pemetaan
- Lanjut ke: PS-02, PS-08
- Entitas: `pos_sales`, `pos_tenders`, `payment_methods`, `sync_outbox`
- UAT PRD: U26, U27, U29

## PS-05 - Persetujuan supervisor offline
Modul: POS lokal
Tujuan: Diskon khusus, pembatalan, dan refund mengikuti aturan lokal.

### Isi dan aksi
- Aksi: Batalkan permintaan; Setujui tindakan.

### Perilaku dan validasi
- **Terikat transaksi**: Tampilkan tindakan, nilai, alasan, kasir, nomor struk/draft, dan versi kebijakan. PIN tidak berlaku sebagai pembukaan semua akses.
- **Otorisasi lokal**: Supervisor yang hadir menggunakan akun/PIN tersinkron. Catat identitas, terminal, waktu dan kebijakan pada keputusan.
- **Jika tidak valid**: Kredensial kedaluwarsa, hak tidak cukup, atau terlalu banyak percobaan menunda tindakan khusus. Penjualan biasa dapat tetap dilanjutkan.

### Pemetaan
- Lanjut ke: PS-02, PS-06
- Entitas: `approval_requests`, `approval_actions`, `approval_rules`, `sync_outbox`
- UAT PRD: U32, U33

## PS-06 - Retur dan refund POS
Modul: POS lokal
Tujuan: Cari struk asal, pilih barang dan kondisi, lalu otorisasi.

### Isi dan aksi
- Aksi: Simpan draft retur; Minta persetujuan.

### Perilaku dan validasi
- **Batas offline**: Saat offline hanya transaksi lokal yang tersedia dapat diretur. Struk terminal lain menunggu validasi cloud agar tidak refund ganda.
- **Jumlah dan kondisi**: Retur kumulatif dibatasi sisa transaksi. Barang layak owned masuk stok toko; rusak tidak menjadi stok layak. Titipan mengikuti pembalikan sumber asal.
- **Refund sesuai hak**: Harga, potongan, pajak dan biaya mengikuti transaksi asal. Refund tidak boleh melebihi hak tersisa; bukti dana dicatat terpisah dari barang.

### Pemetaan
- Lanjut ke: PS-05, PS-08
- Entitas: `returns`, `return_lines`, `credit_notes`, `refunds`, `pos_sales`, `pos_sale_lines`
- UAT PRD: U24, U25, U30

## PS-07 - Tutup shift dan hitung kas
Modul: POS lokal
Tujuan: Pisahkan uang fisik dari pembayaran non-tunai.

### Isi dan aksi
- Aksi: Kembali ke shift; Tutup shift.

### Perilaku dan validasi
- **Perhitungan kas**: Kas diharapkan = kas awal + penjualan tunai - refund tunai + kas masuk - kas keluar - setoran. Non-tunai dilaporkan terpisah.
- **Selisih wajib dijelaskan**: Jika kas aktual berbeda, alasan dan approval mengikuti konfigurasi. Jangan menyesuaikan transaksi penjualan agar kas tampak cocok.
- **Tutup ketika offline**: Ringkasan shift disimpan lokal dan masuk antrean. Status belum diterima cloud tetap ditampilkan; shift tidak boleh dihapus untuk mengatasi kegagalan sync.

### Pemetaan
- Lanjut ke: PS-01, PS-08
- Entitas: `pos_shifts`, `pos_cash_entries`, `pos_tenders`, `sync_outbox`
- UAT PRD: U26, U29

## PS-08 - Status lokal dan antrean sync
Modul: POS lokal
Tujuan: Informasi kasir ketika koneksi terputus atau pulih.

### Isi dan aksi
- Aksi: Periksa koneksi; Coba sinkron lagi.

### Perilaku dan validasi
- **Makna status**: Tersimpan lokal berarti aman di database lokal; Diterima cloud hanya setelah ACK. Keduanya tidak boleh diberi label yang sama.
- **Retry tanpa duplikasi**: Kirim ulang identitas event yang sama. Status Menunggu, Mengirim, Diterima, Coba ulang, dan Perlu tinjauan bisa dibuka per struk.
- **Dua kasir offline**: Saldo antarterminal bisa berbeda. Cloud merekonsiliasi kejadian setelah tersambung; layar tidak menawarkan unggah saldo untuk menimpa toko.

### Pemetaan
- Lanjut ke: PS-02, BO-24
- Entitas: `sync_outbox`, `sync_checkpoints`, `sync_conflicts`, `pos_terminals`
- UAT PRD: U26, U27, U28, U29, U40

## Matriks ketersediaan POS

| Fitur | Online | Offline |
| --- | --- | --- |
| Penjualan tunai / promosi lokal | Ya | Ya, memakai master/policy lokal yang valid |
| Pembayaran elektronik | Sesuai bukti otorisasi | Tidak otomatis terverifikasi; perlu bukti/status valid |
| Diskon khusus, batal, refund | Sesuai hak/approval | Supervisor lokal yang berwenang dan kredensial valid |
| Retur struk terminal sendiri | Ya dengan validasi hak tersisa | Ya jika transaksi lokal tersedia dan memenuhi kebijakan |
| Retur struk terminal lain | Setelah validasi cloud | Ditunda |
| Perolehan poin | Ya | Dicatat untuk sinkronisasi |
| Penukaran poin / voucher kuota bersama | Setelah validasi cloud | Tidak tersedia |
| SO / DP SO / pembelian / gudang / produksi | Di backoffice | Tidak ada di POS |

## Review implementasi
- Validasi stok, satu receive PO, batas refund, idempotensi dan approval wajib atomik pada lapisan transaksi; tidak cukup hanya tombol nonaktif.
- Uji dua kasir offline; retry setelah ACK hilang; restart dengan antrean; periode cloud tertutup; perubahan master saat offline.
- Uji sentuh dan keyboard; contrast, fokus, label dan pesan error dengan pengguna sesungguhnya.
- Basis target UI: Backoffice desktop >=1280 px; POS >=1280x800. Tombol sentuh minimum44x44 CSS px. Skala gambar PDF bukan ukuran komponen implementasi.
- DBML tidak berubah dari v1.0. Model logis bukan DDL produksi atau bukti bahwa semua constraint bisnis dijalankan oleh database.
