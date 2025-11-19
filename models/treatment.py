from sqlalchemy import Column, Integer, String, ForeignKey
from core.database import Base

class Treatment(Base):
    __tablename__ = "treatments"

    id = Column(Integer, primary_key=True)
    visit_id = Column(Integer, ForeignKey("visits.id"))
    plan_text = Column(String)
    # Explicit linkage for safety and filtering
    patient_code = Column(String, index=True, nullable=True)  # e.g., P001
    patient_name = Column(String, nullable=True)

