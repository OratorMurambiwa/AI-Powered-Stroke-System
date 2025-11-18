# models/patient.py

from sqlalchemy import Column, Integer, String, Date
from core.database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)

    # Short human-friendly patient identifier (P001, P002...)
    patient_id = Column(String, unique=True, index=True, nullable=False)

    # Demographics
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)

    # Optional stored info
    dob = Column(Date, nullable=True)  # not required, but available
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    def __repr__(self):
        return f"<Patient {self.patient_id} - {self.name}>"
