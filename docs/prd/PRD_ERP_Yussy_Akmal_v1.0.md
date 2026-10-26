# PRD ERP Bakery Yussy Akmal
Versi 1.0 | 25 Oktober 2026

Kebutuhan produk untuk aplikasi backoffice cloud dan POS lokal

Versi 1.0  •  25 Oktober 2026  •  Bahasa Indonesia

### Tujuan dokumen

Menjadi acuan tunggal bagi pemilik usaha, tim operasional, pengembang, dan penguji untuk membangun ERP satu perusahaan Yussy Akmal. Cakupan peluncuran meliputi seluruh modul yang ditetapkan dalam dokumen ini, dengan POS terpisah pada setiap mesin kasir dan backoffice di cloud.

Dokumen ini menggabungkan DISKUSI 1 ERP, diskusi 2 ERP, DISKUSI 3 ERP, dan keputusan pengguna pada percakapan 25 Oktober 2026. Jika berbeda, keputusan pengguna paling akhir berlaku. Ini adalah spesifikasi kebutuhan dan rancangan, bukan pernyataan bahwa aplikasi sudah selesai atau sudah lulus pengujian.

### Cara membaca

PRD menjelaskan perilaku aplikasi, aturan bisnis, batas modul, dan kriteria penerimaan. Dokumen ERD pendamping memuat hubungan entitas, kamus data inti, serta aturan integritas. File DBML menyediakan model yang dapat diedit pengembang.



| Penanda | Makna |
| --- | --- |
| Keputusan | Ketentuan eksplisit dari pengguna atau dokumen awal yang tidak diganti. |
| Rancangan | Detail implementasi yang diturunkan untuk membuat keputusan dapat dijalankan secara konsisten. |
| Konfigurasi | Nilai operasional yang harus diisi sebelum go live, tanpa perlu mengubah kode. |

### Status dan batas

Kebutuhan bisnis utama telah dikonsolidasikan. Jam jadwal, daftar approver, angka stok minimum, harga, akun keuangan, dan data awal masih harus dikonfigurasi. Tidak ada nilai yang belum diberikan pengguna dianggap sebagai keputusan final.


## 01 Tujuan dan ruang lingkup

Sistem menggantikan alur lama secara menyeluruh untuk satu perusahaan. Pengembangan dapat dilakukan bertahap dan diuji di lingkungan terpisah; peluncuran operasional tetap mencakup seluruh kebutuhan versi pertama.



| Area | Termasuk versi pertama |
| --- | --- |
| Penjualan | POS offline, SO backoffice, paket SO, harga per kanal, diskon, voucher, loyalty, DP, pelunasan, retur dan refund. |
| Rantai pasok | PO sekali penerimaan, faktur dan pembayaran supplier, titipan POS, PO khusus SO, retur supplier. |
| Persediaan | Multi UOM, banyak gudang, reservasi, stok transit, selisih kirim, koreksi stok, opname, scrap. |
| Produksi | BOM berversi, permintaan toko dan minimum stok, SO, WO gabungan, sisa bahan, hasil gagal dan produk turunan. |
| Kontrol | Persetujuan terkonfigurasi, audit, jurnal otomatis, tutup periode, laporan, sinkronisasi per terminal. |

### Di luar versi pertama

Batch/lot dan tanggal kedaluwarsa per batch; FEFO otomatis belum diterapkan. Scrap kedaluwarsa tetap dapat dicatat manual.

Multi perusahaan, payroll, kapitalisasi tenaga kerja per produk, integrasi otomatis marketplace/bank, dan portal supplier tidak menjadi cakupan wajib.

POS tidak membuat atau mengelola SO, PO, penerimaan gudang, transfer, produksi, maupun transaksi pembayaran SO. Semua berada di backoffice.

Paket bertingkat atau paket di dalam paket belum didukung; produksi bertahap memakai SKU premik/WIP yang nyata.

### Hasil yang harus dicapai

Transaksi dapat ditelusuri dari dokumen sumber ke mutasi stok dan jurnal. Penjualan tetap berjalan saat internet terputus, sinkronisasi tidak menggandakan transaksi, selisih transit terlihat sampai selesai, dan hasil samping tidak menggandakan biaya produksi.


## 02 Acuan keputusan dan perubahan



| Topik | Ketentuan yang berlaku |
| --- | --- |
| Cakupan | Seluruh sistem Yussy Akmal dalam satu perusahaan. |
| Penerimaan PO | Satu penerimaan final, boleh kurang dari pesanan. Sisa ditutup; kedatangan berikutnya ditolak dan dikembalikan ke supplier. |
| Transfer | Dispatch mengurangi sumber dan menambah transit. Penerimaan menambah tujuan sesuai aktual; sisa tetap transit. |
| Titipan | POS: fisik di kartu manual, pengakuan masuk dan terjual bersamaan. SO: PO khusus per SO, penerimaan di packing. |
| SO batal | Barang supplier yang sudah diterima dialihkan dari packing ke toko untuk dijual sebagai stok milik perusahaan. |
| Paket | SO satu paket satu harga; POS setiap produk dan kemasan memiliki harga sendiri. |
| Produksi | Bahan otomatis sesuai BOM; hasil aktual, sisa layak, produk gagal, dan turunan dicatat saat selesai. |
| Putih telur | Biaya masuk nol; seluruh biaya telur tetap pada produk utama. Harga jual putih telur tersendiri. |
| Jadwal | Batas H-1 dan jam kirim melalui tabel, tidak hardcode. Tambahan setelah WO perlu persetujuan produksi. |
| Akses | Hak tindakan berdasarkan peran/persetujuan; tidak ada pembatasan akses staf berdasarkan toko/dapur. |
| POS lokal | Setiap mesin memiliki instalasi dan database lokal; sinkronisasi ke backoffice cloud. |
| SO dan pembayaran | Seluruh transaksi SO, termasuk DP, pelunasan, pembatalan dan refund, melalui backoffice. |

Rancangan ini menggantikan transfer instan, penundaan modul retur/DP, dan asumsi paket POS tidak didukung dalam dokumen lama. Struktur SQL lama tidak boleh langsung dijalankan tanpa konsolidasi dan migrasi.


## 03 Organisasi dan master data

Struktur awal adalah 6 toko fisik dan 1 outlet virtual Dahlia, 10 dapur produksi dan 1 bagian packing. Terdapat 28 gudang operasional: CDC, packing, 20 gudang RAW/FIN dapur, serta 6 gudang toko. Transit ditambahkan sebagai lokasi virtual sehingga jumlah 28 bukan batas total lokasi sistem.

### Master yang wajib dapat dikelola

Produk/SKU, kategori, satuan, konversi per SKU, supplier, pelanggan, outlet, dapur, gudang, terminal POS, metode pembayaran dan rekening.

Harga per kanal/price list, diskon, voucher, loyalty, pajak terkonfigurasi, BOM dan komponen, jadwal, kebijakan stok minimum/target, pengguna, peran serta matriks persetujuan.

