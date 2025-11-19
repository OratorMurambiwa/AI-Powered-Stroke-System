# scripts/migrate_treatment_patient_fields.py

import sqlite3
import os

# Locate DB path relative to project root
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "stroke.db")


def column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    return column in cols


essential_alters = [
    ("patient_code", "TEXT"),
    ("patient_name", "TEXT"),
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # 1) Add columns if missing
        for col, typ in essential_alters:
            if not column_exists(conn, "treatments", col):
                print(f"Adding column {col} to treatments...")
                conn.execute(f"ALTER TABLE treatments ADD COLUMN {col} {typ}")
                conn.commit()

        # 2) Populate from joins where missing
        # Map: treatments.visit_id -> visits.patient_id -> patients.(patient_id,name)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id, p.patient_id, p.name
            FROM treatments t
            JOIN visits v ON t.visit_id = v.id
            JOIN patients p ON v.patient_id = p.id
            WHERE t.patient_code IS NULL OR t.patient_name IS NULL
            """
        )
        rows = cur.fetchall()
        if rows:
            print(f"Populating patient_code/name for {len(rows)} treatments...")
            for tid, code, name in rows:
                cur.execute(
                    "UPDATE treatments SET patient_code = ?, patient_name = ? WHERE id = ?",
                    (code, name, tid),
                )
            conn.commit()
        else:
            print("No treatments required population.")
        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
