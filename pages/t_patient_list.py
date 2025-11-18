import streamlit as st
from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.patient_service import list_patients, get_patient_by_id

# Page config is set globally in app.py

# Access control
require_role("technician")
render_technician_sidebar()

st.title("Patient List")
st.write("Select a patient to begin a new stroke visit or review past visits.")

# Search bar
search_query = st.text_input("Search by name or patient ID", placeholder="e.g., John or P003")

# Load patients
patients = list_patients()

# Filter
if search_query.strip():
    q = search_query.lower()
    patients = [
        p for p in patients
        if q in p.name.lower() or q in p.patient_id.lower()
    ]

# If no patients
if not patients:
    st.info("No patients found.")
    st.stop()

# Display table
for p in patients:
    with st.container():
        st.write(f"**{p.name}**  —  {p.patient_id}")
        st.write(f"Age: {p.age}, Gender: {p.gender}")

        col1, col2 = st.columns([1,1])

        with col1:
            if st.button(f"Start New Visit ({p.patient_id})", key=f"new_{p.patient_id}"):
                st.session_state["selected_patient"] = p.patient_id
                st.switch_page("pages/t_patient_visit.py")

        with col2:
            if st.button(f"View History ({p.patient_id})", key=f"history_{p.patient_id}"):
                st.session_state["selected_patient"] = p.patient_id
                st.switch_page("pages/t_patient_history.py")

        st.markdown("---")
