# Alur UI ERP Yussy Akmal v1.0
25 Oktober 2026 | Diagram pendamping desain layar

## F-01 - Pesanan pelanggan sampai terpenuhi
Backoffice mengelola SO, kebutuhan, pengiriman, DP dan pelunasan.

```mermaid
%% F-01 - Pesanan pelanggan sampai terpenuhi
flowchart TD
  a["Buat SO + paket / BO-03"]
  b["Validasi H-1 / snapshot / Jadwal lengkap"]
  c["Konfirmasi + demand / BO-04 / BO-09"]
  d["Produksi / BO-10 / BO-11"]
  e["PO khusus SO / BO-06 / BO-07"]
  f["Stok tersedia / Reservasi komponen"]
  g["Packing + delivery / BO-12"]
  h["Invoice + alokasi DP / BO-29 / BO-20"]
  a --> b
  b -->|"Lolos"| c
  c -->|"Buat sendiri"| d
  c -->|"Supplier"| e
  c -->|"Dari stok"| f
  d -->|"Transfer FIN"| g
  e -->|"Terima packing"| g
  f --> g
  g --> h
```

- Setelah WO dibuat, tambahan masuk approval produksi; hanya selisih kebutuhan yang ditambahkan.
- DP boleh diterima sebelum delivery melalui BO-04/20. Saat invoice terbentuk, DP dialokasikan tanpa kas masuk kedua.
- Komponen dibeli tidak masuk WO; seluruh komponen harus tersedia sebelum delivery yang bersangkutan.

## F-02 - PO hanya satu kali penerimaan
Sisa yang belum datang ditutup, bukan dibuat backorder.

```mermaid
%% F-02 - PO hanya satu kali penerimaan
flowchart TD
  a["PO confirmed / BO-06"]
  b["Input aktual per baris / BO-07"]
  c["Terima 5 dari 10 / Tutup kekurangan 5"]
  d["Semua aktual nol / Catat penolakan"]
  e["PO selesai diterima / Receive kedua terkunci"]
  f["Faktur + pembayaran / BO-29 / BO-20"]
  g["Kedatangan berikutnya / BO-08: kembalikan"]
  h["Retur dari receipt / BO-19: kredit supplier"]
  a --> b
  b -->|"Ada aktual > 0"| c
  b -->|"Semua nol"| d
  c -->|"Final"| e
  e --> f
  e -->|"Sisa datang"| g
  e -->|"Barang bermasalah"| h
```

- Jumlah aktual tidak melebihi pesanan. Baris nol perlu alasan; satu PO tidak dapat diposting oleh dua petugas sekaligus.
- Barang pada kedatangan berikutnya ditolak tanpa mutasi stok/utang. Bukti penolakan disimpan.
- Retur mengurangi stok/kewajiban yang sah, tetapi tidak membuka PO untuk penerimaan kedua.

## F-03 - Transfer 100, diterima 98
Selisih 2 pcs tetap terlihat sampai diperiksa dan diselesaikan.

```mermaid
%% F-03 - Transfer 100, diterima 98
flowchart TD
  a["Kirim 100 / BO-13: masuk transit"]
  b["Terima 98 / BO-14: stok toko +98"]
  c["Kasus selisih 2 / BO-15"]
  d["Masih di perjalanan / Tetap transit"]
  e["Diterima kemudian / Receipt tambahan"]
  f["Kembali ke packing / Konfirmasi tiba"]
  g["Rusak / hilang / Approval kerugian"]
  h["Salah jumlah kirim / Koreksi + bukti"]
  a --> b
  b -->|"Sisa 2"| c
  c -->|"Tindak lanjut"| d
  c --> e
  c --> f
  c --> g
  c --> h
```

- Hanya pilihan masih dalam perjalanan yang tidak menyelesaikan kuantitas transit. Catat PIC dan tenggat pemeriksaan.
- Barang kembali dipindahkan ke packing setelah tiba; rusak/hilang mengurangi transit lewat approval.
- Kesalahan jumlah kirim memulihkan sumber hanya bila barang memang tidak berangkat. Jumlah seluruh resolusi tidak boleh melebihi sisa.

