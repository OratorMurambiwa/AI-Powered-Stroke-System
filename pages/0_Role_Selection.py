"""Deprecated duplicate role selection page.

This file previously mirrored parts of `app.py` to act as a logout/redirect target.
Navigation logic has been centralized to always return to `app.py`, so keeping a
second copy increases maintenance cost. You can delete this file safely if no
one relies on its direct URL.

Left in place temporarily with a minimal redirect for any stale bookmarks.
"""

import streamlit as st
from core.session_manager import init_session_state, logout
from services.user_service import ensure_default_users

def render_signup_section():
    st.markdown("### New here? Sign up")
    tab1, tab2, tab3 = st.tabs(["Technician", "Physician", "Patient"])  # reuse labels
    from services.user_service import create_user

    with tab1:
        tech_user = st.text_input("Username", key="su2_tech_user")
        tech_pass = st.text_input("Password", type="password", key="su2_tech_pass")
        tech_name = st.text_input("Full Name (optional)", key="su2_tech_name")
        if st.button("Create Technician Account", key="btn_su2_tech"):
            try:
                create_user("technician", tech_user, tech_pass, full_name=tech_name)
                st.success("Technician account created. You can now log in.")
            except Exception as e:
                st.error(str(e))

    with tab2:
        doc_user = st.text_input("Username", key="su2_doc_user")
        doc_pass = st.text_input("Password", type="password", key="su2_doc_pass")
        doc_name = st.text_input("Full Name (optional)", key="su2_doc_name")
        if st.button("Create Physician Account", key="btn_su2_doc"):
            try:
                create_user("physician", doc_user, doc_pass, full_name=doc_name)
                st.success("Physician account created. You can now log in.")
            except Exception as e:
                st.error(str(e))

    with tab3:
        st.caption("Patients must sign up with their existing patient code (e.g., P003)")
        pat_code = st.text_input("Patient Code (e.g., P003)", key="su2_pat_code").upper()
        pat_pass = st.text_input("Password", type="password", key="su2_pat_pass")
        pat_name = st.text_input("Full Name (optional)", key="su2_pat_name")
        if st.button("Create Patient Account", key="btn_su2_pat"):
            try:
                create_user("patient", pat_code, pat_pass, patient_code=pat_code, full_name=pat_name)
                st.success("Patient account created. You can now log in.")
            except Exception as e:
                st.error(str(e))


def main():
    # Redirect immediately to canonical home page
    init_session_state()
    try:
        ensure_default_users()
    except Exception:
        pass
    try:
        st.switch_page("app.py")
    except Exception:
        st.rerun()


if __name__ == "__main__":
    main()
