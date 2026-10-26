# ERP Yussy Akmal

Backoffice cloud dan POS lokal per mesin kasir. **Implementasi awal 0.1.0 untuk uji operasional terkontrol**, berdasarkan keputusan bisnis dan spesifikasi v1.0. Belum dipasang pada server perusahaan atau mesin kasir operasional.

## Dokumen

| Kebutuhan | Berkas |
| --- | --- |
| PRD | [PDF](docs/prd/PRD_ERP_Yussy_Akmal_v1.0.pdf), [Word](docs/prd/PRD_ERP_Yussy_Akmal_v1.0.docx), [Markdown](docs/prd/PRD_ERP_Yussy_Akmal_v1.0.md) |
| ERD, 104 tabel bisnis | [PDF](docs/erd/ERD_ERP_Yussy_Akmal_v1.0.pdf) |
| DBML | [ERP_Yussy_Akmal_v1.0.dbml](schema/ERP_Yussy_Akmal_v1.0.dbml) |
| Model aplikasi | [JSON](schema/ERD_Model_Yussy_Akmal_v1.0.json) |
| Desain, 30 layar Backoffice dan 8 POS | [PDF](docs/ui/Desain_UI_Wireframe_Yussy_Akmal_v1.0.pdf), [spesifikasi](docs/ui/Spesifikasi_UI_Yussy_Akmal_v1.0.md), [SVG](docs/ui/Wireframe_SVG) |
| Enam alur UI | [Alur UI](docs/ui/Alur_UI_Yussy_Akmal_v1.0.md) |
| Keputusan dan UAT | [Keterlacakan](docs/prd/Keterlacakan_Keputusan_v1.0.md), [40 skenario target UAT](docs/prd/UAT_Cases_Yussy_Akmal_v1.0.json) |

## Aplikasi

- **Backoffice:** master, SO/paket satu harga, DP, jadwal H-1, resep dan produksi, PO/penerimaan final, transfer/transit, persetujuan, retur/refund, invoice, jurnal, periode dan monitor sinkronisasi.
- **POS lokal:** penjualan barang toko dan kemasan terpisah, sumber owned/titipan, split payment, struk, shift, retur lokal dengan supervisor dan antrean persisten. SO berada di Backoffice.
- FastAPI, SQLAlchemy, HTML/CSS/JavaScript lokal tanpa CDN. PostgreSQL 17 pada Docker; SQLite untuk pengembangan dan pengujian.
- Satu instalasi dan database POS per komputer kasir. Event berurutan, UUID/hash, pengiriman ulang dan ACK setelah commit; saldo lokal tidak dikirim untuk menimpa saldo cloud.

## Mulai dengan Docker

Prasyarat: Git, Python 3.12+, Docker Engine/Desktop dengan Compose v2. Internet diperlukan untuk pemasangan pertama.

```bash
git clone https://github.com/yussyakmal-dotcom/ERP-YA.git
cd ERP-YA
python3 scripts/configure.py cloud --output .env.cloud
docker compose --env-file .env.cloud -f compose.cloud.yml up -d --build --wait
```

Buka `http://localhost:8080`. Gunakan `SETUP_TOKEN` dari `.env.cloud` untuk membuat administrator pertama. Tidak ada akun atau sandi default. Untuk cloud perusahaan, pasang HTTPS dan ikuti [panduan pemasangan](docs/INSTALL.md).

Pada **masing-masing komputer kasir**, gunakan salinan repositori sendiri:

```bash
python3 scripts/configure.py pos --output .env.pos
docker compose --env-file .env.pos -f compose.pos.yml up -d --build --wait
```

Buka `http://localhost:8081`; pasangkan URL HTTPS Backoffice dan token terminal berbeda yang dibuat di Backoffice. Volume database pada tiap komputer terpisah.

## Pengembangan dan pemeriksaan

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8080
python -m pytest -q
node --check app/static/app.js
node --check app/static/pos.js
node --check app/static/settings.js
```

Mode pengembangan menggunakan SQLite `data/erp.db`. Lihat [INSTALL.md](docs/INSTALL.md) untuk mode POS terpisah, backup/restore, pairing, master awal, dan penanganan konflik.

**[Hasil validasi](docs/VALIDATION.md) dan [cakupan/batas implementasi](docs/IMPLEMENTATION_STATUS.md)** menjelaskan yang sudah berjalan dan yang masih perlu diselesaikan. PRD dan wireframe adalah target; keberadaan tabel bukan bukti seluruh fitur atau UAT selesai.

Batch, expiry dan FEFO tetap ditunda. Jam jadwal, harga, pajak, resep, stok awal dan matriks persetujuan harus diisi perusahaan. Migrasi sistem lama, laporan lanjutan, integrasi bank, perangkat fisik dan go-live masih memerlukan pekerjaan serta UAT nyata.
