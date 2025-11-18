import streamlit as st
from core.session_manager import require_role
from core.database import get_db
from models.visit import Visit
from models.treatment import Treatment
import requests
from core.helpers import render_doctor_sidebar


def main():
    require_role("doctor")
    render_doctor_sidebar()

    db = next(get_db())
    visit_id = st.session_state.get("open_visit_id")

    if not visit_id:
        st.error("No visit selected.")
        return

    st.title("Finalize Case")

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    treatment = db.query(Treatment).filter(Treatment.visit_id == visit_id).first()

    st.subheader("Review Before Finalizing")

    # Show ICD-10 code saved on the Visit (source of truth)
    if visit.icd_code:
        desc = ""
        try:
            url = f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms={visit.icd_code}"
            data = requests.get(url, timeout=6).json()
            results = data[3] if isinstance(data, list) and len(data) > 3 else []
            for c, name in results:
                if c == visit.icd_code:
                    desc = name
                    break
        except Exception:
            pass
        st.write(f"**ICD Code:** {visit.icd_code}{(' — ' + desc) if desc else ''}")
    else:
        st.error("No ICD code added yet.")

    st.write("---")

    if treatment and treatment.plan_text:
        st.text_area("Treatment Plan", treatment.plan_text, height=200)
    else:
        st.error("No treatment plan generated yet.")

    if st.button("Finalize Case"):
        visit.status = "completed"
        db.commit()
        st.success("Case finalized successfully!")
        st.switch_page("pages/d_dashboard.py")

    if st.button("Back"):
        st.switch_page("pages/d_view_case.py")


if __name__ == "__main__":
    main()
