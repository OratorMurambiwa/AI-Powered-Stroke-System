import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

# Path: project_root/data/stroke.db
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "stroke.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db():
    """
    Generator function used with FastAPI-style dependencies.
    Not used by Streamlit, but we keep it for compatibility.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    """
    Streamlit version — returns a raw session.
    All Streamlit pages will call this.
    """
    return SessionLocal()


# Streamlit helper - returns a real session
def get_db_session():
    db = SessionLocal()
    return db


@contextmanager
def get_db_context():
    """
    Context manager for database sessions.
    Automatically closes session when done.
    
    Usage:
        with get_db_context() as db:
            result = db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()