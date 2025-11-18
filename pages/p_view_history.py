import streamlit as st
from core.session_manager import require_role
from core.helpers import render_patient_sidebar
from core.database import get_db
from sqlalchemy.orm import Session
from models.visit import Visit
from models.patient import Patient
from models.treatment import Treatment
import os
from core import database as db_core


def main():
    require_role("patient")
    render_patient_sidebar()

    if "patient_visit_id" not in st.session_state:
        st.error("No visit selected.")
        return

    visit_id = st.session_state["patient_visit_id"]
    db = next(get_db())

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        st.error("Visit not found.")
        return

    patient = db.query(Patient).filter(Patient.id == visit.patient_id).first()

    st.title(f"Visit #{visit.id} Summary")

    st.subheader("Basic Information")
    st.write(f"**Name:** {patient.name}")
    st.write(f"**Age:** {patient.age}")
    st.write(f"**Gender:** {patient.gender}")

    st.write("---")
    st.subheader("Vitals")
    st.write(f"**Systolic BP:** {visit.systolic_bp}")
    st.write(f"**Diastolic BP:** {visit.diastolic_bp}")
    st.write(f"**Heart Rate:** {visit.heart_rate}")
    st.write(f"**Glucose:** {visit.glucose}")
    st.write(f"**NIHSS Score:** {visit.nihss_score}")

    st.write("---")
    st.subheader("Scan & Model Prediction")

    if visit.scan_path:
        base_dir = db_core.BASE_DIR
        ann_path = os.path.join(base_dir, "data", "uploads", "annotations", f"visit_{visit.id}.png")
        if os.path.exists(ann_path):
            st.image(ann_path, caption="Annotated Scan", width=350)
            with st.expander("View original scan"):
                st.image(visit.scan_path, caption="Original Scan", width=350)
        else:
            st.image(visit.scan_path, caption="Uploaded Scan", width=350)

    pred = getattr(visit, "prediction_label", None) or "—"
    conf = getattr(visit, "prediction_confidence", None)
    st.write(f"**Prediction:** {pred}")
    if conf is not None:
        try:
            st.write(f"**Confidence:** {float(conf):.2f}%")
        except Exception:
            st.write(f"**Confidence:** {conf}")
    else:
        st.write("**Confidence:** —")
    st.write(f"**tPA Eligibility:** {visit.tpa_eligible}")
    st.write(f"**Reason:** {visit.tpa_reason}")

    st.write("---")
    st.subheader("Treatment & ICD Code")

    treatment = (
        db.query(Treatment)
        .filter(Treatment.visit_id == visit_id)
        .first()
    )

    # Show ICD code stored on Visit (source of truth)
    st.write(f"**ICD Code:** {visit.icd_code or '—'}")

    if treatment and (treatment.plan_text or '').strip():
        if st.button("View Treatment Plan"):
            st.switch_page("pages/p_view_treatment.py")
    else:
        st.info("Doctor has not provided a treatment plan yet.")

    if st.button("Back"):
        st.switch_page("pages/p_dashboard.py")


if __name__ == "__main__":
    main()
