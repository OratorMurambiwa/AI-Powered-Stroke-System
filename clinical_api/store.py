from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import os
import sqlite3
from .errors import ClinicalError
from .validation import uuid_id, text

def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")

class LinkStore:
    def __init__(self, path: Path, source_id: str, version: int = 1):
        if type(version) is not int or version not in {1, 2, 3, 4}:
            raise ValueError("Explicit supported store version required")
        self.version = version
        self.path = Path(path).resolve()
        self.source_id = uuid_id(source_id)

    def initialize(self) -> None:
        # Explicit operator-only creation; never initialize/migrate an existing file.
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(self.path)
        try:
            db.executescript(Path(__file__).with_name("schema.sql" if self.version == 1 else f"schema-v{self.version}.sql").read_text())
            db.execute("INSERT INTO metadata VALUES(?,?)", (self.version, self.source_id))
            db.commit()
        finally:
            db.close()

    @contextmanager
    def connection(self, write: bool = False):
        db = None
        try:
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=0.5)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            if not write:
                db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            metadata = db.execute("SELECT version,source_id FROM metadata").fetchall()
            if len(metadata) != 1 or metadata[0]["version"] != self.version or metadata[0]["source_id"] != self.source_id:
                raise ClinicalError(503, "mapping_store_mismatch")
            yield db
            db.commit()
        except sqlite3.IntegrityError:
            raise ClinicalError(409, "mapping_conflict") from None
        except sqlite3.Error:
            raise ClinicalError(503, "mapping_store_unavailable") from None
        finally:
            if db is not None:
                db.close()  # Uncommitted operations roll back on every failure.

    @staticmethod
    def audit(db: sqlite3.Connection, action: str, object_id: str, operator: str, reason: str) -> None:
        db.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)", (
            str(uuid4()), timestamp(), text(operator, 120), text(reason, 500), action, object_id))
