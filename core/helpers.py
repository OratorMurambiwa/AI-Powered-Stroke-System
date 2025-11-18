import os
import uuid
import hashlib
import streamlit as st


def generate_patient_id():
    """Returns a 4-digit style patient ID like P001, P002, P045."""
    number = str(uuid.uuid4().int)[:3]  # First 3 digits
    return f"P{number.zfill(3)}"


def save_uploaded_file(uploaded_file, folder_path):
    """Saves an uploaded file to a directory and returns its full path."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    file_ext = os.path.splitext(uploaded_file.name)[1]
    filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(folder_path, filename)

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return file_path



def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# -----------------------------
# Sidebar helpers
# -----------------------------
def hide_default_sidebar_nav():
    """Hide Streamlit's default multi-page navigation for a cleaner custom menu.

    Sidebar is also collapsed by default via app-wide set_page_config.
    """
    st.markdown(
        """
        <style>
        /* Hide the auto-generated Pages section */
        [data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hide_sidebar_completely():
    """Completely hide Streamlit's sidebar and the toggle control.

    Useful on login/signup pages or any unauthenticated views where
    navigation should not be visible.
    """
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_technician_sidebar():
    """Render a minimal technician sidebar menu.

    Items:
    - Dashboard
    - Register New Patient
    - Patient List
    - Logout
    """
    hide_default_sidebar_nav()
    with st.sidebar:
        st.markdown("### Technician Menu")
        if st.button("Back to Dashboard", use_container_width=True):
            st.switch_page("pages/t_dashboard.py")
        if st.button("Register New Patient", use_container_width=True):
            st.switch_page("pages/t_patient_registration.py")
        if st.button("Patient List", use_container_width=True):
            st.switch_page("pages/t_patient_list.py")
        st.divider()
        if st.button("Logout", use_container_width=True):
            from core.session_manager import logout
            logout()


def render_doctor_sidebar():
    """Render a minimal doctor sidebar menu.

    Items:
    - Patient List
    - Waiting for Review
    - Logout
    """
    hide_default_sidebar_nav()
    with st.sidebar:
        st.markdown("### Doctor Menu")
        if st.button("Patient List", use_container_width=True):
            st.session_state.pop("doctor_filter_status", None)
            st.switch_page("pages/d_patient_list.py")
        if st.button("Waiting for Review", use_container_width=True):
            st.session_state["doctor_filter_status"] = "sent_to_doctor"
            st.switch_page("pages/d_case_list.py")
        st.divider()
        if st.button("Logout", use_container_width=True):
            from core.session_manager import logout
            logout()


def render_patient_sidebar():
    """Render patient sidebar with Logout only, hiding default nav."""
    hide_default_sidebar_nav()
    with st.sidebar:
        if st.button("Logout", use_container_width=True):
            from core.session_manager import logout
            logout()