SKU mempunyai penanda dapat dibeli, dijual, diproduksi, jenis intermediate premik/WIP, serta jenis paket. Kebijakan titipan dibedakan berdasarkan sumber stok, bukan hanya penanda global SKU.

### Aturan satuan dan perubahan master

Setiap SKU memiliki satu satuan dasar. Contoh pembelian dus dapat dikonversi menjadi gram; faktor berlaku per SKU. Kuantitas input, satuan input, faktor konversi saat transaksi, dan kuantitas dasar disimpan sebagai snapshot. Perubahan konversi tidak menghitung ulang transaksi lama.

Satuan dasar produk yang sudah bertransaksi tidak boleh diganti langsung. Gunakan SKU baru atau migrasi terkendali. Barcode SKU/satuan aktif harus tidak ambigu. Produk atau BOM yang sudah dipakai dinonaktifkan atau dibuat versi baru, bukan dihapus dari riwayat.

### Aturan CRUD

Master mendukung tambah, lihat, ubah, dan nonaktifkan. Penghapusan fisik hanya untuk data yang belum direferensikan. Draft transaksi boleh diubah/dihapus sesuai hak akses. Dokumen posted, mutasi stok, dan jurnal dikoreksi melalui reversal atau dokumen koreksi yang tertaut.


## 04 Hak akses dan persetujuan

Akses lokasi tidak dibatasi untuk staf. Namun hak melihat biaya, mengubah harga, memposting dokumen, memberi diskon, menyetujui tindakan, serta membuka periode tetap dibedakan berdasarkan peran. Lokasi terminal menentukan sumber stok transaksi POS, bukan batas akses pengguna backoffice.



| Objek pengaturan | Isi minimal |
| --- | --- |
| Peran dan hak | Pengguna dapat memiliki beberapa peran; hak tindakan ditetapkan eksplisit. |
| Aturan persetujuan | Jenis tindakan, rentang nilai/kuantitas, langkah persetujuan, pengguna/peran penyetuju, masa berlaku, dan izin offline. |
| Permintaan | Dokumen dan revisi yang diminta, pengaju, alasan, nilai transaksi, status, dan snapshot aturan. |
| Keputusan | Penyetuju, waktu, setuju/tolak, catatan, metode otorisasi, terminal jika offline. |

### Tindakan yang harus didukung

Persetujuan mencakup PO, koreksi stok, scrap/selisih transit, diskon khusus, pembatalan, refund, pesanan tambahan setelah WO, dan buka kembali periode. Angka ambang dan daftar penyetuju diisi oleh perusahaan; Rp500.000 pada dokumen lama bukan ambang final.

### Perilaku persetujuan

Dokumen tidak boleh diposting sebelum langkah wajib selesai. Perubahan nilai atau isi material membatalkan persetujuan lama dan membuat revisi baru. Rancangan awal melarang pengaju menyetujui permintaannya sendiri; pengecualian hanya melalui aturan eksplisit yang diaudit.

Supervisor offline memakai kredensial lokal yang telah disinkronkan. PIN disimpan sebagai hash, ada pembatasan percobaan, dan otorisasi terikat transaksi tertentu. Kebijakan kedaluwarsa kredensial/aturan offline dikonfigurasi. Jika tidak ada otorisasi offline yang valid, tindakan khusus ditunda; penjualan biasa tetap dapat berjalan.


## 05 Arsitektur dua aplikasi

Backoffice cloud menjadi pusat master, dokumen operasional, konsolidasi stok, dan jurnal perusahaan. Setiap mesin POS menjalankan aplikasi serta database lokal sendiri dalam Docker. Volume persisten menyimpan transaksi dan antrean sinkronisasi melampaui umur container.



| Data atau proses | Pemilik utama | Salinan POS |
| --- | --- | --- |
| Master dan kebijakan | Backoffice | Cache berversi untuk penjualan offline. |
| SO dan seluruh pembayarannya | Backoffice | Tidak dibuat atau diproses POS. |
| Penjualan POS dan shift | Terminal pembuat | Disimpan lokal dahulu, diterima sekali di cloud. |
| Stok resmi dan valuasi | Backoffice | Snapshot + mutasi lokal yang belum terakui. |
| Persetujuan offline | Terminal dengan policy cache | Dikirim bersama bukti dan versi kebijakan. |
| Jurnal keuangan perusahaan | Backoffice | Tidak diposting ulang secara independen di kasir. |

### Dua kasir dalam satu toko

Terminal A dan B memiliki UUID, urutan lokal, shift, database, dan antrean masing-masing. Keduanya memakai gudang toko yang sama di cloud. Nomor struk memuat identitas terminal agar unik. Keduanya mengirim kejadian transaksi, bukan menimpa saldo stok cloud.

Saat offline, tampilan stok antarkasir dapat berbeda dan penjualan POS tetap boleh minus. Backoffice menghitung hasil gabungan setelah sinkronisasi. Tampilan POS wajib menunjukkan waktu sinkronisasi terakhir dan jumlah transaksi yang belum diterima.

### Rancangan teknologi

Database cloud menggunakan PostgreSQL sebagai kelanjutan rancangan sumber. PostgreSQL lokal per terminal merupakan rancangan awal untuk memudahkan konsistensi transaksi dan Docker. Bahasa backend/frontend belum diputuskan pengguna; pilihan framework tidak mengubah kontrak bisnis atau ERD.


## 06 Penjualan dan operasional POS

POS hanya menjual barang toko. Kasir membuka shift, memilih/scan produk, melihat harga, memberi diskon sesuai wewenang, menerima pembayaran, dan mencetak struk. Snack box POS menjadi baris produk dan kemasan terpisah; tidak menggunakan harga paket SO.

### Perhitungan dan pembayaran

Urutan perhitungan mengikuti rancangan awal: harga price list/satuan, diskon item, diskon global, voucher, penukaran loyalty, lalu pajak sesuai konfigurasi. Potongan dialokasikan ke baris secara deterministik agar retur sebagian dapat dihitung. Simpan snapshot harga, tarif pajak, faktor satuan, dan versi kebijakan.

Pembayaran mendukung tunai, transfer, QRIS, dan kartu dengan referensi serta status verifikasi. Offline berarti aplikasi dapat mencatat penjualan; aplikasi tidak boleh menyatakan pembayaran elektronik telah disahkan penyedia tanpa bukti yang valid. Split tender dapat dicatat sebagai beberapa baris pembayaran, dan kembalian hanya berasal dari tender tunai.

### Aturan stok dan promosi offline

POS dapat melanjutkan ketika stok tidak cukup, dengan alasan dan penanda anomali. Untuk mencegah pemakaian voucher/loyalty ganda antarterminal, rancangan versi pertama mengizinkan perolehan poin offline tetapi penukaran saldo bersama/voucher berkuota memerlukan koneksi. Promosi lokal yang tidak memakai saldo bersama dapat berjalan dari policy cache.

