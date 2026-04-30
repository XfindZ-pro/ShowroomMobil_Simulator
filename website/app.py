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
    CHAT_HISTORY = db.load_chat_history(30)
except Exception as e:
    print(f"CRITICAL ERROR: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat/history')
def get_chat_history():
    return jsonify(db.load_chat_history(30))

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
    
    === INFORMASI WAKTU ===
    Sekarang: **{waktu_skrg}** (Tahun **2026**)
    
    === ATURAN MUTLAK (ANTI-HALUSINASI) ===
    1. **DATA REAL-TIME ADALAH KEBENARAN TERTINGGI:** Abaikan pesan-pesan sebelumnya di history jika mereka menyebutkan stok mobil atau saldo yang BERBEDA dengan section "=== DATA REAL-TIME ===" di bawah ini.
    2. **JANGAN PERCAYA HISTORY UNTUK STOK:** Jika history bilang kamu baru beli mobil tapi di "LIST UNIT (GARASI)" tertulis "(Garasi Kosong)", maka mobil itu TIDAK ADA. Jangan menampilkannya.
    3. **SISA KAS:** Hanya gunakan angka dari DATA REAL-TIME.
    4. **RIWAYAT TRANSAKSI:** Jika LOG kosong, jangan mengarang riwayat penjualan.
    
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
    db.save_chat_message('user', user_input)
    db.save_chat_message('assistant', ai_reply)
    CHAT_HISTORY = db.load_chat_history(30)

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
    try:
        # Normalisasi perintah (bisa dipisah spasi atau pipe)
        cmd_raw = command.strip()
        if ' ' in cmd_raw:
            cmd_type = cmd_raw.split(' ')[0]
        elif '|' in cmd_raw:
            cmd_type = cmd_raw.split('|')[0]
        else:
            cmd_type = cmd_raw

        args_str = cmd_raw[len(cmd_type):].strip()
        if args_str.startswith('|'): args_str = args_str[1:].strip()
        
        msg = f"Command '{cmd_type}' not recognized"
        status = False

        if cmd_type in ['/execute_setprice', '/execute_set_price']:
            parts = [p.strip() for p in args_str.split('|')] if '|' in args_str else args_str.split()
            if len(parts) < 2: return jsonify({"response": "⚠️ Format salah. Butuh ID dan Harga.", "system_msg": ""})
            status, msg = engine.set_harga_unit(parts[0], parts[1])
        
        elif cmd_type in ['/execute_sell', '/execute_sell_inventory']:
            parts = [p.strip() for p in args_str.split('|')] if '|' in args_str else args_str.split()
            if len(parts) < 1: return jsonify({"response": "⚠️ Format salah. Butuh ID unit.", "system_msg": ""})
            # Jika harga tidak ada, kirim 0 agar engine fallback ke harga_jual di DB
            harga_deal = parts[1] if len(parts) > 1 else "0"
            status, msg = engine.jual_mobil(parts[0], harga_deal)
            
        elif cmd_type in ['/execute_buy', '/execute_restock']:
            # Coba parsing dengan pipe (|) jika format baru
            if '|' in args_str:
                buy_args = [a.strip() for a in args_str.split('|')]
                model = buy_args[0]
                tahun = buy_args[1]
                harga = buy_args[2]
                kondisi = buy_args[3]
                plat = buy_args[4] if len(buy_args) > 4 else None
                status, msg = engine.beli_mobil(model, tahun, harga, kondisi, plat)
            else:
                # Regex parsing untuk format lama: "Model Spasi Tahun Harga Spasi Kondisi"
                import re
                match = re.search(r'^(.*?)\s+(\d{4})\s+(\d+)\s+(.+)$', args_str)
                if match:
                    model, tahun, harga, kondisi = match.groups()
                else:
                    # Fallback list based
                    p = [p.strip() for p in args_str.split() if p.strip()]
                    if len(p) >= 3:
                        kondisi, harga, tahun = p[-1], p[-2], p[-3]
                        model = " ".join(p[:-3])
                    else:
                        return jsonify({"response": "❌ Format /execute_buy tidak dikenal", "system_msg": ""})
                
                status, msg = engine.beli_mobil(model, tahun, harga, kondisi)
            
        elif cmd_type == '/execute_payroll':
            status, msg = engine.bayar_gaji()

        # Respon sukses/gagal dari engine
        icon = "✅" if status else "⚠️"
        response_text = f"{icon} **STATUS DATABASE:**\n{msg}\n\nSilakan pilih langkah selanjutnya:"
        response_text += "\n[UI:Lihat Stok|Cek stok unit sekarang]"
        response_text += "\n[UI:Laporan Keuangan|Cek saldo kas]"

        return jsonify({
            "response": response_text,
            "system_msg": f"SYSTEM WRITE: {msg}"
        })

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"ERROR EXECUTION: {error_detail}")
        return jsonify({
            "response": f"❌ Error Eksekusi: {str(e)}", 
            "system_msg": f"SYSTEM ERROR: {str(e)}"
        })

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
        engine.db.clear_chat_history()
        global CHAT_HISTORY
        CHAT_HISTORY = []
        return jsonify({"status": "success", "message": "Database & Chat berhasil direset."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Memory Active: Saving last 15 turns.")
    app.run(debug=True, port=5000)