from sqlalchemy.orm import Session
from models.patient import Patient
from models.visit import Visit
from core.time_utils import now_utc
from core.database import get_db_context


# ------------------------------------------
# Generate 4-digit patient IDs like P001, P002
# ------------------------------------------
def generate_patient_code(db: Session):
    latest = (
        db.query(Patient)
        .order_by(Patient.id.desc())
        .first()
    )
    
    if not latest:
        return "P001"

    next_num = latest.id + 1
    return f"P{next_num:03d}"


# ------------------------------------------
# Convenience: expose next patient id for UIs
# ------------------------------------------
def get_next_patient_id(db: Session = None):
    """Return the next sequential patient code (e.g., P001, P002).

    If a session isn't provided, opens a short-lived DB context.
    """
    if db is None:
        with get_db_context() as _db:
            return generate_patient_code(_db)
    return generate_patient_code(db)


# ------------------------------------------
# Create a new patient
# ------------------------------------------
def create_patient(db: Session, name: str, age: int, gender: str):
    patient_id = generate_patient_code(db)

    patient = Patient(
        patient_id=patient_id,
        name=name,
        age=age,
        gender=gender
    )

    db.add(patient)
    db.commit()
    db.refresh(patient)

    return patient


# ------------------------------------------
# Fetch ALL patients
# ------------------------------------------


def get_all_patients(db: Session):
    return db.query(Patient).all()


# ------------------------------------------
# Fetch patient by code
# ------------------------------------------
def get_patient(db: Session, patient_id: str):
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()


# ------------------------------------------
# Create a NEW stroke visit
# ------------------------------------------
def create_visit(db: Session, patient_id: str):
    patient = get_patient(db, patient_id)

    if not patient:
        return None, "Patient not found"

    visit = Visit(
        patient_id=patient.id,
        timestamp=now_utc()
    )

    db.add(visit)
    db.commit()
    db.refresh(visit)

    return visit, None


# ------------------------------------------
# Update vitals for a visit
# ------------------------------------------
def update_vitals(
    db: Session,
    visit_id: int,
    systolic_bp: int,
    diastolic_bp: int,
    heart_rate: int,
    temperature: float,
    oxygen_saturation: int,
    glucose: int,
    inr: float
):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        return None, "Visit not found"

    visit.systolic_bp = systolic_bp
    visit.diastolic_bp = diastolic_bp
    visit.heart_rate = heart_rate
    visit.temperature = temperature
    visit.oxygen_saturation = oxygen_saturation
    visit.glucose = glucose
    visit.inr = inr

    db.commit()
    db.refresh(visit)

    return visit, None


# ------------------------------------------
# Get all visits for a patient
# ------------------------------------------
def get_patient_history(db: Session, patient_id: str):
    patient = get_patient(db, patient_id)
    if not patient:
        return None

    return (
        db.query(Visit)
        .filter(Visit.patient_id == patient.id)
        .order_by(Visit.created_at.desc())
        .all()
    )


# ------------------------------------------
# Get a single visit by ID
# ------------------------------------------
def get_visit(db: Session, visit_id: int):
    return db.query(Visit).filter(Visit.id == visit_id).first()


# -----------------------------
# Convenience functions (no-db parameter)
# -----------------------------
def list_patients(db: Session = None):
    if db is None:
        with get_db_context() as db:
            return db.query(Patient).all()
    return db.query(Patient).all()


def get_patient_by_id(patient_id: str, db: Session = None):
    if db is None:
        with get_db_context() as db:
            return db.query(Patient).filter(Patient.patient_id == patient_id).first()
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()


# ------------------------------------------
# Update patient basic info
# ------------------------------------------
def update_patient(patient_code: str, *, name: str | None = None, age: int | None = None, gender: str | None = None, db: Session | None = None):
    if db is None:
        with get_db_context() as _db:
            return update_patient(patient_code, name=name, age=age, gender=gender, db=_db)

    patient = db.query(Patient).filter(Patient.patient_id == patient_code).first()
    if not patient:
        return None

    if name is not None:
        patient.name = name
    if age is not None:
        patient.age = age
    if gender is not None:
        patient.gender = gender

    db.commit()
    db.refresh(patient)
    return patient


# ------------------------------------------
# Delete a single visit
# ------------------------------------------
def delete_visit(visit_id: int, db: Session | None = None) -> bool:
    if db is None:
        with get_db_context() as _db:
            return delete_visit(visit_id, db=_db)

    v = db.query(Visit).filter(Visit.id == visit_id).first()
    if not v:
        return False
    db.delete(v)
    db.commit()
    return True


# ------------------------------------------
# Delete a patient and their visits
# ------------------------------------------
def delete_patient(patient_code: str, db: Session | None = None) -> bool:
    if db is None:
        with get_db_context() as _db:
            return delete_patient(patient_code, db=_db)

    patient = db.query(Patient).filter(Patient.patient_id == patient_code).first()
    if not patient:
        return False

    # Delete all visits first to avoid FK constraint issues
    db.query(Visit).filter(Visit.patient_id == patient.id).delete()
    db.delete(patient)
    db.commit()
    return True
