import streamlit as st
from services.user_service import get_current_user
from services.visit_service import get_visits_for_patient
from core.session_manager import require_role
from sqlalchemy.orm import Session
from core.database import get_db
from models.visit import Visit
from models.patient import Patient
from core.helpers import render_doctor_sidebar


def get_doctor_visits(doctor_username: str, db: Session):
    """Fetch all visits assigned to the logged-in doctor."""
    return (
        db.query(Visit)
        .join(Patient, Visit.patient_id == Patient.id)
        .filter(Visit.doctor_username == doctor_username)
        .filter(Visit.status.in_(["sent_to_doctor", "in_review", "completed"]))
        .order_by(Visit.id.desc())
        .all()
    )


# ----------------------------------------------
# MAIN PAGE
# ----------------------------------------------
def main():
    require_role("doctor")  # Protect page (redirects if wrong role)

    render_doctor_sidebar()
    st.title("Doctor Dashboard")
    st.write("Review cases assigned to you.")

    db = next(get_db())
    doctor = get_current_user()

    # Fetch visit queue
    visits = get_doctor_visits(doctor_username=doctor.username, db=db)

    # Summary numbers
    sent = len([v for v in visits if v.status == "sent_to_doctor"])
    reviewing = len([v for v in visits if v.status == "in_review"])
    done = len([v for v in visits if v.status == "completed"])

    # Display summary stats
    st.subheader("Overview")
    # Compute all cases assigned and all patients in system
    all_cases = len(visits)
    all_patients = db.query(Patient).count()

    # Row 1: Waiting for Review, Completed
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        st.metric("Waiting for Review", sent)
        if st.button("Open Waiting for Review", key="card_sent"):
            st.session_state["doctor_filter_status"] = "sent_to_doctor"
            st.switch_page("pages/d_case_list.py")
    with r1c2:
        st.metric("Completed", done)
        if st.button("Open Completed", key="card_completed"):
            st.session_state["doctor_filter_status"] = "completed"
            st.switch_page("pages/d_case_list.py")

    # Row 2: All Cases, All Patients
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        st.metric("All Cases", all_cases)
        if st.button("Open All Cases", key="card_all_cases"):
            st.session_state["doctor_filter_status"] = "all"
            st.switch_page("pages/d_case_list.py")
    with r2c2:
        st.metric("All Patients", all_patients)
        if st.button("Open All Patients", key="card_all_patients"):
            st.session_state.pop("doctor_filter_status", None)
            st.switch_page("pages/d_patient_list.py")

    st.divider()

    st.subheader("Assigned Cases")

    if not visits:
        st.info("No cases assigned yet.")
        return

    for visit in visits:
        patient = db.query(Patient).filter(Patient.id == visit.patient_id).first()

        with st.container():
            st.write(f"### {patient.name} — ({patient.patient_id})")
            st.write(f"- Age: **{patient.age}**")
            st.write(f"- Gender: **{patient.gender}**")
            st.write(f"- Visit ID: **{visit.id}**")
            st.write(f"- Status: **{visit.status}**")

            colA, colB = st.columns(2)

            if colA.button("Review Case", key=f"open_{visit.id}"):
                st.session_state["open_visit_id"] = visit.id
                st.switch_page("pages/d_view_case.py")

            # (Removed manual "Mark Completed" action as requested)

    st.divider()
    if st.button("Logout"):
        st.session_state.clear()
        st.switch_page("app.py")


if __name__ == "__main__":
    main()
