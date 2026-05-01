import sys
import os

# --- PATH CONFIGURATION ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
code_dir = os.path.join(parent_dir, 'code')
sys.path.append(code_dir)

from database import DatabaseManager

db = DatabaseManager()
# Ini akan memicu sinkronisasi otomatis
state = db.load_gamestate()

print("--- GAMESTATE (SYNCED) ---")
print(f"Showroom: {state['showroom_name']}")
print(f"Lokasi: {state['lokasi']}")
print(f"Luas Tanah: {state['luas_tanah']} m2")
print(f"Luas Display: {state['luas_display']} m2")
print(f"Luas Kantor: {state['luas_kantor']} m2")
print(f"Kapasitas: {state['kapasitas']} unit")

print("\n--- ASET ---")
for aset in db._get_connection().execute("SELECT * FROM aset").fetchall():
    print(dict(aset))