### Shift dan koreksi

Satu terminal hanya memiliki satu shift aktif. Tutup shift mencatat kas awal, penjualan tunai, refund tunai, kas masuk/keluar beralasan, setoran, kas aktual, dan selisih; pembayaran non-tunai tidak dimasukkan ke kas fisik. Struk yang dicetak ulang diberi penanda salinan.

Retur/refund POS merujuk transaksi asal dan tidak menghapus penjualan. Saat offline, koreksi hanya untuk transaksi lokal yang tersedia dan belum dikembalikan seluruhnya. Retur transaksi dari terminal lain memerlukan validasi cloud untuk menghindari refund ganda.


## 07 Sinkronisasi dan ketahanan offline

### Kontrak pengiriman kejadian

Penjualan, pembayaran, mutasi lokal, dan outbox event ditulis dalam satu transaksi database lokal. Event memuat event_id UUID, terminal_id, local_sequence, aggregate_id, event_type, schema_version, occurred_at, payload_hash, versi master/kebijakan, dan payload snapshot.

Cloud menyimpan event_id unik serta pasangan terminal_id dan local_sequence unik. Payload yang sama dikirim ulang menghasilkan acknowledgement yang sama; identitas sama dengan payload berbeda menjadi konflik. Penyimpanan inbox, dokumen, mutasi stok, jurnal, dan status applied dilakukan atomik. ACK hanya diberikan setelah commit berhasil.

### Koneksi terputus dan pemulihan

Retry otomatis dengan jeda bertambah; event tidak dihapus sebelum cloud mengakui. Status tersedia: pending, sending, applied, retry, conflict.

Retur menunggu penjualan asal diterima. Urutan lokal dipertahankan, dan dependensi lintas dokumen divalidasi.

Master dikirim menggunakan cursor/revisi dan tombstone nonaktif; checkpoint baru disimpan sesudah perubahan lokal selesai.

Saldo POS dihitung dari snapshot cloud ditambah mutasi lokal yang belum termasuk snapshot. ACK dan watermark mencegah mutasi dihitung dua kali.

Konflik master, pajak, periode tutup, atau kebijakan tidak boleh menyebabkan penjualan hilang. Event masuk antrean pengecualian untuk tindakan backoffice.

### Waktu dan periode

Semua waktu disimpan dengan zona waktu dan ditampilkan WIB. Waktu transaksi asli dan waktu diterima server disimpan terpisah. Periode terbuka memakai tanggal bisnis yang valid; transaksi terlambat dari periode tertutup tidak mengubah jurnal lama diam-diam, melainkan memerlukan posting koreksi terotorisasi pada periode terbuka.

Costing cloud memakai urutan posting yang deterministik per SKU/lokasi. HPP provisional saat stok minus ditandai dan disesuaikan melalui entri koreksi; angka historis tidak ditimpa. Rekonsiliasi harian membandingkan jumlah struk, nilai pembayaran, event dan dokumen applied per terminal.


## 08 Pembelian dan penerimaan supplier

Alur wajib: PO draft, persetujuan jika diperlukan, confirmed, satu goods receipt final, faktur supplier, lalu pembayaran. PO reguler menerima ke lokasi yang diizinkan; PO pemenuhan SO wajib terhubung ke satu SO dan menerima di packing.

### Satu penerimaan final

Penerimaan mencakup semua baris PO, termasuk baris diterima nol dengan alasan. Jumlah boleh kurang dari pesanan, tetapi tidak boleh lebih. Minimal satu baris diterima positif; jika seluruhnya nol, batalkan/tolak kedatangan tanpa memposting penerimaan. Kuantitas dan nilai PO asli tetap tersimpan; jumlah aktual dicatat terpisah.

Contoh: pesan 10 dus, diterima 5 dus. Sistem menerima 5, menutup kekurangan 5, dan menandai PO selesai diterima. Kedatangan berikutnya untuk sisa PO tersebut ditolak dan dikembalikan kepada supplier, tanpa menambah stok atau utang. Bukti penolakan/kedatangan disimpan sebagai catatan audit.

### Faktur dan pembayaran

Faktur merujuk penerimaan; pemeriksaan kumulatif mencegah kuantitas ditagih melebihi penerimaan bersih. Beberapa faktur boleh merujuk satu penerimaan selama batas tersebut dijaga. Selisih harga memerlukan review sesuai konfigurasi dan diposting sebagai selisih harga yang tertelusur, bukan mengubah mutasi lama.

Pembayaran dapat sebagian atau melunasi beberapa faktur dari supplier yang sama. Jumlah alokasi tidak boleh melampaui pembayaran atau saldo kewajiban. Belanja jasa yang tidak menjadi stok dicatat sebagai beban di backoffice.

### Retur supplier

Retur merujuk penerimaan asal, mengurangi stok yang tersedia, dan menghasilkan klaim/kredit supplier. Retur tidak membuka kembali PO untuk penerimaan kedua. Penyelesaian kredit terhadap utang atau pengembalian dana supplier dicatat terpisah dan saling tertaut.


## 09 Barang titipan dan pembelian khusus SO



| Aspek | Titipan dijual POS | Barang supplier untuk SO |
| --- | --- | --- |
| Penerimaan fisik | Kartu manual di toko. | PO khusus satu SO; diterima ke packing. |
| Pengakuan stok | Saat penjualan: masuk dan keluar berpasangan. | Saat goods receipt diposting. |
| Kewajiban supplier | Terbentuk berdasarkan kuantitas terjual dan harga supplier saat penjualan. | Mengikuti penerimaan dan faktur PO. |
| Produksi | Tidak membuat WO. | Tidak membuat WO untuk komponen yang dibeli. |
| Jika SO batal | Tidak berlaku. | Lepas reservasi; transfer ke toko sebagai stok milik perusahaan. |

### Titipan POS

Perjanjian supplier menyimpan SKU, lokasi toko, harga supplier, periode berlaku dan aturan settlement. Snapshot harga supplier mengikuti penjualan, termasuk saat offline. Jika perjanjian/harga belum tersedia lokal, item titipan tidak boleh dijual sebelum master lengkap.

Satu penjualan titipan menghasilkan pengakuan masuk, keluar, HPP, dan kewajiban supplier secara atomik. Kuantitas fisik yang belum terjual tidak masuk saldo stok perusahaan. Settlement diturunkan dari penjualan bersih setelah retur dan tidak ditagih lagi melalui penerimaan biasa.

### Pemisahan kepemilikan pada SKU yang sama

SKU dapat memiliki stok milik perusahaan dan alur titipan pada toko yang sama. Baris POS wajib menyimpan sumber owned atau consignment. Rancangan UI meminta pilihan eksplisit bila keduanya tersedia; tidak boleh menebak berdasarkan stok minus.

