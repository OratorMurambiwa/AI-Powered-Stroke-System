import streamlit as st
from core.session_manager import require_role, logout
from core.helpers import render_technician_sidebar
from services.patient_service import get_all_patients
from core.database import get_db_context
from models.visit import Visit
from sqlalchemy import or_

# Page config is set globally in app.py


# Restrict page
require_role("technician")
render_technician_sidebar()

st.title("Technician Dashboard")


# Load summary data
with get_db_context() as db:
    patients = get_all_patients(db)
    total_patients = len(patients)

    # Cases not reviewed yet (not sent to doctor and not completed)
    not_reviewed_statuses = ["in_progress", "analysis_completed", "saved"]
    not_reviewed = (
        db.query(Visit)
        .filter(
            or_(
                Visit.status.is_(None),
                Visit.status == "",
                Visit.status.in_(not_reviewed_statuses),
            )
        )
        .count()
    )

    # Completed cases
    completed = db.query(Visit).filter(Visit.status == "completed").count()

st.subheader("Overview")
colA, colB, colC = st.columns(3)
with colA:
    st.metric("Total Patients", total_patients)
    if st.button("Open Cases", key="tech_card_all_cases"):
        st.session_state["tech_filter_status"] = "all"
        st.switch_page("pages/t_case_list.py")
with colB:
    st.metric("Cases Not Reviewed", not_reviewed)
    if st.button("Open Cases", key="tech_card_not_reviewed"):
        st.session_state["tech_filter_status"] = "not_reviewed"
        st.switch_page("pages/t_case_list.py")
with colC:
    st.metric("Completed Cases", completed)
    if st.button("Open Cases", key="tech_card_completed"):
        st.session_state["tech_filter_status"] = "completed"
        st.switch_page("pages/t_case_list.py")

# Navigation Buttons
st.write("## Actions")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Register New Patient"):
        st.switch_page("pages/t_patient_registration.py")

with col2:
    if st.button("Patient List"):
        st.switch_page("pages/t_patient_list.py")

with col3:
    if st.button("Logout"):
        # Use centralized logout which handles redirect
        logout()
