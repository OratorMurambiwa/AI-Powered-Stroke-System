from core.database import get_db_session, get_db_context
from models import User
from models.patient import Patient
from core.helpers import hash_password  # legacy sha256
from core.auth import verify_password, hash_password as bcrypt_hash
import streamlit as st


def authenticate_user(username: str, password: str, role: str):
    """Authenticate user by username, password, and required role.

    Supports legacy SHA-256 hashes (stored using core.helpers.hash_password) and new
    bcrypt hashes (stored using core.auth.hash_password). New accounts will use bcrypt.
    """
    with get_db_context() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None

        stored = user.password_hash or ""
        # Attempt bcrypt verify first; if it fails, fall back to legacy sha256 compare.
        password_ok = False
        try:
            if verify_password(password, stored):
                password_ok = True
        except Exception:
            pass
        if not password_ok:
            # legacy path
            if stored == hash_password(password):
                password_ok = True
        if not password_ok:
            return None

        required = (role or "").strip().lower()
        user_role = (user.role or "").strip().lower()
        allowed = {"doctor", "physician"} if required in {"doctor", "physician"} else {required}
        if user_role not in allowed:
            return None
        return user


def ensure_default_users():
    """
    Creates default demo users on fresh database.
    """
    with get_db_context() as db:
        # If any users already exist, skip
        if db.query(User).first():
            return

        # Create demo users
        users = [
            User(username="tech1", role="technician", password_hash=bcrypt_hash("pass123")),
            User(username="doc1", role="physician", password_hash=bcrypt_hash("pass123")),
            User(username="patient1", role="patient", password_hash=bcrypt_hash("pass123")),
        ]

        db.add_all(users)
        db.commit()
        print("Default demo users created.")


def get_doctor_list():
    """Return all users with a doctor role (physician/doctor)."""
    with get_db_context() as db:
        return (
            db.query(User)
            .filter(User.role.in_(["physician", "doctor"]))
            .all()
        )


def create_user(role: str, username: str, password: str, *, patient_code: str | None = None, full_name: str | None = None):
    """Create a new user.

    - role: one of 'technician', 'physician', 'patient'
    - username: unique username; for patients, this should be the patient code (e.g., P001)
    - password: raw password, will be hashed
    - patient_code: required when role='patient'; must refer to an existing Patient.patient_id
    - full_name: optional display name
    """
    role = (role or "").strip().lower()
    if role not in {"technician", "physician", "patient"}:
        raise ValueError("Invalid role. Expected technician, physician, or patient.")

    username = (username or "").strip()
    if not username:
        raise ValueError("Username cannot be empty.")

    if role == "patient":
        # For patients, enforce username matches provided patient code and that the patient exists
        code = (patient_code or username).strip().upper()
        if not code:
            raise ValueError("Patient code is required for patient sign up.")
        import re
        if not re.fullmatch(r"P\d{3}", code):
            raise ValueError("Patient code must be in the format P followed by three digits (e.g., P003).")

        with get_db_context() as db:
            # patient must exist
            patient = db.query(Patient).filter(Patient.patient_id == code).first()
            if not patient:
                raise ValueError("Patient code not found. Please register the patient first.")
            # username must be unique
            if db.query(User).filter(User.username == code).first():
                raise ValueError("A user with this patient code already exists.")

            user = User(username=code, role="patient", password_hash=bcrypt_hash(password), full_name=full_name)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    # Technician / Physician
    with get_db_context() as db:
        if db.query(User).filter(User.username == username).first():
            raise ValueError("Username already exists.")

        user = User(username=username, role=role, password_hash=bcrypt_hash(password), full_name=full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def get_current_user():
    """Return the currently logged-in user from Streamlit session state.

    This mirrors usage in pages that import from services.user_service.
    """
    return getattr(st.session_state, "user", None)