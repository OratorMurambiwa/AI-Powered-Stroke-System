# core/setup_db.py

from core.database import Base, engine, get_db_session
from services.user_service import ensure_default_users

def main():
    print("Creating database tables...")

    # Create all SQLAlchemy tables
    Base.metadata.create_all(bind=engine)

    # Insert demo users
    ensure_default_users()

    print("Database initialized successfully.")

if __name__ == "__main__":
    main()
