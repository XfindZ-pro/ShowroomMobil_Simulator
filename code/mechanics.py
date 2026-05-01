import datetime
import locale
import random
import json
from database import DatabaseManager
try:
    from scraper import search_pasar_online
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False

try:
    locale.setlocale(locale.LC_TIME, 'id_ID')
except:
    pass

class GameEngine:
    def __init__(self):
        self.db = DatabaseManager()

    def _parse_int(self, value):
        try:
            return int(str(value).replace('.', '').replace(',', '').replace('Rp', '').strip())
        except:
            return 0

    def get_context_string(self):
        state = self.db.load_gamestate()
        fin = self.db.load_keuangan()
        inv = self.db.load_inventory()
        aset_list = self.db.load_aset()
        
        now = datetime.datetime.now()
        waktu_str = now.strftime("%A, %d %B %Y - Pukul %H:%M")
        
        available_cars = [c for c in inv if c.get('status', '').strip() == 'Tersedia']
        
        # Kapasitas dibaca dari Gamestate sekarang
        luas_display = state.get('luas_display', 0)
        kapasitas_max = luas_display // 25 if luas_display > 0 else 0
        
        aset_stok = sum(c.get('modal', 0) for c in available_cars)
        net_worth = fin.get('kas', 0) + aset_stok - fin.get('hutang_bank', 0)

        context = (
            f"=== DATA REAL-TIME ===\n"
            f"Waktu: {waktu_str}\n"
            f"Showroom: {state.get('showroom_name')} | Lokasi: {state.get('lokasi')}\n"
            f"Keuangan: Kas Rp {fin.get('kas',0):,} | Net Worth Rp {net_worth:,}\n"
            f"Fasilitas: Display {luas_display}m2 (Terisi: {len(available_cars)}/{kapasitas_max} Unit)\n"
        )

        # Daftar Aset Showroom (Barang & Dokumen)
        if aset_list:
            context += "=== ASET & DOKUMEN ===\n"
            for a in aset_list:
                context += f"- {a['nama_aset']} ({a['jumlah']} {a['satuan']}) | Kat: {a['kategori']}\n"
        
        context += "=== LIST UNIT (GARASI) ===\n"
        if not available_cars:
            context += "(Garasi Kosong)\n"
        else:
            for c in available_cars:
                h_jual = c.get('harga_jual', 0)
                modal = c.get('modal', 0)
                lbl_harga = f"Jual: Rp {h_jual:,}" if h_jual > 0 else "Jual: Belum diset"
                context += f"- [{c.get('id')}] {c.get('nama_mobil')} ({c.get('tahun')}) | Modal: Rp {modal:,} | {lbl_harga}\n"
        
        # Riwayat Transaksi (Log)
        logs = state.get('transaksi_log', [])
        context += "=== RIWAYAT TRANSAKSI (LOG) ===\n"
        if not logs:
            context += "(Belum ada transaksi yang tercatat)\n"
        else:
            # Ambil 5 log terakhir agar tidak terlalu panjang
            for log in logs[:10]:
                context += f"- {log}\n"
        
        return context

    def setup_showroom(self, nama, owner, lokasi, modal, luas_tanah):
        """Inisialisasi data showroom baru."""
        state = self.db.load_gamestate()
        fin = self.db.load_keuangan()
        
        lt = self._parse_int(luas_tanah)
        m = self._parse_int(modal)
        
        # Alokasi Luas (Default: 70% Display, 30% Kantor)
        ld = int(lt * 0.7)
        lk = lt - ld
        
        state.update({
            "showroom_name": nama,
            "owner": owner,
            "lokasi": lokasi,
            "luas_tanah": lt,
            "luas_display": ld,
            "luas_kantor": lk,
            "is_setup": True,
            "transaksi_log": ["Sistem Showroom Diaktifkan"]
        })
        
        fin['kas'] = m
        
        # Tambah Aset Awal (Surat Tanah)
        aset_awal = [
            {
                "nama_aset": f"Sertifikat Tanah {nama}",
                "jumlah": 1,
                "satuan": "Buku",
                "kategori": "Dokumen",
                "keterangan": f"Bukti kepemilikan lahan {lt}m2"
            }
        ]
        
        self.db.save_gamestate(state)
        self.db.save_keuangan(fin)
        self.db.save_aset(aset_awal)
        return True, "Setup Berhasil!"

    def read_full_database(self, db_name):
        """Membaca isi lengkap tabel database tertentu."""
        data = {}
        if 'keuangan' in db_name.lower():
            data = self.db.load_keuangan()
            judul = "KEUANGAN"
        elif 'aset' in db_name.lower():
            data = self.db.load_aset()
            judul = "ASET"
        elif 'gamestate' in db_name.lower() or 'status' in db_name.lower():
            data = self.db.load_gamestate()
            judul = "GAMESTATE"
        elif 'inventory' in db_name.lower():
            data = self.db.load_inventory()
            judul = "INVENTORY"
        else:
            return "❌ Database tidak dikenali. Coba: keuangan, aset, gamestate, inventory."

        json_str = json.dumps(data, indent=2, default=str)
        return f"📂 **ISI TABEL {judul}:**\n```json\n{json_str}\n```"

    def inspect_unit(self, keyword):
        inv = self.db.load_inventory()
        keyword = keyword.lower().strip()
        found = [c for c in inv if keyword in c.get('id', '').lower() or keyword in c.get('nama_mobil', '').lower()]
        
        if not found: return "❌ Unit tidak ditemukan."
        
        res = "📄 **DETAIL UNIT DARI DATABASE:**\n"
        for c in found:
            res += f"""
> **{c.get('nama_mobil')}**
> - ID: `{c.get('id')}`
> - Plat: `{c.get('plat')}`
> - Modal: **Rp {c.get('modal'):,}**
> - Harga Jual: Rp {c.get('harga_jual', 0):,}
> - Mesin: {c.get('mesin')} | BBM: {c.get('sisa_bbm')}
> - KM: {c.get('kilometer')}
> - Pajak: {c.get('pajak')}
> - Status: {c.get('status')}
----------------
"""
        return res


    def cari_pasar_online(self, query: str, force_refresh: bool = False) -> str:
        """Scrape harga pasar dari situs online (OLX, Mobil123, Carmudi)."""
        if not SCRAPER_AVAILABLE:
            return "❌ Modul scraper tidak tersedia. Pastikan beautifulsoup4 terinstall."
        
        hasil = search_pasar_online(query, force_refresh=force_refresh)
        return hasil.get("summary", "Tidak ada hasil.")

    def set_harga_unit(self, car_id, harga_baru):
        inv = self.db.load_inventory()
        target_idx = -1
        for i, c in enumerate(inv):
            if c['id'].lower() == car_id.lower():
                target_idx = i
                break
        
        if target_idx == -1: return False, "Unit ID tidak ditemukan."
        
        harga_clean = self._parse_int(harga_baru)
        inv[target_idx]['harga_jual'] = harga_clean
        self.db.save_inventory(inv)
        return True, f"✅ Sukses! Harga **{inv[target_idx]['nama_mobil']}** diubah menjadi **Rp {harga_clean:,}**"

    def beli_mobil(self, model, tahun, harga, kondisi, plat=None):
        state = self.db.load_gamestate()
        fin = self.db.load_keuangan()
        inv = self.db.load_inventory()
        
        # Kapasitas dari state
        kapasitas = state.get('luas_display', 0) // 25
        available = len([c for c in inv if c.get('status', '').strip() == 'Tersedia'])
        if available >= kapasitas: return False, "Garasi Penuh!"

        harga_clean = self._parse_int(harga)
        if fin['kas'] < harga_clean: return False, f"Kas tidak cukup (Butuh Rp {harga_clean:,})"
            
        fin['kas'] -= harga_clean
        new_id = f"UNIT-{len(inv)+1:03d}"
        
        # Plat Default Surabaya (L) jika tidak ditentukan
        if not plat:
            plat = f"L {random.randint(1000,9999)} {random.choice(['XY', 'AZ', 'QR', 'SB'])}"

        new_car = {
            "id": new_id, 
            "nama_mobil": model, 
            "plat": plat,
            "transmisi": "Manual", # Default manual sesuai style motuba
            "pajak": 2027, 
            "kilometer": f"{random.randint(50,180)}.000 km",
            "status_unit": kondisi, 
            "modal": harga_clean, 
            "kepemilikan": "Showroom",
            "harga_jual": 0, 
            "mesin": "Bensin", 
            "sisa_bbm": "1/2 Tank",
            "tahun": self._parse_int(tahun), 
            "status": "Tersedia",
            "tanggal_beli": str(datetime.date.today())
        }
        inv.append(new_car)
        state["transaksi_log"].append(f"BELI {model} -Rp {harga_clean:,}")
        self.db.save_gamestate(state)
        self.db.save_keuangan(fin)
        self.db.save_inventory(inv)
        return True, f"Sukses beli {model}."

    def jual_mobil(self, car_id, harga_deal):
        state = self.db.load_gamestate()
        fin = self.db.load_keuangan()
        inv = self.db.load_inventory()
        
        target_idx = -1
        for i, c in enumerate(inv):
            # Cek ID (Case Insensitive)
            if c['id'].lower() == car_id.lower():
                target_idx = i
                break
        
        if target_idx == -1: 
            return False, f"Unit ID '{car_id}' tidak ditemukan di inventory."
        
        if inv[target_idx].get('status') != 'Tersedia':
            return False, f"Unit {inv[target_idx]['nama_mobil']} statusnya bukan 'Tersedia'."

        # Validasi Harga Jual (Pesan Bos: Harus diatur dulu)
        current_asking_price = inv[target_idx].get('harga_jual', 0)
        if current_asking_price <= 0:
            return False, f"⚠️ Harga jual belum diatur untuk {inv[target_idx]['nama_mobil']}. Silakan atur harga jual terlebih dahulu!"

        hj_clean = self._parse_int(harga_deal)
        
        # Fallback ke harga_jual di database jika input 0/kosong
        if hj_clean <= 0:
            hj_clean = inv[target_idx].get('harga_jual', 0)
        
        if hj_clean <= 0:
            return False, f"⚠️ Harga deal Rp 0 tidak valid. Silakan tentukan harga deal atau atur harga jual unit!"

        profit = hj_clean - inv[target_idx].get('modal', 0)
        
        fin['kas'] += hj_clean
        state['total_transaksi'] += 1
        nama_mobil = inv[target_idx]['nama_mobil']
        del inv[target_idx]
        
        state["transaksi_log"].append(f"JUAL {nama_mobil} +Rp {profit:,}")
        self.db.save_gamestate(state)
        self.db.save_keuangan(fin)
        self.db.save_inventory(inv)
        return True, f"Terjual! {nama_mobil} laku Rp {hj_clean:,}"

    def set_harga_unit(self, car_id, harga_baru):
        inv = self.db.load_inventory()
        target_idx = -1
        for i, c in enumerate(inv):
            if c['id'].lower() == car_id.lower():
                target_idx = i
                break
        
        if target_idx == -1: return False, f"Unit ID {car_id} tidak ditemukan."
        
        harga_clean = self._parse_int(harga_baru)
        inv[target_idx]['harga_jual'] = harga_clean
        self.db.save_inventory(inv)
        return True, f"Harga jual {inv[target_idx]['nama_mobil']} diatur ke Rp {harga_clean:,}"

    def pindah_lokasi(self, lokasi_baru):
        state = self.db.load_gamestate()
        state['lokasi'] = lokasi_baru
        self.db.save_gamestate(state)
        return True, f"Showroom Firzanta Motor resmi pindah ke {lokasi_baru}!"

    def bayar_gaji(self):
        state = self.db.load_gamestate()
        fin = self.db.load_keuangan()
        karyawan = state.get('karyawan', [])
        if not karyawan: return False, "Tidak ada karyawan."
        total = sum(k['gaji_bulanan'] for k in karyawan)
        if fin['kas'] < total: return False, "Kas kurang."
        fin['kas'] -= total
        state["transaksi_log"].append(f"PAYROLL -Rp {total:,}")
        self.db.save_gamestate(state)
        self.db.save_keuangan(fin)
        return True, f"Gaji lunas Rp {total:,}."

    def tambah_karyawan(self, n, j, g):
        state = self.db.load_gamestate()
        g_clean = self._parse_int(g)
        new_emp = {"id": f"EMP-{len(state.get('karyawan', []))+1:03d}", "nama": n, "jabatan": j, "gaji_bulanan": g_clean}
        state.setdefault('karyawan', []).append(new_emp)
        self.db.save_gamestate(state)
        return True, f"Karyawan {n} direkrut."