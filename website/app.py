import sys
import os
import re
import ollama
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify

# --- PATH CONFIGURATION ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
code_dir = os.path.join(parent_dir, 'code')
sys.path.append(code_dir)

from config import MODEL_NAME
from mechanics import GameEngine
from database import DatabaseManager
from system.rules import get_rules

app = Flask(__name__)


CHAT_HISTORY = []

try:
    db = DatabaseManager()
    engine = GameEngine()
except Exception as e:
    print(f"CRITICAL ERROR: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    global CHAT_HISTORY
    
    user_input = request.json.get('message')
    if not user_input: return jsonify({"error": "No input"}), 400

    # --- JALUR EKSEKUSI LANGSUNG (WRITE DB VIA POP-UP) ---
    # Bypass history LLM untuk eksekusi teknis agar tidak mengotori konteks
    if user_input.startswith('/execute_'):
        return handle_direct_execution(user_input)

    # --- JALUR CHAT NORMAL (LLM + MEMORY) ---
    state = db.load_gamestate()
    data_context = engine.get_context_string()
    rules_text = get_rules()

    # 1. System Prompt (Selalu Fresh dengan Data Terbaru)
    now = datetime.datetime.now()
    waktu_skrg = now.strftime("%A, %d %B %Y - Pukul %H:%M:%S")
    
    system_prompt = f"""
    {rules_text}
    
    === INFORMASI WAKTU (PENTING) ===
    Sekarang adalah: **{waktu_skrg}**
    Tahun saat ini: **2026** (Bukan 2023 atau 2024).
    Jangan pernah mengatakan fitur sedang dikembangkan atau data tidak ada karena "tahun belum sampai". 
    Semua data pasar 2025/2026 tersedia melalui [ACTION:SEARCH_ONLINE].

    === PERINTAH ANTI-HALUSINASI (MUTLAK) ===
    1. **DATA ADALAH KEADILAN:** Gunakan HANYA data dari section "=== DATA REAL-TIME ===" di bawah.
    2. **JANGAN MENGARANG TRANSAKSI:** Jika section "RIWAYAT TRANSAKSI (LOG)" hanya berisi "Sistem Showroom Diaktifkan", itu artinya **BELUM ADA PENJUALAN ATAU PEMBELIAN MOBIL**.
    3. **VERIFIKASI SEBELUM MENJAWAB:**
       - Apakah mobil ini ada di "LIST UNIT"? Jika tidak, jangan bilang ada.
       - Apakah transaksi ini ada di "RIWAYAT TRANSAKSI"? Jika tidak, jangan bilang sudah terjadi.
    4. **SISA KAS:** Gunakan angka Kas yang tertera. Jangan berimajinasi.

    === STATUS FITUR SISTEM (PENTING) ===
    - Fitur SEARCH_ONLINE: **AKTIF & SIAP PAKAI** — menggunakan DuckDuckGo real-time.
    - Saat Bos menyebut "cari", "kulakan", "restock", "ada apa di pasaran", "OLX", "Mobil123" → WAJIB gunakan [ACTION:SEARCH_ONLINE|query].
    - JANGAN katakan fitur sedang dalam pengembangan. Fitur ini SUDAH BERJALAN.
    - Contoh yang BENAR: "Siap Bos! Saya carikan sekarang. [ACTION:SEARCH_ONLINE|Toyota Avanza bekas]"

    === DATA REAL-TIME ===
    {data_context}
    """

    # 2. Susun Context: System Prompt + History (15 Terakhir) + Input User Saat Ini
    # Kita tidak memasukkan user_input ke history dulu, nanti setelah respon AI keluar
    messages = [{'role': 'system', 'content': system_prompt}] + CHAT_HISTORY + [{'role': 'user', 'content': user_input}]

    try:
        response = ollama.chat(model=MODEL_NAME, messages=messages)
        ai_reply = response['message']['content']
    except Exception as e:
        return jsonify({"response": f"❌ Error AI: {str(e)}", "system_msg": ""})

    # 3. Update History
    # Simpan User Input
    CHAT_HISTORY.append({'role': 'user', 'content': user_input})
    # Simpan AI Reply
    CHAT_HISTORY.append({'role': 'assistant', 'content': ai_reply})

    # 4. Truncate History (Jaga agar tetap 15 pasang / 30 pesan terakhir)
    if len(CHAT_HISTORY) > 30:
        CHAT_HISTORY = CHAT_HISTORY[-30:]

    # --- LOGIKA ACTION READ (Auto-Run) ---
    system_notification = ""
    def clean(s): return s.strip()

    # Inspect
    inspect = re.search(r"\[ACTION:INSPECT\|(.*?)\]", ai_reply)
    if inspect:
        res = engine.inspect_unit(inspect.group(1).strip())
        system_notification += f"{res}\n"
    
    # Search Online (dari situs jual-beli)
    search_online = re.search(r"\[ACTION:SEARCH_ONLINE\|(.*?)\]", ai_reply)
    if search_online:
        q = search_online.group(1).strip()
        print(f"[APP] ACTION:SEARCH_ONLINE triggered: {q}")
        res = engine.cari_pasar_online(q)
        system_notification += f"{res}\n"
        # Feed hasil ke chat history supaya AI bisa referensi di giliran berikutnya
        CHAT_HISTORY.append({'role': 'system', 'content': f'HASIL SEARCH ONLINE untuk "{q}":\n{res}'})

    return jsonify({
        "response": ai_reply,
        "system_msg": system_notification.strip()
    })

def handle_direct_execution(command):
    """Menulis ke database tanpa lewat LLM, tapi memberi info balik."""
    parts = command.split(' ')
    cmd_type = parts[0]
    args = parts[1:]
    
    msg = ""
    status = False

    try:
        if cmd_type == '/execute_setprice':
            status, msg = engine.set_harga_unit(args[0], args[1])
        
        elif cmd_type == '/execute_sell':
            status, msg = engine.jual_mobil(args[0], args[1])
            
        elif cmd_type == '/execute_buy':
            # args: Model(join space), Tahun, Harga, Kondisi
            kondisi = args[-1]
            harga = args[-2]
            tahun = args[-3]
            model = " ".join(args[:-3])
            status, msg = engine.beli_mobil(model, tahun, harga, kondisi)
            
        elif cmd_type == '/execute_payroll':
            status, msg = engine.bayar_gaji()

        # Respon teknis sukses
        response_text = f"✅ **STATUS DATABASE:**\n{msg}\n\nSilakan pilih langkah selanjutnya:"
        response_text += "\n[UI:Lihat Stok|Cek stok unit sekarang]"
        response_text += "\n[UI:Laporan Keuangan|Cek saldo kas]"
        response_text += "\n[UI:Cek Pasar|Cek harga pasar mobil lain]"

        return jsonify({
            "response": response_text,
            "system_msg": f"SYSTEM WRITE: {msg}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ System Error: {str(e)}", "system_msg": ""})

# --- API SEARCH MARKET ONLINE ---
@app.route('/api/search_market', methods=['POST'])
def search_market():
    """Endpoint manual untuk memicu scraping pasar dari frontend."""
    query = request.json.get('query', '').strip()
    force = request.json.get('force_refresh', False)
    
    if not query:
        return jsonify({"error": "Query tidak boleh kosong"}), 400
    
    result = engine.cari_pasar_online(query, force_refresh=force)
    return jsonify({
        "summary": result,
        "query": query
    })

# --- API DATABASE EXPLORER ---
def get_db_conn():
    from config import DB_FILE
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/db/tables')
def list_tables():
    conn = get_db_conn()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    conn.close()
    return jsonify([t['name'] for t in tables])

@app.route('/api/db/data/<table_name>')
def get_table_data(table_name):
    conn = get_db_conn()
    try:
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        data = [dict(r) for r in rows]
        # Get columns
        cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
        columns = [d[0] for d in cursor.description]
        return jsonify({"columns": columns, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

@app.route('/api/db/delete/<table_name>', methods=['POST'])
def delete_row(table_name):
    row_id = request.json.get('id')
    id_col = request.json.get('id_column', 'id')
    conn = get_db_conn()
    try:
        conn.execute(f"DELETE FROM {table_name} WHERE {id_col} = ?", (row_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

@app.route('/api/db/upsert/<table_name>', methods=['POST'])
def upsert_row(table_name):
    row_data = request.json.get('data')
    id_col = request.json.get('id_column', 'id')
    conn = get_db_conn()
    try:
        columns = list(row_data.keys())
        values = list(row_data.values())
        
        placeholders = ", ".join(["?"] * len(columns))
        update_placeholders = ", ".join([f"{col}=excluded.{col}" for col in columns if col != id_col])
        
        query = f"""
            INSERT INTO {table_name} ({", ".join(columns)}) 
            VALUES ({placeholders})
            ON CONFLICT({id_col}) DO UPDATE SET {update_placeholders}
        """
        conn.execute(query, values)
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Upsert Error: {e}")
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

@app.route('/api/db/reset', methods=['POST'])
def reset_db():
    try:
        engine.db.reset_database()
        return jsonify({"status": "success", "message": "Database berhasil direset ke default."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Memory Active: Saving last 15 turns.")
    app.run(debug=True, port=5000)