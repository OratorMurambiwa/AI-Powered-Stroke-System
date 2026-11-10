from pathlib import Path
import sqlite3
from uuid import uuid4

def create_records(path: Path, source_id: str) -> None:
    """Create fresh synthetic tables matching only the legacy fields read by the bridge."""
    db = sqlite3.connect(path)
    try:
        db.executescript('''
        CREATE TABLE clinical_source_metadata(source_id TEXT NOT NULL, synthetic INTEGER NOT NULL, schema_version INTEGER NOT NULL);
        CREATE TABLE clinical_record_ids(kind TEXT NOT NULL, native_id INTEGER NOT NULL, record_uuid TEXT NOT NULL UNIQUE, PRIMARY KEY(kind,native_id));
        CREATE TABLE patients(id INTEGER PRIMARY KEY, patient_id TEXT, name TEXT, age INTEGER, gender TEXT);
        CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, role TEXT);
        CREATE TABLE visits(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), timestamp TEXT,
          status TEXT, systolic_bp INTEGER, diastolic_bp INTEGER, heart_rate INTEGER, nihss_score INTEGER,
          scan_path TEXT, treatment_plan TEXT);
        ''')
        db.execute('INSERT INTO clinical_source_metadata VALUES(?,1,1)', (source_id,))
        db.executemany('INSERT INTO patients VALUES(?,?,?,?,?)', [(1, 'P001', 'Synthetic Patient A', 50, 'Synthetic'), (2, 'P002', 'Synthetic Patient B', 60, 'Synthetic')])
        db.executemany('INSERT INTO users VALUES(?,?,?)', [(1, 'synthetic-doc', 'physician'), (2, 'synthetic-tech', 'technician'), (3, 'synthetic-other-doc', 'doctor')])
        db.executemany('INSERT INTO visits VALUES(?,?,?,?,?,?,?,?,?,?)', [
            (1, 1, '2099-01-01T00:00:00Z', 'in_progress', 120, 80, 70, None, 'never-read-scan', 'never-read-treatment'),
            (2, 2, '2099-01-01T00:00:00Z', 'in_progress', 120, 80, 70, None, 'never-read-scan', 'never-read-treatment'),
            (3, 1, '2099-01-02T00:00:00Z', 'in_progress', 120, 80, 70, None, 'never-read-scan', 'never-read-treatment'),
        ])
        db.executemany('INSERT INTO clinical_record_ids VALUES(?,?,?)', [(kind, native_id, str(uuid4())) for kind, ids in [('patient', [1, 2]), ('staff', [1, 2, 3]), ('encounter', [1, 2, 3])] for native_id in ids])
        db.commit()
    finally:
        db.close()
