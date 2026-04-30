# Firzanta Motor OS

Firzanta Motor OS adalah sistem manajemen showroom mobil bekas berbasis AI. Sistem ini dirancang khusus untuk mempermudah pengelolaan operasional jual-beli mobil, mulai dari interaksi dengan pelanggan, pencarian data pasar, hingga manajemen database internal.

## Fitur Utama

- **Asisten AI Interaktif:** Ditenagai oleh model AI (via Ollama) yang berperan sebagai penasihat operasional showroom untuk membantu Anda mengambil keputusan bisnis.
- **Pencarian Pasar Real-Time (Web Scraper):** Mengumpulkan informasi katalog mobil bekas secara langsung dari platform jual beli untuk memantau harga pasar, tahun produksi, jarak tempuh, dan lokasi.
- **Manajemen Database Terpadu:** Sistem untuk melacak inventaris unit mobil, status keuangan (kas, hutang, aset), data karyawan, serta log transaksi.
- **UI/UX Modern:** Tampilan antarmuka yang dinamis dan ringan, dibangun menggunakan Tailwind CSS dan Alpine.js untuk pengalaman pengguna yang cepat dan responsif.

## Prasyarat

- Python 3.10 atau lebih baru.
- Library Python: `flask`, `ollama`, `beautifulsoup4`, `requests`, `duckduckgo_search`.
- Pastikan service Ollama berjalan di latar belakang jika menggunakan model AI lokal.

## Cara Menjalankan

1. Buka terminal atau command prompt.
2. Arahkan ke dalam direktori repositori:
   ```bash
   cd "Firzanta Motor"
   ```
3. (Opsional) Install library yang dibutuhkan:
   ```bash
   pip install flask ollama beautifulsoup4 requests duckduckgo-search
   ```
4. Jalankan aplikasi web:
   ```bash
   python website/app.py
   ```
5. Buka web browser dan akses alamat:
   **http://127.0.0.1:5000**

## Arsitektur Sistem

- **Backend:** Python (Flask), SQLite (`firzanta_motor.db`).
- **Frontend:** HTML5, Tailwind CSS, Alpine.js, Vanilla JavaScript.
- **AI/Logika:** Modul mekanik game (`mechanics.py`) dan scraper terdedikasi (`scraper.py`).
