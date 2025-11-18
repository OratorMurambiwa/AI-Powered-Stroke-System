import streamlit as st
from core.session_manager import require_role
from core.database import get_db
from sqlalchemy.orm import Session
from models.visit import Visit
from models.patient import Patient


def get_waiting_visits(doctor_username: str, db: Session):
    return (
        db.query(Visit)
        .filter(Visit.doctor_username == doctor_username)
        .filter(Visit.status == "sent_to_doctor")
        .order_by(Visit.id.desc())
        .all()
    )


def main():
    require_role("doctor")

    st.title("Patient Queue")
    st.write("Cases waiting for your review.")

    db = next(get_db())
    doctor = st.session_state["user"]

    visits = get_waiting_visits(doctor["username"], db)

    if not visits:
        st.info("No cases waiting right now.")
        return

    for v in visits:
        p = db.query(Patient).filter(Patient.id == v.patient_id).first()

        with st.container():
            st.write(f"### {p.name} ({p.patient_id})")
            st.write(f"- Age: {p.age}")
            st.write(f"- Gender: {p.gender}")
            st.write(f"- Visit ID: {v.id}")

            if st.button(f"Open Case #{v.id}", key=f"open_{v.id}"):
                st.session_state["open_visit_id"] = v.id
                st.switch_page("pages/d_view_case.py")

    if st.button("Back to Dashboard"):
        st.switch_page("pages/d_dashboard.py")


if __name__ == "__main__":
    main()
