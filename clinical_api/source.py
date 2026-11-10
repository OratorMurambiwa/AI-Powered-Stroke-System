from contextlib import contextmanager
from pathlib import Path
import sqlite3
from .errors import ClinicalError
from .validation import uuid_id, integer

class ClinicalSource:
    """Read-only, explicitly marked synthetic source. No legacy initializer/import."""
    def __init__(self, path: Path, source_id: str):
        self.path = Path(path).resolve()
        self.source_id = uuid_id(source_id)

    @contextmanager
    def connection(self):
        connection = None
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0.5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            row = connection.execute("SELECT source_id, synthetic, schema_version FROM clinical_source_metadata").fetchall()
            if len(row) != 1 or row[0]["source_id"] != self.source_id or row[0]["synthetic"] != 1 or row[0]["schema_version"] != 1:
                raise ClinicalError(503, "source_identity_mismatch")
            yield connection
        except sqlite3.Error:
            raise ClinicalError(503, "clinical_source_unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def record_uuid(db, kind: str, native_id: int) -> str:
        row = db.execute("SELECT record_uuid FROM clinical_record_ids WHERE kind=? AND native_id=?", (kind, native_id)).fetchone()
        if not row:
            raise ClinicalError(503, "record_identity_unavailable")
        try:
            return uuid_id(row["record_uuid"])
        except ClinicalError:
            raise ClinicalError(503, "record_identity_unavailable") from None

    def check_person(self, role: str, native_id: int) -> str:
        integer(native_id, 1)
        with self.connection() as db:
            if role == "patient":
                row = db.execute("SELECT id FROM patients WHERE id=?", (native_id,)).fetchone()
            else:
                row = db.execute("SELECT role FROM users WHERE id=?", (native_id,)).fetchone()
                if row and ("doctor" if row["role"] == "physician" else row["role"]) != role:
                    raise ClinicalError(409, "clinical_role_mismatch")
            if not row:
                raise ClinicalError(404, "clinical_record_not_found")
            return self.record_uuid(db, "patient" if role == "patient" else "staff", native_id)

    def check_encounter(self, native_id: int, patient_native_id: int) -> str:
        integer(native_id, 1)
        with self.connection() as db:
            row = db.execute("SELECT patient_id FROM visits WHERE id=?", (native_id,)).fetchone()
            if not row or row["patient_id"] != patient_native_id:
                raise ClinicalError(409, "encounter_patient_mismatch")
            return self.record_uuid(db, "encounter", native_id)

    def patient(self, native_id: int, expected_uuid: str) -> dict:
        with self.connection() as db:
            if self.record_uuid(db, "patient", native_id) != expected_uuid:
                raise ClinicalError(503, "record_identity_mismatch")
            row = db.execute("SELECT name, age, gender FROM patients WHERE id=?", (native_id,)).fetchone()
            if not row:
                raise ClinicalError(503, "clinical_record_unavailable")
            return dict(row)

    def encounter(self, native_id: int, patient_native_id: int, expected_uuid: str, expected_patient_uuid: str) -> dict:
        with self.connection() as db:
            if self.record_uuid(db, "encounter", native_id) != expected_uuid or self.record_uuid(db, "patient", patient_native_id) != expected_patient_uuid:
                raise ClinicalError(503, "record_identity_mismatch")
            row = db.execute("SELECT patient_id, timestamp, status, systolic_bp, diastolic_bp, heart_rate, nihss_score FROM visits WHERE id=?", (native_id,)).fetchone()
            if not row or row["patient_id"] != patient_native_id:
                raise ClinicalError(503, "clinical_record_unavailable")
            result = dict(row)
            result.pop("patient_id")
            return result
