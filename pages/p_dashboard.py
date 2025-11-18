import streamlit as st
from core.session_manager import require_role
from core.helpers import render_patient_sidebar
from core.database import get_db
from sqlalchemy.orm import Session
from models.patient import Patient
from models.visit import Visit


def main():
    require_role("patient")
    render_patient_sidebar()

    patient = st.session_state["user"]
    db = next(get_db())

    # Fetch Patient Object
    p = (
        db.query(Patient)
        .filter(Patient.patient_id == patient.username)
        .first()
    )

    if not p:
        st.error("Patient record not found.")
        return

    st.title(f"Welcome, {p.name}")

    st.subheader("Your Profile")
    st.write(f"**Patient ID:** {p.patient_id}")
    st.write(f"**Age:** {p.age}")
    st.write(f"**Gender:** {p.gender}")

    st.write("---")
    st.subheader("Your Stroke Visit History")

    visits = (
        db.query(Visit)
        .filter(Visit.patient_id == p.id)
        .order_by(Visit.id.desc())
        .all()
    )

    if not visits:
        st.info("You have no stroke visits yet.")
        return

    for v in visits:
        with st.container():
            st.write(f"### Visit #{v.id}")
            diag = getattr(v, 'prediction_label', None) or '—'
            st.write(f"- **Diagnosis:** {diag}")
            nihss = v.nihss_score if getattr(v, 'nihss_score', None) is not None else '—'
            st.write(f"- **NIHSS Score:** {nihss}")
            st.write(f"- **Status:** {getattr(v, 'status', '—') or '—'}")
            if getattr(v, 'tpa_eligible', None) is None:
                tpa_text = '—'
            else:
                tpa_text = 'Yes' if v.tpa_eligible else 'No'
            st.write(f"- **tPA Eligible:** {tpa_text}")

            if st.button(f"View Visit #{v.id}", key=f"open_visit_{v.id}"):
                st.session_state["patient_visit_id"] = v.id
                st.switch_page("pages/p_view_history.py")


if __name__ == "__main__":
    main()
