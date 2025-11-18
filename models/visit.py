# models/visit.py

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy import Text
from sqlalchemy.orm import relationship
from datetime import datetime

from core.database import Base

class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)

    # Link to patient
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    # Stroke event metadata
    visit_id = Column(String, unique=True, index=True, nullable=False)  # example: V00102
    timestamp = Column(DateTime, default=datetime.utcnow)
    # Time of stroke onset (if recorded) — used by tPA eligibility checks
    onset_time = Column(DateTime, nullable=True)

    # Workflow status and assignment
    status = Column(String, default="in_progress")
    doctor_username = Column(String, nullable=True)

    # Vitals at time of stroke
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    oxygen_saturation = Column(Integer, nullable=True)
    glucose = Column(Float, nullable=True)
    inr = Column(Float, nullable=True)
    platelet_count = Column(Integer, nullable=True)

    # NIHSS scoring
    nihss_score = Column(Integer, nullable=True)

    # tPA eligibility result
    tpa_eligible = Column(Boolean, nullable=True)
    tpa_reason = Column(String, nullable=True)

    # ML model prediction
    prediction_label = Column(String, nullable=True)
    prediction_confidence = Column(Float, nullable=True)

    # Scan image path
    scan_path = Column(String, nullable=True)

    # Doctor inputs
    icd_code = Column(String, nullable=True)
    treatment_plan = Column(String, nullable=True)  # doctor-written or AI-written plan
    finalized = Column(Boolean, default=False)
    technician_notes = Column(Text, nullable=True)

    # ORM relationships
    patient = relationship("Patient", backref="visits")

    def __repr__(self):
        return f"<Visit {self.visit_id} for Patient {self.patient_id}>"
