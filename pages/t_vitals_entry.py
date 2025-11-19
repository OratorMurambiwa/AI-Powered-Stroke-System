import streamlit as st
from datetime import timedelta, timezone
from core.time_utils import now_utc

from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.visit_service import get_visit_by_id, update_visit

# Page config is set globally in app.py

# Role access control
require_role("technician")
render_technician_sidebar()

st.title("Enter Patient Vitals")

# Ensure visit exists
if "current_visit_id" not in st.session_state:
    st.error("No active visit. Please start a new stroke visit first.")
    st.stop()

visit_id = st.session_state["current_visit_id"]
visit = get_visit_by_id(visit_id)

if not visit:
    st.error("Visit not found.")
    st.stop()

st.write("### Enter Vitals")

# Input fields (no min/max constraints)
systolic = st.number_input("Systolic BP", value=int(getattr(visit, "systolic_bp", 0) or 0), step=1)
diastolic = st.number_input("Diastolic BP", value=int(getattr(visit, "diastolic_bp", 0) or 0), step=1)
heart_rate = st.number_input("Heart Rate", value=int(getattr(visit, "heart_rate", 0) or 0), step=1)
resp_rate = st.number_input("Respiratory Rate", value=int(getattr(visit, "respiratory_rate", 0) or 0), step=1)

# Temperature in Fahrenheit. If previous stored value looks like Celsius (<=45), convert for display.
_temp_stored = float(getattr(visit, "temperature", 0.0) or 0.0)
_temp_display = (_temp_stored * 9.0/5.0 + 32.0) if _temp_stored and _temp_stored <= 45.0 else _temp_stored
temperature = st.number_input("Temperature (°F)", value=float(_temp_display), step=0.1, format="%.1f")

oxygen = st.number_input("Oxygen Saturation (%)", value=int(getattr(visit, "oxygen_saturation", 0) or 0), step=1)
glucose = st.number_input("Blood Glucose (mg/dL)", value=float(getattr(visit, "glucose", 0.0) or 0.0), step=0.1, format="%.1f")
inr = st.number_input("INR", value=float(getattr(visit, "inr", 0.0) or 0.0), step=0.1, format="%.1f")

st.write("### Time Since Symptom Onset")
# Prefer duration input (hours + minutes) instead of date/time pickers
existing_onset = getattr(visit, 'onset_time', None)
def _default_duration_from_existing(onset):
    if not onset:
        return 0, 0
    try:
        now = now_utc()
        # Coerce naive datetimes to UTC for safety
        if getattr(onset, 'tzinfo', None) is None:
            onset = onset.replace(tzinfo=timezone.utc)
        if onset > now:
            return 0, 0
        delta = now - onset
        total_minutes = int(delta.total_seconds() // 60)
        hours = max(total_minutes // 60, 0)
        minutes = max(total_minutes % 60, 0)
        return hours, minutes
    except Exception:
        return 0, 0

def _clamp(v, lo, hi):
    try:
        return max(lo, min(int(v), hi))
    except Exception:
        return lo

def _hours_minutes_inputs(default_h: int, default_m: int):
    c1, c2 = st.columns(2)
    with c1:
        hours = st.number_input("Hours", min_value=0, max_value=168, value=int(default_h), step=1)
    with c2:
        minutes = st.number_input("Minutes", min_value=0, max_value=59, value=int(default_m), step=1)
    return _clamp(hours, 0, 168), _clamp(minutes, 0, 59)

_def_h, _def_m = _default_duration_from_existing(existing_onset)
hours_since_onset, minutes_since_onset = _hours_minutes_inputs(_def_h, _def_m)

if st.button("Save Vitals", type="primary"):
    # Convert duration (hours, minutes) to an onset datetime relative to now
    onset_dt = None
    try:
        total_minutes = int(hours_since_onset) * 60 + int(minutes_since_onset)
        if total_minutes > 0:
            onset_dt = now_utc() - timedelta(minutes=total_minutes)
    except Exception:
        onset_dt = None

    update_visit(
        visit_id,
        systolic_bp=systolic,
        diastolic_bp=diastolic,
        heart_rate=heart_rate,
        respiratory_rate=resp_rate,
        temperature=temperature,
        oxygen_saturation=oxygen,
        glucose=glucose,
        inr=inr,
        onset_time=onset_dt,
    )

    st.success("Vitals saved successfully.")
    st.switch_page("pages/t_nihss_page.py")