Barang supplier yang dialihkan dari SO batal sudah diakui saat penerimaan. Saat dijual POS sebagai owned, sistem hanya mengurangi stok dan mengakui penjualan/HPP; tidak boleh menciptakan penerimaan titipan atau utang supplier kedua.

### Retur titipan

Retur layak yang kembali ke kartu manual membalik pengakuan masuk/keluar terkait dan mengurangi kewajiban supplier. Jika supplier sudah dibayar, terbentuk kredit/klaim yang dapat diselesaikan. Barang rusak dipisahkan sebagai kasus klaim atau kerugian terotorisasi; tidak otomatis dianggap dapat dijual lagi.


## 10 Sales Order dan paket

Semua SO dibuat dan diproses di backoffice. Outlet asal menjadi atribusi penjualan; Dahlia tidak memiliki POS atau gudang sendiri. Pemenuhan SO dilakukan dari packing sesuai alokasi, termasuk barang yang diproduksi maupun dibeli dari supplier.

### Paket dan snapshot komponen

SO menjual paket sebagai satu SKU dengan satu harga. Paket tidak mempunyai saldo stok sendiri. Komponen produk dan kemasan disalin ke snapshot saat konfirmasi; pemenuhan dan HPP mengikuti komponen, sedangkan faktur pelanggan tetap menampilkan paket. Perubahan BOM paket setelah konfirmasi tidak mengubah pesanan lama.

Komponen paket dapat berupa produk dapur, barang supplier, dan kemasan. Kebutuhan setiap komponen ditandai sumber stok, produksi, atau pembelian. Komponen yang dibeli tidak dimasukkan ke WO. Paket bertingkat ditolak. Penjualan komponen satuan dan paket tidak boleh menghitung kebutuhan komponen dua kali.

### Tanggal dan perubahan

Tanggal kirim SO harus setelah tanggal pesan. Satu SO memiliki satu jadwal; kebutuhan dua jadwal dipisah menjadi dua SO. Jam cutoff H-1 dan jam kirim berasal dari versi jadwal aktif dan disimpan pada pesanan. Jadwal tanpa jam lengkap tidak dapat digunakan untuk konfirmasi.

Setelah WO dibuat, penambahan atau perubahan yang berdampak pada produksi membutuhkan persetujuan penanggung jawab produksi. Sistem membuat revisi kebutuhan dan WO tambahan/revisi untuk selisihnya, bukan menjalankan ulang seluruh kebutuhan. Pesanan yang sudah diproduksi/dikirim tidak boleh berkurang diam-diam.

### Pengiriman dan pembayaran

Delivery boleh sebagian selama tercatat per baris/komponen, tidak melebihi kebutuhan tersisa, dan tersedia stok/reservasi yang sah. DP, pelunasan, invoice, pembatalan, dan refund SO seluruhnya berada di backoffice. DP tidak otomatis menjadi pendapatan sebelum penjualan terkait diakui.


## 11 Perencanaan kebutuhan dan produksi

Kebutuhan berasal dari SO pelanggan, permintaan toko, dan usulan berdasarkan minimum stok. MTS mengisi persediaan premik/WIP/produk toko; MTO memenuhi pesanan. Semua sumber dicatat sebagai demand agar dapat ditelusuri, direvisi, dan dialokasikan tanpa duplikasi.

### Minimum stok dan permintaan toko

Kebijakan per SKU/toko memuat minimum, target, kelipatan pemesanan, dan sumber pemenuhan. Jika posisi persediaan bersih di bawah minimum, sistem mengusulkan jumlah menuju target. Perhitungan mempertimbangkan stok tersedia, reservasi, kiriman transit, serta permintaan/replenishment yang sudah terbuka. Permintaan toko yang sudah tercakup tidak ditambahkan kembali.

Usulan menjadi draft untuk diperiksa admin produksi. Rancangan awal tidak otomatis memposting pembelian atau produksi. Setelah disetujui, demand dipenuhi dari stok packing, produksi, atau pembelian sesuai kebijakan SKU.

### BOM dan WO gabungan

BOM berversi menentukan hasil standar, bahan, satuan, kuantitas, dapur, serta produk turunan yang diharapkan. WO menyimpan versi dan snapshot bahan; versi aktif yang berganti tidak mengubah WO berjalan. Premik dan WIP diproduksi sebagai SKU sendiri lalu dikonsumsi oleh tahap berikutnya.

WO digabung untuk SKU, dapur, versi BOM, tanggal, dan jadwal yang kompatibel. Tabel alokasi menyimpan kuantitas setiap demand yang dipenuhi WO. Satu SKU memiliki dapur default; produksi di dapur lain harus memakai pemetaan yang sah. Perintah tambahan setelah persetujuan memiliki revisi dan hubungan ke WO semula.

### Kekurangan hasil

Jika hasil kurang, kebutuhan belum terpenuhi tetap terbuka dan dapat dibuat WO tambahan terotorisasi. Prioritas alokasi mengikuti waktu kirim dan prioritas pesanan yang dikonfigurasi. Produk berlebih menjadi stok tersedia setelah alokasi pesanan terpenuhi.


## 12 Eksekusi produksi dan biaya hasil

### Mulai produksi

Saat WO dimulai, bahan otomatis dikeluarkan sesuai snapshot resep dan skala produksi. Pengeluaran strict non-minus dan mempertimbangkan reservasi. Bahan berasal dari gudang bahan atau lokasi WIP yang dipetakan pada baris BOM; jangan menganggap semua komponen selalu berada di RAW.

Nilai bahan dipindahkan ke pekerjaan dalam proses agar biaya tidak hilang selama WO belum selesai. Pemakaian tambahan di luar BOM tidak otomatis diizinkan; membutuhkan revisi/koreksi terotorisasi dan jejak audit.

### Selesai produksi

Petugas mencatat hasil utama aktual, bahan layak yang dikembalikan, produk gagal, dan produk turunan. Pengembalian bahan merujuk pengeluaran asal, tidak melebihi yang dikeluarkan, dan memakai biaya asal. Produk turunan dicatat dengan SKU, satuan, jumlah aktual, serta tujuan gudang.

Putih telur dari 100 telur masuk dengan biaya nol. Seluruh biaya telur tetap dibebankan ke produk utama. Harga jual putih telur dapat diatur terpisah. Tidak ada pengalokasian biaya kepada produk turunan pada kebijakan versi pertama ini.

### Rumus dan kasus khusus

Biaya material bersih = nilai bahan dikeluarkan dikurangi nilai bahan layak dikembalikan. Rancangan biaya kegagalan normal: biaya material bersih dibebankan pada hasil utama layak; biaya per unit = biaya material bersih dibagi hasil utama layak. Produk gagal dicatat sebagai jumlah gagal, tidak menjadi stok jual atau biaya kedua.

