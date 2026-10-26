# Paket Desain UI dan DBML ERP Yussy Akmal v1.0

25 Oktober 2026. Berdasarkan PRD dan ERD v1.0 yang sudah dibuat.

## Berkas
- Desain_UI_Wireframe_Yussy_Akmal_v1.0.pdf: peta navigasi, panduan visual, 6 alur, 38 wireframe, keadaan layar, dan handoff.
- Wireframe_SVG/: setiap halaman PDF sebagai SVG vektor. Buka di editor vektor untuk revisi. Menggunakan font DejaVu Sans dan DejaVu Serif; tampilan dapat berubah jika font diganti.
- Spesifikasi_UI_Yussy_Akmal_v1.0.md: field, aksi, validasi, transisi, entitas dan referensi UAT untuk setiap layar.
- Alur_Mermaid/: satu file Mermaid per alur yang dapat dirender sendiri.
- Alur_UI_Yussy_Akmal_v1.0.md: kumpulan 6 diagram dalam blok Mermaid terpisah, beserta catatan bisnis.
- ERP_Yussy_Akmal_v1.0.dbml: DBML terpisah, identik dengan versi dalam paket PRD/ERD sebelumnya. 104 tabel dan 282 relasi FK.
- Screen_Specifications_v1.0.json: spesifikasi terstruktur dan indeks halaman.

## Status
Desain statis untuk review, bukan aplikasi operasional atau prototype klik. Nomor, nama, jumlah dan harga adalah ilustrasi. Warna dan tipografi adalah usulan; bukan aset merek resmi.

DBML adalah model logis, bukan migrasi SQL siap produksi. Sintaks parser eksternal dan migrasi database belum dijalankan. Integritas referensi diperiksa terhadap model, dan semua entitas yang dirujuk desain harus ada di DBML. Validasi aturan bisnis tetap membutuhkan transaksi service/database dan pengujian implementasi.

Jam jadwal, approver, ambang, harga, pajak, minimum stok dan kebijakan operasional harus diisi/dikonfirmasi saat konfigurasi. Desain tidak mengubah keputusan PRD.
