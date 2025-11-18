import streamlit as st
from sqlalchemy.orm import Session

from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from core.database import get_db
from models.visit import Visit
from models.patient import Patient
from sqlalchemy import or_


def _get_filtered_visits(db: Session, status_filter: str):
    q = (
        db.query(Visit)
        .join(Patient, Visit.patient_id == Patient.id)
        .order_by(Visit.id.desc())
    )

    if status_filter == "not_reviewed":
        not_reviewed_statuses = ["in_progress", "analysis_completed", "saved"]
        q = q.filter(
            or_(
                Visit.status.is_(None),
                Visit.status == "",
                Visit.status.in_(not_reviewed_statuses),
            )
        )
    elif status_filter == "completed":
        q = q.filter(Visit.status == "completed")
    elif status_filter == "all":
        pass
    else:
        pass

    return q.all()


def main():
    require_role("technician")
    render_technician_sidebar()

    st.title("Technician Cases")

    db = next(get_db())

    status_filter = st.session_state.get("tech_filter_status", "all")
    human = {
        "all": "All Cases",
        "not_reviewed": "Cases Not Reviewed",
        "completed": "Completed Cases",
    }.get(status_filter, "All Cases")

    st.subheader(human)

    visits = _get_filtered_visits(db, status_filter)

    if not visits:
        st.info("No cases found for this filter.")
        if st.button("Back to Dashboard"):
            st.switch_page("pages/t_dashboard.py")
        return

    # Optional search by patient name or code
    query = st.text_input("Search by patient name or patient ID", placeholder="e.g., Jane or P010")

    # Build list with patient details
    rows = []
    for v in visits:
        p = db.query(Patient).filter(Patient.id == v.patient_id).first()
        if not p:
            continue
        rows.append((v, p))

    if query.strip():
        q = query.lower()
        rows = [
            (v, p) for (v, p) in rows
            if q in (p.name or "").lower() or q in (p.patient_id or "").lower()
        ]

    for v, p in rows:
        with st.container():
            left, right = st.columns([3, 2])
            with left:
                # Patient name is clickable -> technician patient history
                if st.button(p.name or p.patient_id, key=f"tech_patient_{p.id}_{v.id}"):
                    st.session_state["selected_patient"] = p.patient_id
                    st.switch_page("pages/t_patient_history.py")
                st.caption(f"Patient ID: {p.patient_id}")
                st.write(f"Visit ID: {v.visit_id}")
                ts = getattr(v, "timestamp", None)
                st.write(f"Date/Time: {ts if ts else '—'}")
            with right:
                st.write(f"Status: {getattr(v, 'status', '—')}")
                nih = getattr(v, 'nihss_score', None)
                if nih is not None:
                    st.write(f"NIHSS: {nih}")
                pred = getattr(v, 'prediction_label', None)
                if pred:
                    st.write(f"Prediction: {pred}")
        st.markdown("---")

    if st.button("Back to Dashboard", key="tech_back_dash"):
        st.switch_page("pages/t_dashboard.py")


if __name__ == "__main__":
    main()
