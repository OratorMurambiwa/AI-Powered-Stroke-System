import sqlite3
import os

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, 'data', 'stroke.db')

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("PRAGMA table_info('visits')")
cols = [r[1] for r in c.fetchall()]
print("Existing columns:", cols)

if 'technician_notes' not in cols:
    c.execute("ALTER TABLE visits ADD COLUMN technician_notes TEXT")
    print("Added 'technician_notes' column to 'visits'.")
else:
    print("'technician_notes' already exists.")

conn.commit()
conn.close()
print("Migration complete.")
