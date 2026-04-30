import sqlite3
import os
import json
from config import DB_FILE

class DatabaseManager:
    def __init__(self):
        self.db_path = DB_FILE
        self.ensure_db_exists()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def reset_database(self):
        """Mereset seluruh database ke default (Hapus semua tabel dan buat ulang)."""
        tables = ['gamestate', 'inventory', 'keuangan', 'aset', 'karyawan', 'transaksi_log', 'cache_pasar']
        conn = self._get_connection()
        for t in tables:
            try:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            except:
                pass
        conn.commit()
        conn.close()
        self.ensure_db_exists()

    def ensure_db_exists(self):
        """Inisialisasi Database dan Tabel jika belum ada."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Tabel GameState (Ditambah luas_display & luas_kantor)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gamestate (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                showroom_name TEXT DEFAULT 'Showroom Baru',
                owner TEXT DEFAULT 'Pemain',
                reputasi INTEGER DEFAULT 10,
                total_transaksi INTEGER DEFAULT 0,
                lokasi TEXT DEFAULT 'Jakarta',
                luas_tanah INTEGER DEFAULT 300,
                is_setup BOOLEAN DEFAULT 0
            )
        ''')
        
        # Migrasi: Tambah kolom jika belum ada
        cursor.execute("PRAGMA table_info(gamestate)")
        gs_cols = [c[1] for c in cursor.fetchall()]
        if "luas_display" not in gs_cols:
            cursor.execute("ALTER TABLE gamestate ADD COLUMN luas_display INTEGER DEFAULT 200")
        if "luas_kantor" not in gs_cols:
            cursor.execute("ALTER TABLE gamestate ADD COLUMN luas_kantor INTEGER DEFAULT 100")

        # 2. Tabel Inventory
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id TEXT PRIMARY KEY,
                nama_mobil TEXT,
                plat TEXT,
                transmisi TEXT,
                pajak INTEGER,
                kilometer TEXT,
                status_unit TEXT,
                modal INTEGER,
                kepemilikan TEXT,
                harga_jual INTEGER,
                mesin TEXT,
                sisa_bbm TEXT,
                tahun INTEGER,
                status TEXT,
                tanggal_beli TEXT
            )
        ''')

        # 3. Tabel Keuangan
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keuangan (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                kas INTEGER DEFAULT 100000000,
                pihutang INTEGER DEFAULT 0,
                hutang_bank INTEGER DEFAULT 0,
                leasing_pending INTEGER DEFAULT 0,
                tagihan_lain INTEGER DEFAULT 0
            )
        ''')

        # 4. Tabel Aset (Skema Baru: List Barang & Dokumen)
        # Menghapus tabel lama jika skemanya masih yang lama (deteksi kolom display_unit)
        cursor.execute("PRAGMA table_info(aset)")
        cols = [c[1] for c in cursor.fetchall()]
        if "display_unit" in cols:
            cursor.execute("DROP TABLE aset")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama_aset TEXT,
                jumlah INTEGER,
                satuan TEXT,
                kategori TEXT,
                keterangan TEXT
            )
        ''')

        # 5. Tabel Karyawan
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS karyawan (
                id TEXT PRIMARY KEY,
                nama TEXT,
                jabatan TEXT,
                gaji_bulanan INTEGER
            )
        ''')

        # 6. Tabel Transaksi Log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaksi_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Masukkan data default jika tabel kosong (id=1)
        cursor.execute('INSERT OR IGNORE INTO gamestate (id) VALUES (1)')
        cursor.execute('INSERT OR IGNORE INTO keuangan (id) VALUES (1)')
        
        conn.commit()
        conn.close()

    # --- GAMESTATE ---
    def load_gamestate(self):
        conn = self._get_connection()
        res = conn.execute('SELECT * FROM gamestate WHERE id = 1').fetchone()
        state = dict(res) if res else {}
        
        # Load nested data (Karyawan & Log)
        state['karyawan'] = [dict(r) for r in conn.execute('SELECT * FROM karyawan').fetchall()]
        state['transaksi_log'] = [r['log_text'] for r in conn.execute('SELECT log_text FROM transaksi_log ORDER BY id DESC').fetchall()]
        
        # Mapping SQLite Boolean
        state['is_setup'] = bool(state.get('is_setup'))
        
        conn.close()
        return state

    def save_gamestate(self, data):
        conn = self._get_connection()
        # Update main fields
        conn.execute('''
            UPDATE gamestate SET 
                showroom_name = ?, owner = ?, reputasi = ?, 
                total_transaksi = ?, lokasi = ?, luas_tanah = ?, 
                luas_display = ?, luas_kantor = ?, is_setup = ?
            WHERE id = 1
        ''', (
            data.get('showroom_name'), data.get('owner'), data.get('reputasi'),
            data.get('total_transaksi'), data.get('lokasi'), data.get('luas_tanah'),
            data.get('luas_display', 200), data.get('luas_kantor', 100),
            1 if data.get('is_setup') else 0
        ))

        # Handle transaksi_log
        current_logs = [r['log_text'] for r in conn.execute('SELECT log_text FROM transaksi_log').fetchall()]
        new_logs = [log for log in data.get('transaksi_log', []) if log not in current_logs]
        for log in new_logs:
            conn.execute('INSERT INTO transaksi_log (log_text) VALUES (?)', (log,))

        # Handle karyawan
        conn.execute('DELETE FROM karyawan')
        for emp in data.get('karyawan', []):
            conn.execute('''
                INSERT INTO karyawan (id, nama, jabatan, gaji_bulanan)
                VALUES (?, ?, ?, ?)
            ''', (emp.get('id'), emp.get('nama'), emp.get('jabatan'), emp.get('gaji_bulanan')))

        conn.commit()
        conn.close()

    # --- KEUANGAN ---
    def load_keuangan(self):
        conn = self._get_connection()
        res = conn.execute('SELECT * FROM keuangan WHERE id = 1').fetchone()
        conn.close()
        return dict(res) if res else {}

    def save_keuangan(self, data):
        conn = self._get_connection()
        conn.execute('''
            UPDATE keuangan SET 
                kas = ?, pihutang = ?, hutang_bank = ?, 
                leasing_pending = ?, tagihan_lain = ?
            WHERE id = 1
        ''', (
            data.get('kas'), data.get('pihutang'), data.get('hutang_bank'),
            data.get('leasing_pending'), data.get('tagihan_lain')
        ))
        conn.commit()
        conn.close()

    # --- INVENTORY ---
    def load_inventory(self):
        conn = self._get_connection()
        res = conn.execute('SELECT * FROM inventory').fetchall()
        conn.close()
        return [dict(r) for r in res]

    def save_inventory(self, data):
        conn = self._get_connection()
        conn.execute('DELETE FROM inventory')
        for car in data:
            conn.execute('''
                INSERT INTO inventory (
                    id, nama_mobil, plat, transmisi, pajak, kilometer, 
                    status_unit, modal, kepemilikan, harga_jual, mesin, 
                    sisa_bbm, tahun, status, tanggal_beli
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                car.get('id'), car.get('nama_mobil'), car.get('plat'), car.get('transmisi'),
                car.get('pajak'), car.get('kilometer'), car.get('status_unit'), car.get('modal'),
                car.get('kepemilikan'), car.get('harga_jual'), car.get('mesin'),
                car.get('sisa_bbm'), car.get('tahun'), car.get('status'), car.get('tanggal_beli')
            ))
        conn.commit()
        conn.close()

    # --- ASET ---
    def load_aset(self):
        conn = self._get_connection()
        res = conn.execute('SELECT * FROM aset').fetchall()
        conn.close()
        return [dict(r) for r in res]

    def save_aset(self, data):
        """Menyimpan list aset. data harus berupa list of dict."""
        conn = self._get_connection()
        conn.execute('DELETE FROM aset')
        for a in data:
            conn.execute('''
                INSERT INTO aset (nama_aset, jumlah, satuan, kategori, keterangan)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                a.get('nama_aset'), a.get('jumlah'), a.get('satuan'),
                a.get('kategori'), a.get('keterangan')
            ))
        conn.commit()
        conn.close()

    def read_rules(self, filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f: return f.read()
        return "Rules file not found."