import streamlit as st
from services.user_service import authenticate_user
from core.session_manager import login, init_session_state, clear_session
from core.helpers import hide_sidebar_completely


def main():
    st.set_page_config(page_title="Doctor Login", page_icon="🩺", initial_sidebar_state="collapsed")
    hide_sidebar_completely()

    init_session_state()
    clear_session()

    st.title("Doctor Login")
    st.write("Please enter your credentials to continue.")

    with st.form("doctor_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        # Seeded doctors use role "physician"; align the check
        user = authenticate_user(username, password, role="physician")

        if user:
            login(user)
            st.success("Login successful! Redirecting...")
            st.switch_page("pages/d_dashboard.py")
        else:
            st.error("Invalid credentials. Try again.")


if __name__ == "__main__":
    main()
