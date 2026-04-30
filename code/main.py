import ollama
import re
import os
import sys
import shutil
import time
import traceback
from config import MODEL_NAME, RULES_FILE
from mechanics import GameEngine
from database import DatabaseManager

sys.path.append(os.path.join(os.path.dirname(__file__), 'system'))
from rules import get_rules # Import dari rules.py

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def run_setup_wizard(engine):
    print("\n" + "="*50)
    print("   🔧 KONFIGURASI SHOWROOM BARU 🔧")
    print("="*50)
    
    nama = input("1. Nama Showroom   : ") or "Showroom Saya"
    owner = input("2. Nama Pemilik    : ") or "Bos Muda"
    lokasi = input("3. Lokasi Showroom : ") or "Jakarta"
    
    print("\n--- ASET & MODAL ---")
    luas_tanah = input("4. Luas Tanah (m2) : ") or "300"
    modal_input = input("5. Modal Awal (Rp) : ") or "100000000"
    
    engine.setup_showroom(nama, owner, lokasi, modal_input, luas_tanah)
    print("\n✅ Konfigurasi tersimpan! Memulai sistem AI...\n")
    time.sleep(1)

def main():
    clear_screen()
    try:
        db = DatabaseManager()
        engine = GameEngine()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        input("Enter untuk keluar...")
        return

    state = db.load_gamestate()
    if not state.get('is_setup', False):
        run_setup_wizard(engine)
        state = db.load_gamestate()

    print("\n🚗 === SIMULATOR SHOWROOM V2.8 (OFFLINE MARKET) === 🚗")
    print(f"      --- {state.get('showroom_name', 'Unknown').upper()} ---")
    print("Ketik 'exit' untuk keluar.\n")
    
    chat_history = []
    rules_text = get_rules() # Mengambil langsung dari Python
    
    while True:
        try:
            data_context = engine.get_context_string()
            
            # --- PROMPT ANTI HALUSINASI & ANTI AUTO-SEARCH ---
            system_prompt = f"""
            {rules_text}
            
            === ATURAN MUTLAK (JANGAN DILANGGAR) ===
            1. **DILARANG BERTINDAK SENDIRI:** Jangan pernah mengeluarkan tag [ACTION:...] jika user tidak menyuruhnya.
            2. **KHUSUS PENCARIAN:** JANGAN otomatis mencari (SEARCH) saat stok kosong. Tunggu user mengetik "Cari harga X".
            3. **KHUSUS PEMBELIAN:** JANGAN otomatis beli (BUY). Tunggu user mengetik "Beli X" atau "Deal".
            
            === FORMAT SARAN ===
            Jika stok kosong, cukup berikan **SARAN** (Nomor 1, 2, 3).
            Contoh:
            "Bos, garasi kosong. Saran saya:
            1. Cari harga Avanza.
            2. Cari harga Brio."
            (JANGAN LANGSUNG EKSEKUSI [ACTION:SEARCH...])

            === DATA REAL-TIME ===
            {data_context}
            
            === TAG PERINTAH (HANYA KELUARKAN JIKA DISURUH) ===
            - [ACTION:BUY|Model|Tahun|Harga_Angka|Kondisi]
            - [ACTION:SELL|ID_Unit|Harga_Deal_Angka]
            - [ACTION:SEARCH|Nama_Mobil]   <-- JANGAN GUNAKAN KECUALI DISURUH "CARI"!
            - [ACTION:HIRE|Nama|Jabatan|Gaji_Angka]
            - [ACTION:PAYROLL]
            """
            
            current_messages = [{'role': 'system', 'content': system_prompt}] + chat_history
            
            try:
                owner_name = state.get('owner', 'Bos')
                user_input = input(f"\n👤 {owner_name}: ")
            except KeyboardInterrupt: break
                
            if user_input.lower() in ["exit", "keluar"]: break
                
            chat_history.append({'role': 'user', 'content': user_input})
            current_messages.append({'role': 'user', 'content': user_input})
            
            print("🤖 Asisten sedang berpikir...", end="\r")
            
            try:
                response = ollama.chat(model=MODEL_NAME, messages=current_messages)
                ai_reply = response['message']['content']
            except Exception as e:
                print(f"\n❌ Error Ollama: {e}")
                continue
                
            print(" " * 30, end="\r")
            print(f"🤖 Asisten:\n{ai_reply}")
            
            action_happened = False
            def clean(s): return s.strip()

            # BUY
            buy = re.search(r"\[ACTION:BUY\|(.*?)\|(.*?)\|(.*?)\|(.*?)\]", ai_reply)
            if buy:
                try:
                    m, t, h, k = map(clean, buy.groups())
                    ok, msg = engine.beli_mobil(m, t, h, k)
                    print(f"\n⚙️ SYSTEM: {msg}")
                    chat_history.append({'role': 'system', 'content': f"SYSTEM: {msg}"})
                    action_happened = True
                except: pass

            # SELL
            sell = re.search(r"\[ACTION:SELL\|(.*?)\|(.*?)\]", ai_reply)
            if sell:
                try:
                    u, h = map(clean, sell.groups())
                    ok, msg = engine.jual_mobil(u, h)
                    print(f"\n⚙️ SYSTEM: {msg}")
                    chat_history.append({'role': 'system', 'content': f"SYSTEM: {msg}"})
                    action_happened = True
                except: pass
            
            # SEARCH (LOKAL)
            search = re.search(r"\[ACTION:SEARCH\|(.*?)\]", ai_reply)
            if search:
                try:
                    q = clean(search.group(1))
                    print(f"\n🌍 Mencari di Database Lokal: {q}...")
                    res = engine.cari_harga_pasar(q)
                    print(res)
                    chat_history.append({'role': 'system', 'content': res})
                except: pass

            # HIRE
            hire = re.search(r"\[ACTION:HIRE\|(.*?)\|(.*?)\|(.*?)\]", ai_reply)
            if hire:
                try:
                    n, j, g = map(clean, hire.groups())
                    ok, msg = engine.tambah_karyawan(n, j, g)
                    print(f"\n🤝 HRD: {msg}")
                    chat_history.append({'role': 'system', 'content': f"SYSTEM: {msg}"})
                    action_happened = True
                except: pass

            # PAYROLL
            if "[ACTION:PAYROLL]" in ai_reply:
                try:
                    ok, msg = engine.bayar_gaji()
                    print(f"\n💰 FINANCE: {msg}")
                    chat_history.append({'role': 'system', 'content': f"SYSTEM: {msg}"})
                    action_happened = True
                except: pass

            if not action_happened:
                chat_history.append({'role': 'assistant', 'content': ai_reply})

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()