Jika seluruh hasil utama gagal, WO ditutup melalui approval dengan biaya bersih diposting sebagai kerugian produksi; pembagian dengan nol dilarang. Tenaga kerja dan overhead tetap beban periode sebagaimana rancangan awal. Hasil utama parsial sebelum complete tidak diposting sebagai output final pada versi pertama.

### Perpindahan hasil

Hasil berada di gudang FIN dapur. Transfer ke packing dan reservasi SO dilakukan sebagai proses tersendiri. Transfer bukan pendapatan, dan reservasi bukan perpindahan fisik.


## 13 Transfer transit dan selisih

Transfer memiliki dua tindakan terpisah: kirim dan terima. Saat dispatch, sumber berkurang dan lokasi transit bertambah dengan biaya yang sama. Saat diterima, transit berkurang dan tujuan bertambah sesuai jumlah aktual. Beberapa penerimaan boleh menyelesaikan satu pengiriman; aturan sekali receive hanya berlaku untuk PO supplier.

### Contoh 100 dikirim dan 98 diterima

Toko bertambah 98. Dua unit tetap di transit dan memiliki kasus selisih terbuka. Dokumen tidak boleh ditutup sebagai diterima penuh sebelum dua unit tersebut mempunyai penyelesaian yang tercatat.



| Hasil pemeriksaan | Penyelesaian |
| --- | --- |
| Masih dalam perjalanan | Tetap transit; catat penanggung jawab dan tindak lanjut. |
| Diterima kemudian | Penerimaan tambahan memindahkan transit ke tujuan. |
| Kembali ke packing | Konfirmasi kedatangan kembali, pindahkan transit ke packing. |
| Rusak atau hilang | Approval; keluarkan dari transit dan catat kerugian sesuai alasan. |
| Salah jumlah kirim | Koreksi tertaut dengan bukti hitung; kembalikan saldo ke sumber bila barang memang tidak pernah berangkat. |

### Routing dan kontrol

Premik kembali ke CDC lalu ke dapur; WIP boleh langsung antardapur; produk final dari dapur ke packing lalu toko. Antar toko dan toko ke packing didukung sesuai aturan. Rute pengembalian/koreksi yang sah harus tersedia meskipun rute operasional normal searah.

Pengiriman tidak boleh mengambil stok yang dipesan pihak lain. Barang yang dialokasikan untuk permintaan toko membawa identitas alokasinya sampai diterima. Jumlah diterima tidak melebihi sisa transit; kelebihan fisik menjadi kasus selisih untuk ditelusuri, bukan penerimaan otomatis.

Transit virtual tetap bagian dari nilai persediaan perusahaan. Laporan menampilkan umur kiriman dan selisih belum selesai. Transfer memakai tanggal efektif yang diaudit dan tidak boleh mengubah snapshot periode tertutup tanpa koreksi terkontrol.


## 14 Persediaan reservasi dan valuasi

Seluruh saldo stok menggunakan satuan dasar. Ledger mutasi bersifat append-only; saldo cepat adalah hasil agregasi yang dapat direkonsiliasi. Setiap mutasi mengacu dokumen/baris sumber, lokasi, jumlah bertanda, biaya, waktu efektif dan waktu posting.

### Reservasi dan kondisi barang

Reservasi mengikat SKU, gudang, dan demand tertentu. Stok tersedia = stok layak dikurangi reservasi aktif. POS dapat melewati ketersediaan dengan penanda anomali, tetapi gudang, produksi, delivery, retur supplier, dan scrap tidak boleh minus.

Jika barang yang direservasi ternyata rusak, sistem melepaskan atau mengalihkan reservasi melalui penanganan pengecualian lalu mencatat scrap. Jangan memaksa pengiriman barang rusak atau membatalkan seluruh SO hanya untuk memperbaiki stok.

### Rata rata tertimbang bergerak

Untuk stok non-negatif, nilai persediaan baru berasal dari nilai saldo lama ditambah nilai penerimaan; biaya rata-rata = nilai baru dibagi jumlah baru. Pengeluaran memakai biaya rata-rata saat posting; transfer membawa biaya sumber. Nilai uang/kuantitas menggunakan decimal, bukan floating point.

Saat POS membuat stok minus, jangan memakai rumus rata-rata biasa dengan penyebut nol/negatif. Simpan kekurangan dan HPP provisional; penerimaan berikutnya menutup kekurangan dan menghasilkan penyesuaian HPP tertaut bila biaya berbeda. Mekanisme ini harus diuji pada stok nol, minus, dan penerimaan bertahap.

Penerimaan produk turunan berbiaya nol menambah kuantitas tanpa nilai. Jika SKU yang sama juga dibeli dengan biaya positif, rata-rata mengikuti gabungan nilai/kuantitas yang sah. Biaya nol hanya untuk penerimaan hasil turunan, bukan perintah menimpa seluruh nilai SKU menjadi nol.

### Opname dan koreksi

Opname mencatat waktu hitung, saldo acuan dan mutasi setelah hitung sebelum menentukan koreksi. Selisih tidak boleh menimpa transaksi yang berlangsung saat penghitungan. Pengurangan memerlukan stok tersedia atau penyelesaian reservasi; koreksi besar mengikuti matriks approval.


## 15 Pembatalan retur dan refund



| Kasus | Perubahan stok | Penyelesaian nilai |
| --- | --- | --- |
| POS batal sebelum checkout | Tidak ada mutasi posted. | Draft dibatalkan. |
| POS retur barang owned layak | Masuk kembali ke toko dengan biaya transaksi asal. | Credit/refund sesuai jumlah yang dikembalikan. |
| POS retur barang rusak | Tidak masuk stok layak; catat disposisi kerugian. | Refund dan kerugian tertaut, tanpa penggandaan HPP. |
| Titipan POS retur | Balik pasangan pengakuan terkait; fisik kembali kartu manual jika layak. | Kurangi kewajiban atau buat klaim supplier. |
| SO batal sebelum pemenuhan | Lepas reservasi; batalkan/revisi demand, WO dan PO yang masih dapat dibatalkan. | DP dikembalikan sesuai persetujuan; bukan otomatis hilang. |
| SO batal setelah barang supplier diterima | Transfer packing ke toko sebagai stok owned. | Utang supplier tetap tercatat; tidak dibatalkan karena SO batal. |
| SO setelah delivery | Retur penjualan, bukan hapus SO. | Credit note dan refund/kompensasi piutang di backoffice. |
| Retur supplier | Keluar dari stok tersedia; referensi penerimaan asal. | Supplier credit mengurangi utang atau menjadi klaim pengembalian dana. |

### Batas dan bukti

Jumlah kumulatif retur tidak boleh melebihi jumlah transaksi asal dikurangi retur sebelumnya. Refund tidak boleh melebihi hak pengembalian yang tersisa setelah pembayaran/kompensasi sebelumnya. Sistem menyimpan alasan, kondisi barang, bukti, penyetuju, dan hubungan dokumen asal.

