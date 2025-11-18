import sqlite3
import os

# Resolve DB path relative to repo root
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, 'data', 'stroke.db')

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("PRAGMA table_info('visits')")
cols = [r[1] for r in c.fetchall()]
print("Existing columns:", cols)

if 'onset_time' not in cols:
    c.execute("ALTER TABLE visits ADD COLUMN onset_time DATETIME")
    print("Added 'onset_time' column to 'visits'.")
else:
    print("'onset_time' already exists.")

conn.commit()
conn.close()
print("Migration complete.")
