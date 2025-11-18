import streamlit as st
from core.session_manager import login, init_session_state, clear_session
from services.user_service import authenticate_user
from core.helpers import hide_sidebar_completely


def main():
    st.set_page_config(page_title="Technician Login", page_icon="🩺", initial_sidebar_state="collapsed")
    hide_sidebar_completely()

    # Ensure session keys exist
    init_session_state()

    # Clear any previous login when entering this page
    clear_session()

    st.title("Technician Login")
    st.write("Please enter your credentials to continue.")

    with st.form("tech_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        # Validate user with role filtering
        user = authenticate_user(username, password, role="technician")

        if user:
            # Store session
            login(user)

            st.success("Login successful! Redirecting...")

            # Clear query params (new API)
            st.query_params.clear()

            # Go to dashboard
            st.switch_page("pages/t_dashboard.py")
        else:
            st.error("Invalid credentials. Try again.")


if __name__ == "__main__":
    main()