Refund adalah aliran uang; retur adalah aliran barang. Keduanya dapat terjadi pada waktu berbeda tetapi harus saling tertaut. Refund tanpa barang kembali memerlukan alasan serta persetujuan yang sesuai. Pembatalan produksi berjalan tidak otomatis mengembalikan bahan yang sudah dipakai.


## 16 Keuangan dan tutup periode

Backoffice membentuk jurnal berpasangan dari kejadian bisnis. Jurnal wajib seimbang, dokumen posted tidak dihapus, dan koreksi memakai reversal. Pemetaan akun serta pajak merupakan konfigurasi perusahaan, bukan tarif/kebijakan hukum yang ditentukan dokumen ini.



| Kejadian | Pola pembukuan yang dirancang |
| --- | --- |
| Penerimaan barang | Persediaan bertambah; kewajiban penerimaan belum ditagih terbentuk. |
| Faktur supplier | Kewajiban sementara direklasifikasi ke utang faktur; selisih harga/pajak dicatat terpisah. |
| Produksi | Bahan ke pekerjaan dalam proses, kemudian ke produk utama; pengembalian bahan membalik biaya asal. |
| Penjualan dan delivery | Pendapatan/pajak serta pembayaran atau piutang; HPP dan pengurangan persediaan tidak boleh terposting dua kali. |
| DP pelanggan | Kas/bank bertambah dan kewajiban uang muka bertambah. Alokasi ke invoice mengurangi uang muka dan piutang. |
| Titipan terjual | Pengakuan masuk/keluar dan kewajiban supplier berdasarkan harga beli snapshot. |
| Refund dan retur | Credit note, pengembalian dana, persediaan layak/kerugian sesuai dokumen asal. |
| Transfer internal | Perpindahan lokasi dengan nilai dibawa; tidak menciptakan penjualan. |

### DP dan alokasi pembayaran

DP terikat SO dan pelanggan. Saldo DP tersedia = penerimaan dikurangi alokasi ke invoice dan refund. Alokasi tidak boleh melebihi saldo DP atau piutang. Pemindahan ke SO lain tidak otomatis; gunakan tindakan terotorisasi yang tertelusur. Pembayaran biasa dan uang muka tidak dihitung sebagai dua kas masuk.

### Penutupan periode

Pre-close memeriksa jurnal seimbang, dokumen belum posted, penerimaan belum ditagih, saldo DP, selisih transit, stok minus, dan terminal belum sinkron. Pengecualian harus diselesaikan atau dicatat dan diotorisasi sebelum penutupan. Snapshot saldo dibuat atomik; posting ke periode tertutup ditolak.

Buka kembali periode memerlukan approval dan pemeriksaan periode sesudahnya. Rancangan awal tidak membuka periode lama jika sudah ada periode setelahnya yang ditutup. Laporan menggunakan hanya jurnal sah dan rentang tanggal yang benar; saldo awal dan laba berjalan dipertimbangkan.


## 17 Layar laporan dan pengalaman pengguna

### Navigasi backoffice

Menu utama: dashboard; master; penjualan SO; pembelian; gudang dan transit; produksi; persetujuan; keuangan; laporan; sinkronisasi; pengaturan. Setiap dokumen memiliki daftar, pencarian/filter, detail, riwayat status, lampiran, dan tautan ke dokumen terkait.

### Laporan wajib



| Kelompok | Laporan minimal |
| --- | --- |
| Penjualan | Per tanggal bisnis, toko, terminal, kasir, kanal, SKU, paket, diskon dan metode pembayaran; retur ditampilkan terpisah dan bersih. |
| Persediaan | Kartu stok, tersedia/reservasi, transit, selisih terbuka, valuasi, scrap, opname, stok minus dan HPP provisional. |
| Produksi | Kebutuhan vs WO, pemenuhan SO/toko, bahan standar vs bersih, hasil aktual, gagal, turunan biaya nol, sisa bahan. |
| Pembelian | PO vs aktual diterima, kekurangan ditutup, kedatangan ditolak, penerimaan belum ditagih, kinerja supplier. |
| Keuangan | Buku besar, neraca saldo, laba rugi, neraca, kas/bank, umur utang/piutang, saldo DP, refund dan settlement titipan. |
| Kontrol | Status per terminal, backlog/conflict sinkronisasi, approval tertunda, audit perubahan, kesiapan tutup periode. |

### Ketepatan tampilan

Setiap angka dapat ditelusuri ke dokumen sumber. Penjualan paket tidak dijumlahkan lagi sebagai omzet komponen. Laporan tidak menjumlahkan gram, pcs dan ml sebagai satu total kuantitas. Harga, pajak, potongan dan biaya menggunakan snapshot transaksi.

POS menampilkan status online/offline, waktu sinkronisasi, antrean, stok yang mungkin belum terkini, serta hasil cetak yang jelas. Layar backoffice menampilkan tindakan yang tersedia berdasarkan status dokumen dan hak pengguna; kesalahan validasi menyebut penyebab dan langkah penyelesaian.


## 18 Kualitas sistem dan operasional

Target di bawah adalah rancangan penerimaan teknis awal. Beban produksi sesungguhnya perlu diukur melalui uji beban sebelum go live; angka ini bukan klaim performa aplikasi yang sudah ada.



| Aspek | Kriteria atau rancangan target |
| --- | --- |
| Respons POS lokal | Tambah item dan pencarian umum p95 di bawah 1 detik pada perangkat uji yang disepakati. |
| Checkout lokal | Commit transaksi p95 di bawah 2 detik, tidak termasuk otorisasi penyedia pembayaran/cetak. |
| Offline | Uji 72 jam terputus dan setidaknya 10.000 transaksi antrean per terminal tanpa kehilangan data. |
| Sinkronisasi | Uji kirim ulang, urutan terputus, proses mati, dua kasir dan koneksi putus saat ACK; efek bisnis tepat sekali. |
| Keamanan | TLS, password/PIN hash, role permissions, audit, enkripsi/akses terbatas untuk backup; tidak menyimpan PIN polos. |
| Backup | Backup database cloud harian dan log kontinu; backup POS lokal ke media berbeda sesuai kebijakan. Uji restore wajib. |
| Pemulihan | Target awal cloud RPO 15 menit dan RTO 4 jam; validasi melalui latihan pemulihan. |
| Monitoring | Alert backlog/conflict sync, ruang disk, backup gagal, jurnal tidak seimbang, stok minus, serta transit menua. |

### Docker dan inisialisasi

Pada instalasi baru, proses bootstrap membuat database, menjalankan migrasi tabel, dan seed minimum secara idempotent. Restart tidak menghapus atau mengisi ulang data transaksi. Cloud dan setiap terminal memakai persistent volume; kredensial tidak ditanam dalam image. Akun admin pertama dibuat melalui proses setup dengan sandi baru.

Rancangan deployment menyertakan pemeriksaan kesehatan, migrasi terkontrol satu proses, kompatibilitas versi sync, backup sebelum upgrade, dan prosedur rollback. Salinan POS menyimpan hanya data yang diperlukan operasional kasir meskipun akses pengguna backoffice tidak dibatasi per lokasi.


