from sqlalchemy import Column, Integer, String, ForeignKey
from core.database import Base

class Treatment(Base):
    __tablename__ = "treatments"

    id = Column(Integer, primary_key=True)
    visit_id = Column(Integer, ForeignKey("visits.id"))
    plan_text = Column(String)

