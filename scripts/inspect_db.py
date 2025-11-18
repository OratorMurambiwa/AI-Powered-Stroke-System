import sqlite3, os, json
ROOT = os.path.dirname(os.path.dirname(__file__))
DB = os.path.join(ROOT, 'data', 'stroke.db')
print('DB:', DB, 'exists:', os.path.exists(DB))
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("PRAGMA table_info('visits')")
cols = [r[1] for r in cur.fetchall()]
print('visits cols:', cols)
cur.execute("SELECT id, visit_id, doctor_username, status, systolic_bp, diastolic_bp, heart_rate, respiratory_rate, temperature, oxygen_saturation, glucose, inr, nihss_score, prediction_label, prediction_confidence, tpa_eligible FROM visits ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()
for r in rows:
    print(r)
con.close()
