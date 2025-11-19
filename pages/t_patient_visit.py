import streamlit as st

from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.patient_service import get_patient_by_id
from services.visit_service import create_visit

# Page config is set globally in app.py

# Access control
require_role("technician")
render_technician_sidebar()

st.title("New Stroke Visit")

# Ensure a patient is selected
if "selected_patient" not in st.session_state:
    st.error("No patient selected. Please return to the patient list.")
    st.stop()

patient_id = st.session_state["selected_patient"]
patient = get_patient_by_id(patient_id)

if not patient:
    st.error("Patient not found.")
    st.stop()

# Show basic patient info
st.subheader(f"Patient: {patient.name} ({patient.patient_id})")
st.write(f"Age: {patient.age}, Gender: {patient.gender}")
st.write("---")

st.write("### Confirm that you want to start a new stroke visit for this patient.")

if st.button("Start Visit", type="primary"):
    visit = create_visit(patient_id)

    # Store visit ID in session so next pages can use it
    st.session_state["current_visit_id"] = visit.id

    st.success("Visit created successfully.")
    st.switch_page("pages/t_vitals_entry.py")
