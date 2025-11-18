import streamlit as st
from core.session_manager import require_role
from core.helpers import render_doctor_sidebar
from services.patient_service import get_patient_by_id
from services.visit_service import get_visits_for_patient


def main():
    require_role("doctor")
    render_doctor_sidebar()

    st.title("Patient Visit History")

    if "selected_patient" not in st.session_state:
        st.error("No patient selected. Please go back to the patient list.")
        if st.button("Back to Patient List"):
            st.switch_page("pages/d_patient_list.py")
        st.stop()

    patient_code = st.session_state["selected_patient"]
    patient = get_patient_by_id(patient_code)

    if not patient:
        st.error("Patient not found.")
        if st.button("Back to Patient List"):
            st.switch_page("pages/d_patient_list.py")
        st.stop()

    st.subheader(f"{patient.name} ({patient.patient_id})")
    st.caption(f"Age: {patient.age} • Gender: {patient.gender}")

    visits = get_visits_for_patient(patient.id)

    if not visits:
        st.info("No prior visits found for this patient.")
        if st.button("Back to Patient List"):
            st.switch_page("pages/d_patient_list.py")
        st.stop()

    st.markdown("---")

    for v in visits:
        with st.container():
            left, right = st.columns([3, 2])
            with left:
                st.write(f"Visit ID: {v.visit_id}")
                ts = getattr(v, 'timestamp', None)
                st.write(f"Date/Time: {ts if ts else '—'}")
                st.write(f"Status: {getattr(v, 'status', '—')}")
            with right:
                st.write(f"NIHSS: {getattr(v, 'nihss_score', '—')}")
                st.write(f"Prediction: {getattr(v, 'prediction_label', '—')}")
                conf = getattr(v, 'prediction_confidence', None)
                if conf is not None:
                    try:
                        st.write(f"Confidence: {float(conf):.2f}%")
                    except Exception:
                        st.write(f"Confidence: {conf}")
                st.write(f"tPA Eligible: {getattr(v, 'tpa_eligible', '—')}")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("Open Case", key=f"open_{v.id}"):
                    st.session_state["open_visit_id"] = v.id
                    st.switch_page("pages/d_view_case.py")
            with c2:
                pass
        st.markdown("---")

    if st.button("Back to Patient List", use_container_width=True):
        st.switch_page("pages/d_patient_list.py")


if __name__ == "__main__":
    main()
