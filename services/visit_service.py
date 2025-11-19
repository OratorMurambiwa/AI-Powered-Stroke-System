from sqlalchemy.orm import Session
from core.database import get_db
from models.visit import Visit
from models.patient import Patient


# -----------------------------
# Create a new visit
# -----------------------------
def create_visit(patient_id: int | str | None, db: Session = None):
    if db is None:
        db = next(get_db())
    # Accept either numeric patient PK, patient code (e.g., P001), or Patient object
    if isinstance(patient_id, str):
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not patient:
            return None
        patient_pk = patient.id
    elif hasattr(patient_id, "id") and isinstance(getattr(patient_id, "id"), int):
        patient_pk = patient_id.id
    else:
        patient_pk = patient_id

    # Generate per-patient sequential visit code: <PatientCode>-V### (e.g., P003-V001)
    # Display will show only the V### portion.
    patient_obj = db.query(Patient).filter(Patient.id == patient_pk).first()
    existing_count = db.query(Visit).filter(Visit.patient_id == patient_pk).count()
    seq = existing_count + 1
    visit_code = f"{patient_obj.patient_id}-V{seq:03d}"

    visit = Visit(patient_id=patient_pk, visit_id=visit_code, status="in_progress")
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


# -----------------------------
# Get visit by ID
# -----------------------------
def get_visit_by_id(visit_id: int, db: Session = None):
    if db is None:
        db = next(get_db())

    return db.query(Visit).filter(Visit.id == visit_id).first()


# -----------------------------
# Get all visits for a patient
# -----------------------------
def get_visits_for_patient(patient_id: int, db: Session = None):
    if db is None:
        db = next(get_db())

    return db.query(Visit).filter(Visit.patient_id == patient_id).all()


# -----------------------------
# Update visit attributes
# -----------------------------
def update_visit(visit_id: int, db: Session = None, **kwargs):
    if db is None:
        db = next(get_db())

    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        return None
    
    for key, value in kwargs.items():
        if hasattr(visit, key):
            setattr(visit, key, value)

    db.commit()
    db.refresh(visit)
    return visit


# -----------------------------
# Assign doctor to a visit
# -----------------------------
def assign_doctor(visit_id: int, doctor_username: str, db: Session = None):
    if db is None:
        db = next(get_db())

    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        return None

    visit.doctor_username = doctor_username
    visit.status = "sent_to_doctor"

    db.commit()
    db.refresh(visit)
    return visit