## 19 Migrasi dan peluncuran

Peluncuran mengganti seluruh sistem. Tahapan implementasi berikut mengatur pekerjaan pengembang dan pengujian, bukan menunda fitur yang telah ditetapkan masuk versi pertama.



| Tahap | Hasil dan gerbang |
| --- | --- |
| Fondasi | Schema konsolidasi, master, akses, approval, ledger, migrasi Docker; uji unit/integritas lulus. |
| Operasional | Pembelian, transit, SO, produksi, titipan, DP dan retur terhubung end-to-end. |
| POS dan sync | Dua terminal, offline, snapshot harga, pembayaran, shift, refund dan rekonsiliasi lulus. |
| Keuangan dan UAT | Jurnal, laporan, tutup periode; skenario penerimaan disetujui pemilik proses. |
| Cutover | Backup, freeze transaksi lama pada waktu yang ditentukan, impor saldo/data terbuka, rekonsiliasi, aktivasi seluruh modul. |

### Data migrasi

Master SKU/UOM/konversi, BOM, harga, supplier, pelanggan, organisasi, jadwal, pengguna dan approver.

Stok awal per lokasi beserta nilainya, transit yang masih berjalan, reservasi, SO/PO terbuka, WO berjalan dan biaya WIP.

Saldo kas/bank, akun, utang/piutang, DP pelanggan, kewajiban titipan, kredit/refund belum selesai.

Pemisahan saldo stok milik perusahaan dan barang fisik titipan pada kartu manual. Jangan mengimpor titipan belum terjual sebagai persediaan perusahaan.

### Gerbang go live

Tidak ada saldo pembuka tanpa sumber dan persetujuan. Jumlah/nilai stok serta saldo buku besar direkonsiliasi; transaksi terbuka memiliki pemetaan identitas. Setiap terminal harus registrasi, menerima master, lulus uji cetak dan offline, serta memiliki backup. Rollback setelah transaksi baru terjadi memerlukan rekonsiliasi, bukan sekadar mengembalikan backup lama.


## 20 Kontrak data dan integritas

ERD pendamping menjadi model logis konsolidasi, bukan DDL produksi yang telah diuji. Penamaan tabel pada model dapat berbeda dari potongan SQL lama untuk menghapus duplikasi dan memperjelas batas POS/SO. Semua mapping harus dipertahankan dalam migrasi.

### Prinsip implementasi

ID dokumen/transaksi menggunakan UUID agar aman dari benturan antarterminal. Nomor bisnis tetap terpisah untuk dibaca manusia.

Mutasi stok, perubahan saldo cepat, dokumen dan jurnal dilakukan dalam transaksi database yang sama untuk satu kejadian.

Kunci stok dikunci berurutan per lokasi/SKU; cek ketersediaan dilakukan atomik untuk semua pengeluaran non-POS.

Header dokumen umum menyediakan identitas untuk approval, audit, lampiran, mutasi dan jurnal; jenis dokumen harus cocok dengan tabel rinciannya.

Satu goods receipt posted/final per PO; pengembalian atau koreksi tidak menciptakan penerimaan kedua.

Penjualan POS dan SO dipisahkan agar aturan H+1 tidak memblokir transaksi POS hari yang sama.

Reservasi, alokasi WO, snapshot komponen paket, dan sumber owned/consignment wajib terstruktur; tidak hanya disimpan dalam notes JSON.

### Kelompok API yang wajib tersedia

Auth dan master CRUD; approval rules/requests/actions; purchasing/receipts/invoices/returns; inventory/reservations/transfers/receipts/discrepancies; BOM/demand/WO/completion; SO/components/delivery/DP/invoice/returns; POS/sales/shifts/payments/returns; finance/periods/reports; sync/push/pull/ack/conflicts.

API command menggunakan idempotency key, validasi status, kontrol revisi, dan respons kesalahan yang konsisten. OpenAPI lama harus diperbarui; dokumen ini tidak mengklaim seluruh kontrak endpoint tersebut sudah diimplementasikan.


## 21 Kriteria penerimaan 1 sampai 10

Skenario berikut wajib diuji pada database transaksi yang sesungguhnya. Skenario konkurensi/offline diuji dengan dua terminal atau dua sesi aktif; hasil di bawah adalah target penerimaan, bukan laporan tes yang telah dijalankan.



| ID | Skenario | Hasil yang harus dibuktikan |
| --- | --- | --- |
| U01 | PO 10 dus diterima 5 | Stok +5; kekurangan ditutup; receive kedua ditolak tanpa menambah stok/utang. |
| U02 | Dua petugas receive PO bersamaan | Hanya satu commit; tidak ada penerimaan atau jurnal ganda. |
| U03 | PO SO berisi barang supplier | PO terikat satu SO, masuk packing, komponen dibeli tidak dibuat WO. |
| U04 | SO batal setelah penerimaan supplier | Reservasi lepas; barang dapat ditransfer ke toko; utang tetap. |
| U05 | Barang U04 dijual POS | Sumber owned; stok keluar sekali tanpa pengakuan titipan/utang baru. |
| U06 | Titipan 120 fisik dan 20 terjual | Fisik 120 di kartu manual; hanya 20 masuk dan 20 keluar sistem; kewajiban untuk 20. |
| U07 | Titipan offline dikirim ulang | Pasangan mutasi dan kewajiban supplier tidak berganda. |
| U08 | Transfer kirim 100 terima 98 | Sumber -100, tujuan +98, transit 2; selisih terbuka. |
| U09 | Dua unit transit dinyatakan hilang | Approval tercatat; transit -2; kerugian tercatat sekali. |
| U10 | Selisih ternyata salah jumlah kirim | Koreksi tertaut; saldo sumber dipulihkan sesuai bukti; riwayat tetap ada. |


## 22 Kriteria penerimaan 11 sampai 20

Skenario berikut wajib diuji pada database transaksi yang sesungguhnya. Skenario konkurensi/offline diuji dengan dua terminal atau dua sesi aktif; hasil di bawah adalah target penerimaan, bukan laporan tes yang telah dijalankan.



