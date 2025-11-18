from sqlalchemy import Column, Integer, String
from core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=False)   # FIXED

    role = Column(String, nullable=False)

    full_name = Column(String, nullable=True)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
