import streamlit as st
from core.session_manager import require_role
from core.helpers import render_doctor_sidebar
from services.user_service import get_current_user
from core.database import get_db
from models.patient import Patient
from models.visit import Visit
from sqlalchemy.orm import Session


def main():
    require_role("doctor")
    render_doctor_sidebar()

    st.title("Patient List")
    st.caption("Search by name or patient ID. View visit history.")

    db: Session = next(get_db())
    doctor = get_current_user()

    # Optional visit status filter from session
    filter_status = st.session_state.get("doctor_filter_status")

    # Search
    q = st.text_input("Search", placeholder="e.g., Jane or P003").strip().lower()

    # Base query: all patients; if a status filter is set, reduce to patients with such visits assigned to this doctor
    patients_q = db.query(Patient)

    if filter_status:
        # Join with visits filtered by doctor + status, then distinct patients
        patients_q = (
            db.query(Patient)
            .join(Visit, Visit.patient_id == Patient.id)
            .filter(Visit.doctor_username == doctor.username)
            .filter(Visit.status == filter_status)
            .distinct()
            .order_by(Patient.id.desc())
        )
    else:
        patients_q = patients_q.order_by(Patient.id.desc())

    patients = patients_q.all()

    # Search filter
    if q:
        patients = [p for p in patients if q in (p.name or "").lower() or q in (p.patient_id or "").lower()]

    # Empty state
    if not patients:
        if filter_status:
            st.info(f"No patients found with visits in status: {filter_status}.")
        else:
            st.info("No patients found.")
        if st.button("Clear Filter" if filter_status else "Back to Dashboard"):
            st.session_state.pop("doctor_filter_status", None)
            st.switch_page("pages/d_dashboard.py")
        return

    # Render list
    for p in patients:
        with st.container():
            st.write(f"**{p.name}**  —  {p.patient_id}")
            st.write(f"Age: {p.age}, Gender: {p.gender}")

            # Show last known status of the most recent visit assigned to this doctor
            recent = (
                db.query(Visit)
                .filter(Visit.patient_id == p.id)
                .filter(Visit.doctor_username == doctor.username)
                .order_by(Visit.id.desc())
                .first()
            )
            if recent:
                st.caption(f"Latest Visit: {recent.visit_id} • Status: {recent.status}")

            col1, col2 = st.columns([1,1])
            with col1:
                if st.button(f"View Visit History ({p.patient_id})", key=f"history_{p.patient_id}"):
                    st.session_state["selected_patient"] = p.patient_id
                    st.switch_page("pages/d_patient_history.py")
            with col2:
                if recent:
                    if st.button(f"Open Latest Case ({recent.visit_id})", key=f"open_{recent.id}"):
                        st.session_state["open_visit_id"] = recent.id
                        st.switch_page("pages/d_view_case.py")
        st.markdown("---")

    # Footer actions
    cols = st.columns(2)
    with cols[0]:
        if st.button("Back to Dashboard", use_container_width=True):
            st.session_state.pop("doctor_filter_status", None)
            st.switch_page("pages/d_dashboard.py")
    with cols[1]:
        if filter_status and st.button("Clear Filter", use_container_width=True):
            st.session_state.pop("doctor_filter_status", None)
            st.rerun()


if __name__ == "__main__":
    main()
