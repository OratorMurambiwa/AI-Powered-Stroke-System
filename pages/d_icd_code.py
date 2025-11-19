import streamlit as st
from core.session_manager import require_role


def main():
    require_role("doctor")
    st.switch_page("pages/d_view_case.py")


if __name__ == "__main__":
    main()
