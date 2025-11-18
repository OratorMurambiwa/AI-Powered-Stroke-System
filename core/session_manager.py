import streamlit as st


def init_session_state():
    """Ensure required session keys exist."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "role" not in st.session_state:
        st.session_state.role = None


def login(user):
    """Persist logged-in user object and role."""
    st.session_state.user = user
    st.session_state.role = user.role


def logout():
    """Clear session and redirect to main app page."""
    # Clear session data
    st.session_state.pop("user", None)
    st.session_state.pop("role", None)
    
    # Clear query parameters
    try:
        st.query_params.clear()
    except Exception:
        pass
    
    # Redirect to main page
    st.switch_page("app.py")


def clear_session():
    """Clear session without redirect."""
    st.session_state.pop("user", None)
    st.session_state.pop("role", None)


def require_role(role: str):
    """Restrict page by role; send unauthorized users to app.py.

    Accepts doctor/physician as equivalent roles for access control.
    """
    init_session_state()

    # Check if user is logged in
    if st.session_state.user is None:
        st.warning("Please log in to access this page.")
        st.switch_page("app.py")

    # Role checking with synonyms
    requested = (role or "").strip().lower()
    current = (st.session_state.role or "").strip().lower()

    if requested in {"doctor", "physician"}:
        allowed = {"doctor", "physician"}
    else:
        allowed = {requested}

    if current not in allowed:
        st.error(f" Access denied. This page requires '{role}' role.")
        st.switch_page("app.py")