| ID | Skenario | Hasil yang harus dibuktikan |
| --- | --- | --- |
| U11 | SO dan POS pada hari yang sama | SO same-day ditolak; POS hari yang sama tetap berhasil. |
| U12 | Jam jadwal diubah | Pesanan baru memakai versi baru; SO terkonfirmasi mempertahankan snapshot. |
| U13 | Tambahan SO setelah WO | Tanpa approval ditolak; setelah approval hanya kebutuhan tambahan diproduksi. |
| U14 | Permintaan toko plus minimum stok | Kebutuhan yang sudah tercakup tidak dihitung dua kali; transit diperhitungkan. |
| U15 | Paket SO dan komponen satuan | Invoice paket satu harga; kebutuhan dan stok komponen dihitung tepat sekali. |
| U16 | Snack box POS | Produk dan kemasan mempunyai harga baris masing-masing; tidak memakai harga paket SO. |
| U17 | BOM berubah setelah WO | WO tetap memakai snapshot lama; perubahan berikutnya memakai versi baru. |
| U18 | Bahan produksi tidak cukup | Seluruh start dibatalkan atomik; stok tidak minus dan WO belum mulai. |
| U19 | Sisa bahan dikembalikan | Stok RAW bertambah dengan biaya asal; biaya bersih WO berkurang. |
| U20 | 100 telur menghasilkan putih telur | Biaya telur seluruhnya ke utama; putih telur masuk biaya nol dan dapat dijual/dipakai. |


## 23 Kriteria penerimaan 21 sampai 30

Skenario berikut wajib diuji pada database transaksi yang sesungguhnya. Skenario konkurensi/offline diuji dengan dua terminal atau dua sesi aktif; hasil di bawah adalah target penerimaan, bukan laporan tes yang telah dijalankan.



| ID | Skenario | Hasil yang harus dibuktikan |
| --- | --- | --- |
| U21 | Seluruh hasil utama gagal | Tidak membagi dengan nol; approval menutup WO dan mencatat kerugian. |
| U22 | DP sebagian lalu invoice dan pelunasan | Saldo DP/piutang benar; alokasi tidak menggandakan kas atau pendapatan. |
| U23 | SO batal dengan DP | Refund backoffice tertaut; nilai tidak melebihi saldo yang berhak dikembalikan. |
| U24 | Retur POS sebagian berulang | Akumulasi retur tidak melebihi penjualan; diskon/pajak/biaya mengikuti asal. |
| U25 | Retur titipan setelah settlement | Kredit/klaim supplier tercatat; tidak membayar kewajiban yang sama dua kali. |
| U26 | Dua POS offline menjual SKU sama | Keduanya tersimpan; cloud menggabungkan mutasi, tidak menimpa saldo. |
| U27 | Koneksi putus setelah cloud commit | Retry memberi hasil lama; satu struk, satu efek stok dan jurnal. |
| U28 | Event ID sama payload berbeda | Masuk conflict; tidak mengganti transaksi yang sudah diterima. |
| U29 | Restart Docker dengan antrean | Transaksi dan outbox tetap ada, sinkronisasi dapat dilanjutkan. |
| U30 | Refund transaksi terminal lain offline | Ditunda sampai validasi cloud; tidak terjadi refund ganda. |


## 24 Kriteria penerimaan 31 sampai 40

Skenario berikut wajib diuji pada database transaksi yang sesungguhnya. Skenario konkurensi/offline diuji dengan dua terminal atau dua sesi aktif; hasil di bawah adalah target penerimaan, bukan laporan tes yang telah dijalankan.



| ID | Skenario | Hasil yang harus dibuktikan |
| --- | --- | --- |
| U31 | Stok POS minus lalu barang masuk | HPP provisional dan penyesuaian tertaut; tidak ada rata-rata negatif/NaN. |
| U32 | Approval dokumen lalu isi berubah | Approval revisi lama tidak dapat dipakai untuk memposting revisi baru. |
| U33 | Pengguna tanpa hak posting | Ditolak meskipun boleh melihat semua toko/dapur. |
| U34 | Tutup periode ketika POS belum sync | Peringatan/gate pengecualian muncul; keputusan terotorisasi tercatat. |
| U35 | Event datang dari periode tertutup | Tanggal asli dipertahankan; koreksi periode terbuka mengikuti otorisasi. |
| U36 | Retur supplier setelah PO received | Stok/kredit berkurang; PO tidak terbuka untuk receive ulang. |
| U37 | Opname saat ada penjualan | Mutasi sesudah waktu hitung diperhitungkan; saldo tidak ditimpa. |
| U38 | Bootstrap atau upgrade dijalankan ulang | Migrasi idempotent; data transaksi tidak hilang atau terduplikasi. |
| U39 | Jurnal dan laporan satu periode | Debit= kredit; laporan hanya memakai jurnal sah dan rentang benar. |
| U40 | Restore backup dan reconnect terminal | Saldo serta event konsisten; tidak membuat transaksi duplikat setelah pemulihan. |


## 25 Konfigurasi sebelum go live



| Konfigurasi | Pemilik pengisian | Ketentuan |
| --- | --- | --- |
| Jadwal pagi/siang/sore | Operasional produksi | Jam cutoff H-1 dan jam kirim wajib diisi; tanpa jam, jadwal belum dapat dipakai. |
| Persetujuan | Manajemen | Tindakan, ambang, penyetuju, urutan langkah dan otorisasi offline. |
| SKU dan BOM | Produksi dan master data | Satuan/faktor, dapur, komponen, versi, hasil samping dan biaya nol. |
| Harga dan titipan | Penjualan dan pembelian | Harga per kanal/satuan, harga supplier titipan, masa berlaku, sumber owned/consignment. |
| Stok minimum | Operasional toko | Minimum, target, kelipatan, serta perhitungan kebutuhan terbuka. |
| Keuangan | Finance | COA, pemetaan jurnal, pajak, rekening, saldo awal, kebijakan pembulatan. |
| Terminal | Administrator | UUID terminal, toko/gudang, printer, kredensial sync, backup, kebijakan offline. |
| Cutover | Pemilik proyek | Tanggal freeze, rekonsiliasi saldo dan transaksi terbuka, penanggung jawab UAT. |

### Sumber dan urutan kewenangan

S1 DISKUSI 1 ERP: database dan proses A sampai H. S2 diskusi 2 ERP: ringkasan, ERD awal dan panduan. S3 DISKUSI 3 ERP: kontrak API awal. S4 klarifikasi pengguna pada percakapan 25 Oktober 2026: perubahan cakupan, transit, titipan, retur/DP, produksi, paket, approval dan dua aplikasi. S5 klarifikasi terakhir: jadwal terkonfigurasi, produk turunan biaya nol, dan seluruh SO di backoffice.

Urutan berlaku: S5, S4, lalu sumber awal sepanjang tidak bertentangan. Rancangan teknis dalam PRD/ERD melengkapi kebutuhan tanpa mengubah keputusan bisnis. Kebijakan tambahan yang belum ditetapkan, seperti batas offline, ambang approval dan pembulatan, wajib terkonfigurasi dan diverifikasi pada UAT.

### Dokumen pendamping

ERD_ERP_Yussy_Akmal_v1.0.pdf memuat diagram dan kamus data inti. ERP_Yussy_Akmal_v1.0.dbml memuat tabel dan foreign key yang dapat diedit. Paket sumber berisi versi Word, Markdown, DBML, PDF dan catatan konsistensi model. DDL migrasi, OpenAPI final, kode aplikasi serta hasil UAT merupakan pekerjaan implementasi berikutnya.