## F-04 - Produksi dan hasil samping
Pemakaian bahan mengikuti resep; hasil aktual dicatat saat selesai.

```mermaid
%% F-04 - Produksi dan hasil samping
flowchart TD
  a["Kebutuhan + alokasi / BO-09"]
  b["WO + snapshot BOM / BO-10"]
  c["Mulai produksi / Keluar bahan otomatis"]
  d["Hasil utama layak / Masuk FIN dapur"]
  e["Sisa bahan layak / Kembali RAW / biaya asal"]
  f["Putih telur / SKU baru / Masuk biaya nol"]
  g["Produk gagal / Catat jumlah / alasan"]
  h["Selesaikan WO / BO-11: validasi biaya"]
  a --> b
  b -->|"Bahan cukup"| c
  c -->|"Catat hasil"| d
  c --> e
  c --> f
  c --> g
  d --> h
  e --> h
  f --> h
  g --> h
```

- Pengeluaran bahan strict non-minus. Kekurangan satu bahan membatalkan start seluruh WO.
- Seluruh biaya telur dibebankan pada produk utama; putih telur punya harga jual terpisah dan dapat dipakai sebagai bahan.
- Empat keluaran adalah input form penyelesaian, diposting atomik saat selesai. Hasil utama nol memerlukan approval kerugian.

## F-05 - POS lokal, dua kasir, satu cloud
Transaksi aman secara lokal; status penerimaan cloud ditampilkan terpisah.

```mermaid
%% F-05 - POS lokal, dua kasir, satu cloud
flowchart TD
  a["Kasir K01 / database A / PS-01 - PS-04"]
  b["Kasir K02 / database B / PS-01 - PS-04"]
  c["Commit lokal + antrean / Struk tersimpan"]
  d["Commit lokal + antrean / Struk tersimpan"]
  e["Cloud terima event unik / BO-24"]
  f["ACK + sinkron master / PS-08"]
  g["Konflik / periode tutup / Review backoffice"]
  a -->|"Bayar"| c
  b -->|"Bayar"| d
  c -->|"Saat tersambung"| e
  d -->|"Saat tersambung"| e
  e -->|"Berhasil"| f
  e -->|"Perlu tinjauan"| g
```

- Tidak mengirim saldo lokal untuk menimpa saldo cloud. Stok dua terminal mungkin berbeda saat offline; POS boleh minus dengan penanda.
- Retry memakai identitas event yang sama. ACK hilang tidak boleh menghasilkan penjualan dan jurnal ganda.
- Antrean tidak dibuang saat restart atau error. Tindakan diskon, batal, dan refund offline memakai persetujuan supervisor yang valid.

## F-06 - Pembatalan, retur, dan refund
Barang, hak kredit, dan uang mempunyai status masing-masing.

```mermaid
%% F-06 - Pembatalan, retur, dan refund
flowchart TD
  a["Pilih transaksi asal / SO / POS / receipt"]
  b["SO belum delivery / BO-05: pembatalan"]
  c["Penjualan sudah terjadi / BO-19 / PS-06: retur"]
  d["Retur supplier / BO-19"]
  e["Approval + hak refund / BO-22 / PS-05"]
  f["Barang / kredit tercatat / Disposisi sesuai asal"]
  g["Realisasi dana / BO-20 / POS refund"]
  a --> b
  a --> c
  a --> d
  b --> e
  c --> f
  d --> f
  e --> g
  f -->|"Hak tersisa"| g
```

- SO batal dengan barang supplier diterima: lepas reservasi, transfer ke toko sebagai owned, utang supplier tetap berlaku.
- Retur POS offline hanya untuk struk lokal tersedia. Struk terminal lain membutuhkan validasi cloud.
- Retur tidak selalu langsung refund; boleh kompensasi kredit sesuai dokumen. Jumlah dan uang dibatasi sisa hak setelah tindakan sebelumnya.
