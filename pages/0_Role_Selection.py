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
