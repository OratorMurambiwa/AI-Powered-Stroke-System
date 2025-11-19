import streamlit as st
from core.session_manager import require_role
from core.helpers import render_patient_sidebar
from core.database import get_db
from sqlalchemy.orm import Session
from models.treatment import Treatment
from models.visit import Visit


def main():
    require_role("patient")
    render_patient_sidebar()

    if "patient_visit_id" not in st.session_state:
        st.error("No visit selected.")
        return

    visit_id = st.session_state["patient_visit_id"]
    db = next(get_db())

    treatment = (
        db.query(Treatment)
        .filter(Treatment.visit_id == visit_id)
        .first()
    )

    st.title("Treatment Plan")

    # Only display a plan if the doctor has saved non-empty content.
    if not treatment or not (treatment.plan_text or "").strip():
        st.info("No treatment plan has been created by the doctor for this visit yet.")
        if st.button("Back"):
            st.switch_page("pages/p_view_history.py")
        return

    # Fetch Visit to display ICD stored on Visit (source of truth)
    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    st.subheader("ICD Code")
    st.write(f"**ICD Code:** {visit.icd_code or '—'}")

    st.write("---")
    st.subheader("Doctor's Treatment Plan")

    st.text_area(
        "Plan Details",
        treatment.plan_text,
        height=400,
        disabled=True
    )

    if st.button("Back"):
        st.switch_page("pages/p_view_history.py")


if __name__ == "__main__":
    main()
