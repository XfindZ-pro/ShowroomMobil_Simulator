import sqlite3
import os

db_path = r"d:\coding v2\Firzanta Motor\code\data\firzanta_motor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("TABLES:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
for t in cursor.fetchall():
    print(f"- {t[0]}")

print("\nGAMESTATE:")
cursor.execute("SELECT * FROM gamestate")
print(cursor.fetchone())

print("\nKEUANGAN:")
cursor.execute("SELECT * FROM keuangan")
print(cursor.fetchone())

print("\nINVENTORY COUNT:")
cursor.execute("SELECT count(*) FROM inventory")
print(cursor.fetchone()[0])

conn.close()
