import streamlit as st

from core.session_manager import require_role
from core.helpers import render_technician_sidebar, visit_code_display
from services.patient_service import get_patient_by_id, update_patient, delete_patient, delete_visit
from services.visit_service import get_visits_for_patient

# Technician only
require_role("technician")
render_technician_sidebar()

st.title("Patient Visit History")

# Ensure a patient is selected from previous page
if "selected_patient" not in st.session_state:
    st.error("No patient selected. Please go back to the patient list.")
    if st.button("Back to Patient List"):
        st.switch_page("pages/t_patient_list.py")
    st.stop()

patient_code = st.session_state["selected_patient"]
patient = get_patient_by_id(patient_code)

if not patient:
    st.error("Patient not found.")
    if st.button("Back to Patient List"):
        st.switch_page("pages/t_patient_list.py")
    st.stop()

st.subheader(f"{patient.name} ({patient.patient_id})")
st.caption(f"Age: {patient.age} • Gender: {patient.gender}")

# Edit patient info
with st.expander("✏️ Edit Patient Info", expanded=False):
    new_name = st.text_input("Full Name", value=patient.name)
    new_age = st.number_input("Age", min_value=1, max_value=120, step=1, value=int(patient.age or 1))
    new_gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"], index=["Male","Female","Other","Prefer not to say"].index(patient.gender) if patient.gender in ["Male","Female","Other","Prefer not to say"] else 0)
    if st.button("Save Changes", type="primary"):
        updated = update_patient(patient.patient_id, name=new_name, age=int(new_age), gender=new_gender)
        if updated:
            st.success("Patient info updated.")
            st.rerun()
        else:
            st.error("Failed to update patient.")

# Danger zone: delete patient
with st.expander("🗑️ Delete Patient", expanded=False):
    st.warning("Deleting a patient will remove all their visits. This cannot be undone.")
    confirm = st.text_input("Type DELETE to confirm", value="")
    if st.button("Delete Patient", type="secondary", help="Irreversible action"):
        if confirm.strip().upper() == "DELETE":
            if delete_patient(patient.patient_id):
                st.success("Patient deleted.")
                st.session_state.pop("selected_patient", None)
                st.switch_page("pages/t_patient_list.py")
            else:
                st.error("Failed to delete patient.")
        else:
            st.error("Confirmation text does not match DELETE.")

# Fetch visits
visits = get_visits_for_patient(patient.id)

if not visits:
    st.info("No prior visits found for this patient.")
    if st.button("Start New Visit"):
        st.switch_page("pages/t_patient_visit.py")
    st.stop()

st.markdown("---")

for v in visits:
    with st.container():
        left, right = st.columns([3, 2])
        with left:
            st.write(f"Visit ID: {visit_code_display(v.visit_id)}")
            ts = getattr(v, 'timestamp', None)
            st.write(f"Date/Time: {ts if ts else '—'}")
            st.write(f"Status: {getattr(v, 'status', '—')}")
        with right:
            st.write(f"NIHSS: {getattr(v, 'nihss_score', '—')}")
            st.write(f"Prediction: {getattr(v, 'prediction_label', '—')}")
            conf = getattr(v, 'prediction_confidence', None)
            if conf is not None:
                st.write(f"Confidence: {float(conf):.2f}%")
            st.write(f"tPA Eligible: {getattr(v, 'tpa_eligible', '—')}")
            reason = getattr(v, 'tpa_reason', None)
            if reason:
                st.write(f"Reason: {reason}")

        # Actions row
        c1, c2, c3 = st.columns(3)
        with c1:
            if not getattr(v, 'scan_path', None):
                if st.button("📤 Upload Scan", key=f"upload_{v.id}"):
                    st.session_state["current_visit_id"] = v.id
                    st.switch_page("pages/t_upload_scan.py")
            # If scan already exists, no Review button is shown here per request
        with c2:
            if st.button("✏️ Edit Visit (Vitals/NIHSS)", key=f"edit_{v.id}"):
                st.session_state["current_visit_id"] = v.id
                # Send to vitals first; user can proceed to NIHSS
                st.switch_page("pages/t_vitals_entry.py")
        with c3:
            if st.button("🗑️ Delete Visit", key=f"delete_{v.id}"):
                if delete_visit(v.id):
                    st.success(f"Deleted visit {v.visit_id}.")
                    st.rerun()
                else:
                    st.error("Failed to delete visit.")
        st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    if st.button("Back to Patient List", use_container_width=True):
        st.switch_page("pages/t_patient_list.py")
with col2:
    if st.button("Start New Visit", use_container_width=True):
        st.switch_page("pages/t_patient_visit.py")
