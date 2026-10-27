# Tema Backoffice navy dan cyan

Diterapkan 27 Oktober 2026 mengikuti referensi tampilan yang diberikan pengguna.

- Sidebar navy, ikon garis, penanda cyan untuk modul aktif, dan tombol untuk menciutkan menu.
- Header putih ringkas dengan breadcrumb, nama pengguna, dan tombol keluar.
- Tab modul cyan yang dapat digulir mendatar, toolbar pencarian/tindakan, tabel rapat dengan warna baris berselang-seling.
- Warna dan bentuk konsisten untuk dashboard, master, dokumen, modal formulir, CSV, dan halaman login Backoffice.
- Menu ponsel dibuka lewat tombol header dan ditutup saat memilih modul. Tabel dan tab yang lebar dapat digulir di dalam wadahnya.

Implementasi: `app/static/backoffice.css`, dimuat setelah stylesheet dasar. Semua aturan tema dibatasi pada `body[data-mode="backoffice"]`. POS lokal tetap menggunakan stylesheet dasar dan ukuran tombol sentuhnya. Ikon dibuat dengan SVG lokal; tidak memerlukan font atau aset dari layanan eksternal.

## Verifikasi

- Suite yang sudah ada: **55 passed**, satu peringatan deprecation dari dependensi TestClient.
- Pemeriksaan sintaks JavaScript dan `git diff --check` berhasil.
- Chromium dengan database SQLite sementara: login, tabel produk desktop 1440×960, formulir tambah produk, unduh template CSV, pratinjau dan penerapan CSV, ciutkan/buka sidebar, navigasi ponsel 390×844. Tidak ditemukan page error JavaScript atau overflow horizontal pada halaman ponsel yang diuji.
- Screenshot dashboard, tabel produk, formulir, impor CSV, dan ponsel telah diperiksa secara visual. Data yang tampil berasal dari fixture pengujian, bukan data operasional.

Belum dilakukan UAT pada browser/perangkat pengguna. Perubahan ini tidak mengubah struktur database dan tidak memerlukan migrasi.

## Pembaruan cloud

Dari folder instalasi server, setelah backup database:

```bash
git pull --ff-only origin main
docker compose --env-file .env.cloud -f compose.cloud.yml up -d --build --wait backoffice
```

Kemudian muat ulang browser dengan Ctrl+Shift+R. Lihat `docs/INSTALL.md` untuk backup dan pemeriksaan layanan.
