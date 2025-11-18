import streamlit as st
from core.session_manager import require_role
from core.helpers import render_doctor_sidebar
from services.user_service import get_current_user
from core.database import get_db
from sqlalchemy.orm import Session
from models.visit import Visit
from models.patient import Patient


def _status_label(status: str) -> str:
    m = {
        "sent_to_doctor": "Waiting for Review",
        "in_review": "In Review",
        "completed": "Completed",
    }
    return m.get((status or "").strip(), status or "Cases")


def main():
    require_role("doctor")
    render_doctor_sidebar()

    db: Session = next(get_db())
    doctor = get_current_user()

    status = st.session_state.get("doctor_filter_status", "all")
    st.title(f"Cases — {_status_label(status) if status != 'all' else 'All'}")

    # Optional quick filter
    q = st.text_input("Search (name, patient ID, or visit code)", placeholder="e.g., Jane or P003 or V00012").strip().lower()

    # Load visits for this doctor by status
    base_q = (
        db.query(Visit, Patient)
        .join(Patient, Visit.patient_id == Patient.id)
        .filter(Visit.doctor_username == doctor.username)
    )
    if status and status != "all":
        base_q = base_q.filter(Visit.status == status)
    visits = base_q.order_by(Visit.id.desc()).all()

    # Apply text filter
    if q:
        def _match(vp):
            v, p = vp
            return (
                q in (p.name or "").lower()
                or q in (p.patient_id or "").lower()
                or q in (v.visit_id or "").lower()
            )
        visits = [vp for vp in visits if _match(vp)]

    if not visits:
        st.info("No cases found for this status.")
        if st.button("Back to Dashboard"):
            st.switch_page("pages/d_dashboard.py")
        return

    for v, p in visits:
        with st.container():
            left, right = st.columns([3, 2])
            with left:
                # Patient name is clickable -> patient history
                if st.button(f"{p.name}", key=f"phist_{p.patient_id}_{v.id}"):
                    st.session_state["selected_patient"] = p.patient_id
                    st.switch_page("pages/d_patient_history.py")
                st.caption(f"{p.patient_id} • Age {p.age} • {p.gender}")
                st.write(f"Visit: {v.visit_id}")
                ts = getattr(v, 'timestamp', None)
                st.write(f"Date/Time: {ts if ts else '—'}")
                st.write(f"Status: {v.status}")
            with right:
                st.write(f"NIHSS: {getattr(v, 'nihss_score', '—')}")
                st.write(f"Prediction: {getattr(v, 'prediction_label', '—')}")
                conf = getattr(v, 'prediction_confidence', None)
                if conf is not None:
                    try:
                        st.write(f"Confidence: {float(conf):.2f}%")
                    except Exception:
                        st.write(f"Confidence: {conf}")

            # Actions
            if st.button("Review Case", key=f"open_{v.id}"):
                st.session_state["open_visit_id"] = v.id
                st.switch_page("pages/d_view_case.py")
        st.markdown("---")

    cols = st.columns(2)
    with cols[0]:
        if st.button("Back to Dashboard", key="cases_footer_back_dashboard", use_container_width=True):
            st.switch_page("pages/d_dashboard.py")
    with cols[1]:
        if st.button("Patient List", key="cases_footer_patient_list", use_container_width=True):
            st.switch_page("pages/d_patient_list.py")


if __name__ == "__main__":
    main()
