import streamlit as st
from services.user_service import create_user
from core.session_manager import init_session_state, clear_session, login
from core.database import get_db_context
from models.patient import Patient

# Public patient self-signup page
st.set_page_config(page_title="Patient Sign Up", page_icon="📝", initial_sidebar_state="collapsed")

init_session_state()
clear_session()

st.title("Patient Account Sign Up")
st.caption("Create an account using your assigned patient code (e.g. P001). If you do not have a code yet, please contact a technician to register you first.")

with st.form("patient_signup_form"):
    patient_code = st.text_input("Patient Code (e.g., P001)").upper().strip()
    full_name = st.text_input("Full Name (optional)")
    password = st.text_input("Password", type="password")
    password2 = st.text_input("Confirm Password", type="password")
    submit = st.form_submit_button("Create Account")

    if submit:
        if not patient_code:
            st.error("Patient code is required.")
        elif not password:
            st.error("Password is required.")
        elif password != password2:
            st.error("Passwords do not match.")
        else:
            # verify patient exists
            try:
                with get_db_context() as db:
                    patient = db.query(Patient).filter(Patient.patient_id == patient_code).first()
                if not patient:
                    st.error("Patient code not found. Please ask a technician to register you first.")
                else:
                    try:
                        user = create_user(role="patient", username=patient_code, password=password, patient_code=patient_code, full_name=full_name or patient.name)
                        login(user)
                        st.success("Account created and logged in!")
                        st.switch_page("pages/p_dashboard.py")
                    except Exception as e:
                        st.error(f"Sign up failed: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

st.write("---")
if st.button("Back to Patient Login"):
    st.switch_page("pages/3_Patient_Login.py")
