import streamlit as st
import requests
from core.session_manager import require_role
from core.database import get_db
from models.visit import Visit
from sqlalchemy.orm import Session
from streamlit_searchbox import st_searchbox
from core.helpers import render_doctor_sidebar


def main():
    require_role("doctor")
    render_doctor_sidebar()

    db = next(get_db())

    if "open_visit_id" not in st.session_state:
        st.error("No visit selected.")
        st.stop()

    visit_id = st.session_state["open_visit_id"]

    st.title("ICD-10 Code Generator")

    # Live search with suggestions as you type
    @st.cache_data(show_spinner=False)
    def icd_lookup(term: str):
        term = (term or "").strip()
        if not term:
            return []
        url = f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms={term}"
        try:
            data = requests.get(url, timeout=8).json()
            results = data[3] if isinstance(data, list) and len(data) > 3 else []
        except Exception:
            results = []
        # return a list of display strings
        return [f"{code} — {name}" for code, name in results][:20]

    # Prefill with the currently saved ICD code, so it's static/visible
    current_code = None
    current_display = ""
    try:
        visit = db.query(Visit).filter(Visit.id == visit_id).first()
        if visit and visit.icd_code:
            # fetch description for nicer default display
            data = requests.get(
                f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms={visit.icd_code}",
                timeout=6,
            ).json()
            results = data[3] if isinstance(data, list) and len(data) > 3 else []
            desc = ""
            for c, name in results:
                if c == visit.icd_code:
                    desc = name
                    break
            current_code = visit.icd_code
            current_display = f"{visit.icd_code}{(' — ' + desc) if desc else ''}"
    except Exception:
        pass

    if current_display:
        st.caption("Current ICD-10 selection:")
        st.text(current_display)

    selection = st_searchbox(
        icd_lookup,
        key="icd10_search",
        placeholder="Type keywords, e.g. ischemic stroke",
        default=current_display or "",
    )

    # Stabilize UX: only save when user confirms, avoid saving mid-type
    if selection and selection.strip():
        st.markdown("### Selected")
        st.write(selection)
        if st.button("Save ICD-10 Code", type="primary"):
            import re
            text = selection.strip()
            # Accept formats like "I63.9 — Cerebral infarction, unspecified" or just code
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9\.]+)\s*(?:—|-|:)?\s*(.*)$", text)
            if m:
                code = m.group(1).upper()
                name = m.group(2).strip()
            else:
                code, name = text.upper(), ""

            visit = db.query(Visit).filter(Visit.id == visit_id).first()
            if visit:
                visit.icd_code = code
                db.commit()
                st.success(f"ICD Code Saved: {code}{(' — ' + name) if name else ''}")
                st.switch_page("pages/d_view_case.py")

    if st.button("Back"):
        st.switch_page("pages/d_view_case.py")


if __name__ == "__main__":
    main()
