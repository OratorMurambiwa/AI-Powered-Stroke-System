import streamlit as st
from core.database import get_db_context
from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.patient_service import create_patient, get_all_patients

# Page config is set globally in app.py

# Only technicians can access
require_role("technician")
render_technician_sidebar()

st.title("Register New Patient")

# Step 1: Search existing patients with live suggestions
st.subheader("Step 1: Check if Patient Exists")
search_name = st.text_input("Search patient name:", placeholder="Type to search...")

if search_name.strip():
    with get_db_context() as db:
        all_patients = get_all_patients(db)
    q = search_name.lower()
    matches = [p for p in all_patients if q in (p.name or "").lower()][:10]
    if matches:
        st.warning(f"Found {len(matches)} existing patient(s) with similar names:")
        for p in matches:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{p.name}** - ID: {p.patient_id}, Age: {p.age}, Gender: {p.gender}")
            with col2:
                if st.button("Select", key=f"sel_{p.patient_id}"):
                    st.session_state["selected_patient"] = p.patient_id
                    # Open history for existing patient per prior requirement
                    st.switch_page("pages/t_patient_history.py")
    else:
        st.success("No existing patients found. You can register as new.")

st.write("---")

# Step 2: Register new patient (independent form so typing isn't affected by suggestions)
st.subheader("Step 2: Register New Patient")
st.write("If the patient doesn't exist above, fill in their details:")

with st.form("patient_form"):
    name = st.text_input("Full Name", placeholder="John Doe")
    age = st.number_input("Age", min_value=1, max_value=120, step=1)
    gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"])
    submitted = st.form_submit_button("Create New Patient")

    if submitted:
        if not (name or "").strip():
            st.error("Name cannot be empty.")
        else:
            with get_db_context() as db:
                patient = create_patient(db, name=name.strip(), age=age, gender=gender)
            st.session_state["selected_patient"] = patient.patient_id
            st.success(f"Patient created! ID: {patient.patient_id}")
            st.switch_page("pages/t_patient_visit.py")
