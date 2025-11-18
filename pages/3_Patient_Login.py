import streamlit as st
from services.user_service import authenticate_user
from core.session_manager import login, init_session_state, clear_session
from core.helpers import hide_sidebar_completely


def main():
    st.set_page_config(page_title="Patient Login", page_icon="🧍", initial_sidebar_state="collapsed")
    hide_sidebar_completely()

    init_session_state()
    clear_session()

    st.title("Patient Login")
    st.write("Please enter your credentials to continue.")

    with st.form("patient_login_form"):
        username = st.text_input("Patient ID (e.g., P001)")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        user = authenticate_user(username, password, role="patient")

        if user:
            login(user)
            st.success("Login successful! Redirecting...")
            st.switch_page("pages/p_dashboard.py")
        else:
            st.error("Invalid credentials. Try again.")


if __name__ == "__main__":
    main()
