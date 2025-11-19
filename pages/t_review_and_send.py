import streamlit as st
from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.visit_service import get_visit_by_id, update_visit
from services.tpa_service import run_tpa_eligibility
from services.patient_service import get_patient_by_id
from services.user_service import get_doctor_list

# Page config is set globally in app.py

require_role("technician")
render_technician_sidebar()

st.title("Final Review")

# Ensure we have an active visit
if "current_visit_id" not in st.session_state:
    st.error("No active patient visit found. Start a new visit before proceeding.")
    st.stop()

visit_id = st.session_state["current_visit_id"]
visit = get_visit_by_id(visit_id)

if not visit:
    st.error("Visit not found.")
    st.stop()

patient = visit.patient

# -------------------------
# Patient Overview
# -------------------------
st.subheader("Patient Overview")
st.write(f"**Patient ID:** {patient.patient_id}")
st.write(f"**Name:** {patient.name}")
st.write(f"**Age:** {patient.age}")
st.write(f"**Gender:** {patient.gender}")

st.divider()

# -------------------------
# Vitals
# -------------------------
st.subheader("Vitals")
bp_text = (
    f"{visit.systolic_bp}/{visit.diastolic_bp} mmHg"
    if getattr(visit, "systolic_bp", None) is not None and getattr(visit, "diastolic_bp", None) is not None
    else "—"
)
st.write(f"**Blood Pressure:** {bp_text}")
st.write(f"**Heart Rate:** {getattr(visit, 'heart_rate', '—')}")
st.write(f"**Temperature:** {getattr(visit, 'temperature', '—')}")
st.write(f"**Oxygen Saturation:** {getattr(visit, 'oxygen_saturation', '—')}")
st.write(f"**Glucose:** {getattr(visit, 'glucose', '—')}")
st.write(f"**INR:** {getattr(visit, 'inr', '—')}")

st.divider()

# -------------------------
# NIHSS Score
# -------------------------
st.subheader("NIHSS Assessment")
st.write(f"**Total Score:** {visit.nihss_score}")

st.divider()

# -------------------------
# Scan results
# -------------------------

st.subheader("Scan Analysis")
if visit.scan_path:
    st.image(visit.scan_path, caption="Uploaded Scan", use_column_width=True)
else:
    st.warning("No scan uploaded yet.")

if getattr(visit, 'prediction_label', None):
    st.write(f"**Prediction:** {visit.prediction_label}")
    if getattr(visit, 'prediction_confidence', None) is not None:
        st.write(f"**Confidence:** {float(visit.prediction_confidence):.2f}%")
else:
    st.warning("No scan prediction available.")

# Show class confidence breakdown if available in state; fallback to recompute
probs = st.session_state.get(f"visit_probs_{visit.id}") or []
if not probs and visit.scan_path:
    try:
        from services.scan_service import run_model_on_scan
        _, _, probs = run_model_on_scan(visit.scan_path)
    except Exception:
        probs = []

if probs:
    st.markdown("### Class Confidence Breakdown")
    for item in probs:
        try:
            lbl = item.get('label')
            conf = float(item.get('confidence', 0.0))
        except Exception:
            lbl, conf = str(item), 0.0
        st.write(f"- {lbl}: {conf:.2f}%")

st.divider()

# -------------------------
# tPA results
# -------------------------

st.subheader("tPA Eligibility")
# If tPA hasn't been evaluated yet, run the eligibility checks now so
# the technician (and subsequently the doctor) can see the result even
# when no scan was uploaded.
if visit.tpa_eligible is None:
    try:
        tpa_result = run_tpa_eligibility(visit.id)
    except Exception:
        tpa_result = {"eligible": None, "reason": "No Scan available."}

    # Persist only the reason; do not persist a definitive eligible flag when
    # the result is indeterminate (eligible is None). This prevents storing
    # a false negative when imaging is missing.
    try:
        if tpa_result.get("eligible") is None:
            update_visit(visit.id, tpa_reason=tpa_result.get("reason"))
        else:
            update_visit(visit.id, tpa_eligible=bool(tpa_result.get("eligible")), tpa_reason=tpa_result.get("reason"))
    except Exception:
        pass

    if tpa_result.get("eligible") is None:
        status = "Indeterminate"
    elif tpa_result.get("eligible"):
        status = "Eligible"
    else:
        status = "NOT Eligible"

    st.write(f"Status: {status}")
    st.write(f"Reason: {tpa_result.get('reason', '')}")
else:
    status = "Eligible" if visit.tpa_eligible else "NOT Eligible"
    st.write(f"Status: {status}")
    st.write(f"Reason: {visit.tpa_reason or ''}")

st.divider()

# -------------------------
# Technician Notes
# -------------------------

st.subheader("Technician Notes")
notes = st.text_area(
    "Add any technician notes before sending to the doctor:",
    value=getattr(visit, 'technician_notes', '')
)

# Save notes live
update_visit(visit.id, technician_notes=notes)

st.divider()


# -------------------------
# Assign doctor
# -------------------------

st.subheader("Assign to Doctor")
doctors = get_doctor_list()
doctor_names = [f"{(getattr(doc, 'full_name', None) or doc.username)} ({doc.username})" for doc in doctors]
doctor_selected = st.selectbox("Select doctor to send case to:", doctor_names)
selected_idx = doctor_names.index(doctor_selected) if doctor_names else 0
doctor_username = doctors[selected_idx].username  # extract username


# -------------------------
# Action buttons
# -------------------------

col1, col2 = st.columns(2)

with col1:
    if st.button("Save Visit", type="primary"):
        update_visit(visit.id, status="saved")
        st.success("Visit saved successfully.")

with col2:
    # Basic validation: encourage saving vitals/NIHSS before sending
    missing_vitals = all(
        getattr(visit, f, None) is None for f in [
            'systolic_bp','diastolic_bp','heart_rate','glucose'
        ]
    )
    missing_nihss = getattr(visit, 'nihss_score', None) is None
    if missing_vitals or missing_nihss:
        st.warning("Consider saving Vitals and NIHSS before sending to a doctor for best review.")

    if st.button("Send to Doctor", type="secondary"):
        update_visit(
            visit.id,
            doctor_username=doctor_username,
            status="sent_to_doctor"
        )
        st.success("Case sent to doctor successfully!")
        st.session_state.pop("current_visit_id", None)
        st.switch_page("pages/t_patient_list.py")
