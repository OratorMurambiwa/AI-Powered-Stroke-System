"""Migration: Convert legacy SHA-256 user password hashes to bcrypt.

This script detects users whose stored hashes look like 64 hex chars (sha256) and
re-hashes them with bcrypt using a temporary default password (or prompts).

IMPORTANT: Because SHA-256 is one-way and we cannot recover the original raw
password, this script assigns a TEMP password for affected users.

Default temp password: TempPass123!
Change it after login.
"""
import os
import re
from getpass import getpass
from core.database import get_db_session, DB_PATH
from models.user import User
from core.auth import hash_password as bcrypt_hash

LEGACY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
TEMP_PASSWORD = os.getenv("MIGRATION_TEMP_PASSWORD", "TempPass123!")


def main():
    print(f"Database: {DB_PATH}")
    session = get_db_session()
    try:
        users = session.query(User).all()
        migrated = 0
        for u in users:
            if u.password_hash and LEGACY_PATTERN.fullmatch(u.password_hash):
                # Detected legacy sha256
                u.password_hash = bcrypt_hash(TEMP_PASSWORD)
                migrated += 1
        if migrated:
            session.commit()
            print(f"Migrated {migrated} user(s) to bcrypt. TEMP password => {TEMP_PASSWORD}")
        else:
            print("No legacy SHA-256 hashes detected.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
