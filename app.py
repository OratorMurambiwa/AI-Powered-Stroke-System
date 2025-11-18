import streamlit as st

from core.session_manager import init_session_state, logout
from services.user_service import ensure_default_users, create_user


def go_to(page_path: str):
    st.switch_page(page_path)


def main():
    st.set_page_config(
        page_title="Stroke System",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_session_state()

    try:
        ensure_default_users()
    except Exception:
        pass

    user = st.session_state.get("user")
    role = st.session_state.get("role")

    cols = st.columns([4, 2])
    with cols[0]:
        st.title("Stroke System")
    with cols[1]:
        if user:
            st.info(f"Logged in as: **{user.get('username', '')}** ({role})")
            if st.button("Log out"):
                logout()
                st.rerun()

    st.write("---")

    if user is None or role is None:
        # Hide sidebar & its toggle on the initial role selection page
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="collapsedControl"] { display: none !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Choose how you want to log in")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("### Technician")
            if st.button("Technician Login"):
                go_to("pages/1_Technician_Login.py")

        with c2:
            st.markdown("### Doctor")
            if st.button("Doctor Login"):
                go_to("pages/2_Doctor_Login.py")

        with c3:
            st.markdown("### Patient")
            if st.button("Patient Login"):
                go_to("pages/3_Patient_Login.py")

        st.write("---")

        # Signup section
        st.markdown("### New here? Sign up")
        signup_tab1, signup_tab2, signup_tab3 = st.tabs(["Technician", "Physician", "Patient"])

        with signup_tab1:
            tech_user = st.text_input("Username", key="su_tech_user")
            tech_pass = st.text_input("Password", type="password", key="su_tech_pass")
            tech_name = st.text_input("Full Name (optional)", key="su_tech_name")
            if st.button("Create Technician Account", key="btn_su_tech"):
                try:
                    create_user("technician", tech_user, tech_pass, full_name=tech_name)
                    st.success("Technician account created. You can now log in.")
                except Exception as e:
                    st.error(str(e))

        with signup_tab2:
            doc_user = st.text_input("Username", key="su_doc_user")
            doc_pass = st.text_input("Password", type="password", key="su_doc_pass")
            doc_name = st.text_input("Full Name (optional)", key="su_doc_name")
            if st.button("Create Physician Account", key="btn_su_doc"):
                try:
                    create_user("physician", doc_user, doc_pass, full_name=doc_name)
                    st.success("Physician account created. You can now log in.")
                except Exception as e:
                    st.error(str(e))

        with signup_tab3:
            st.caption("Patients must sign up with their existing patient code (e.g., P003)")
            pat_code = st.text_input("Patient Code (e.g., P003)", key="su_pat_code").upper()
            pat_pass = st.text_input("Password", type="password", key="su_pat_pass")
            pat_name = st.text_input("Full Name (optional)", key="su_pat_name")
            if st.button("Create Patient Account", key="btn_su_pat"):
                try:
                    create_user("patient", pat_code, pat_pass, patient_code=pat_code, full_name=pat_name)
                    st.success("Patient account created. You can now log in.")
                except Exception as e:
                    st.error(str(e))

        # Removed sidebar tip for a cleaner landing page
        return

    st.subheader("Quick navigation")

    if role == "technician":
        if st.button("Go to Technician Dashboard"):
            go_to("pages/t_dashboard.py")

    elif role == "doctor":
        if st.button("Go to Doctor Dashboard"):
            go_to("pages/d_dashboard.py")

    elif role == "patient":
        if st.button("Go to Patient Dashboard"):
            go_to("pages/p_dashboard.py")

    else:
        st.warning("Unknown role. Please log in again.")
        if st.button("Back to login choices"):
            logout()
            st.rerun()


if __name__ == "__main__":
    main()
