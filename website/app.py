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

@app.route('/api/chat/reset', methods=['POST'])
def reset_chat_history():
    global CHAT_HISTORY
    db.reset_chat_history()
    CHAT_HISTORY = []
    return jsonify({"status": "success"})

@app.route('/chat', methods=['POST'])
def chat():
    global CHAT_HISTORY
    
    user_input = request.json.get('message')
    if not user_input: return jsonify({"error": "No input"}), 400

    # --- JALUR EKSEKUSI LANGSUNG (WRITE DB VIA POP-UP) ---
    # Bypass history LLM untuk eksekusi teknis agar tidak mengotori konteks
    DIRECT_CMDS = ['/execute_', '/status', '/buy ', '/sell ', '/setprice ', '/move ', '/inspect ', '/reset_chat', '/help']
    if any(user_input.startswith(c) for c in DIRECT_CMDS):
        # Normalisasi shorthand -> execute prefix
        shorthand_map = {'/status': '/execute_status', '/buy ': '/execute_buy ', '/sell ': '/execute_sell ', '/setprice ': '/execute_setprice ', '/move ': '/execute_move ', '/inspect ': '/execute_inspect ', '/reset_chat': '/execute_reset_chat'}
        mapped = user_input
        for k, v in shorthand_map.items():
            if user_input.startswith(k):
                mapped = user_input.replace(k, v, 1)
                break
        return handle_direct_execution(mapped)

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
            if len(parts) < 2:
                return jsonify({"response": "⚠️ Format: `/setprice [ID] [HARGA]`", "system_msg": ""})
            status, msg = engine.set_harga_unit(parts[0], parts[1])
        
        elif cmd_type in ['/execute_sell', '/execute_sell_inventory']:
            parts = [p.strip() for p in args_str.split('|')] if '|' in args_str else args_str.split()
            if not parts or not parts[0]:
                return jsonify({"response": "⚠️ Format: `/sell [ID] [HARGA_DEAL]`", "system_msg": ""})
            harga_deal = parts[1] if len(parts) > 1 else "0"
            status, msg = engine.jual_mobil(parts[0], harga_deal)

        elif cmd_type in ['/execute_buy', '/execute_restock']:
            if '|' in args_str:
                buy_args = [a.strip() for a in args_str.split('|')]
                if len(buy_args) < 4:
                    return jsonify({"response": "⚠️ Format: `/buy MODEL|TAHUN|HARGA|KONDISI|PLAT`", "system_msg": ""})
                model, tahun, harga, kondisi = buy_args[0], buy_args[1], buy_args[2], buy_args[3]
                plat = buy_args[4] if len(buy_args) > 4 else None
                status, msg = engine.beli_mobil(model, tahun, harga, kondisi, plat)
            else:
                match = re.search(r'^(.*?)\s+(\d{4})\s+(\d+)\s+(.+)$', args_str)
                if match:
                    model, tahun, harga, kondisi = match.groups()
                    status, msg = engine.beli_mobil(model, tahun, harga, kondisi)
                else:
                    return jsonify({"response": "❌ Format: `/buy MODEL TAHUN HARGA KONDISI` atau pakai pipe `|`", "system_msg": ""})

        elif cmd_type == '/execute_move':
            if not args_str:
                return jsonify({"response": "⚠️ Format: `/move [KOTA]`", "system_msg": ""})
            status, msg = engine.pindah_lokasi(args_str.strip())

        elif cmd_type == '/execute_status':
            ctx = engine.get_context_string()
            return jsonify({"response": f"📊 **Status Real-Time Firzanta Motor:**\n\n{ctx}", "system_msg": ""})

        elif cmd_type == '/execute_inspect':
            if not args_str:
                return jsonify({"response": "⚠️ Format: `/inspect [ID_UNIT]`\nContoh: `/inspect UNIT-001`", "system_msg": ""})
            result = engine.inspect_unit(args_str.strip())
            return jsonify({"response": result, "system_msg": ""})

        elif cmd_type == '/execute_reset_chat':
            db.reset_chat_history()
            global CHAT_HISTORY
            CHAT_HISTORY = []
            return jsonify({"response": "🧹 Riwayat percakapan berhasil dibersihkan.", "system_msg": ""})

        elif cmd_type == '/execute_payroll':
            status, msg = engine.bayar_gaji()

        elif cmd_type == '/help':
            help_text = """
📌 **DAFTAR PERINTAH FIRZANTA MOTOR**

| Perintah | Fungsi |
|---|---|
| `/status` | Cek saldo, stok, kondisi real-time |
| `/buy MODEL\|TAHUN\|HARGA\|KONDISI\|PLAT` | Beli unit baru |
| `/sell ID [HARGA_DEAL]` | Jual unit dari stok |
| `/setprice ID HARGA` | Atur harga jual iklan |
| `/move KOTA` | Pindah lokasi showroom |
| `/inspect ID` | Cek detail kondisi unit |
| `/reset_chat` | Bersihkan riwayat percakapan |
| `/help` | Tampilkan daftar perintah ini |
"""
            return jsonify({"response": help_text, "system_msg": ""})

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
    id_col = request.json.get('id_col', 'id')
    conn = get_db_conn()
    try:
        conn.execute(f"DELETE FROM {table_name} WHERE {id_col} = ?", (row_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

@app.route('/api/db/add/<table_name>', methods=['POST'])
def add_row(table_name):
    row_data = request.json
    conn = get_db_conn()
    try:
        cols = ", ".join(row_data.keys())
        placeholders = ", ".join(["?"] * len(row_data))
        conn.execute(f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})", list(row_data.values()))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

@app.route('/api/db/edit/<table_name>', methods=['POST'])
def edit_row(table_name):
    row_data = request.json
    # Asumsikan kolom pertama adalah primary key (id)
    conn = get_db_conn()
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
        id_col = cursor.description[0][0] # Ambil PK (biasanya 'id')
        row_id = row_data.get(id_col)
        
        # Konversi ke int jika kolomnya adalah 'id'
        if id_col.lower() == 'id':
            try: row_id = int(row_id)
            except: pass
        
        cols = [f"{k} = ?" for k in row_data.keys() if k != id_col]
        vals = [v for k, v in row_data.items() if k != id_col]
        vals.append(row_id)
        
        query = f"UPDATE {table_name} SET {', '.join(cols)} WHERE {id_col} = ?"
        conn.execute(query, vals)
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
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