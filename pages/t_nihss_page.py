import streamlit as st

from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.nihss_service import calculate_nihss, save_nihss_scores
from core.database import get_db_context
from services.visit_service import get_visit_by_id, update_visit

# Page config is set globally in app.py

require_role("technician")
render_technician_sidebar()

st.title("NIHSS (Stroke Severity) Scoring")

# Subtle styling to make radios look like the provided example
st.markdown(
    """
    <style>
    /* Larger, clearer section headings */
    .nihss-head { font-size: 1.25rem; font-weight: 700; margin: 0.6rem 0 0.25rem 0; display: block; }
    .nihss-help { color: #999; margin-bottom: 0.5rem; }

    /* Force radio options onto a single horizontal line with scrolling if needed */
    .stRadio > label { font-weight: 600; }
    .stRadio div[role="radiogroup"] {
        display: flex; flex-wrap: nowrap; gap: 0.75rem; align-items: center; overflow-x: auto;
        padding-bottom: 0.25rem;
    }
    .stRadio div[role="radiogroup"] label { white-space: nowrap; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Ensure visit exists
if "current_visit_id" not in st.session_state:
    st.error("No active visit. Please start a new stroke visit.")
    st.stop()

visit_id = st.session_state["current_visit_id"]
visit = get_visit_by_id(visit_id)

if not visit:
    st.error("Visit not found.")
    st.stop()


st.write("### Complete NIHSS Form")
st.info("Choose an option for each item, then click Calculate.")

# NIHSS Components
def radio_with_labels(title: str, options: list[int], labels: dict[int, str], key: str, help_text: str | None = None):
    st.markdown(f"<span class='nihss-head'>{title}</span>", unsafe_allow_html=True)
    if help_text:
        st.markdown(f"<div class='nihss-help'>{help_text}</div>", unsafe_allow_html=True)
    return st.radio(
        label=" ",
        options=options,
        index=0,
        key=key,
        format_func=lambda v: f"{v} - {labels.get(v, '')}",
        horizontal=True,
    )

loc = radio_with_labels(
    "1a. Level of Consciousness",
    [0, 1, 2, 3],
    {0: "Alert", 1: "Drowsy", 2: "Stuporous", 3: "Coma"},
    key="nihss_loc",
    help_text="Assess the patient's level of consciousness",
)
loc_questions = radio_with_labels(
    "1b. LOC Questions",
    [0, 1, 2],
    {0: "Answers both correctly", 1: "Answers one correctly", 2: "Answers neither"},
    key="nihss_locq",
    help_text="Ask month and age",
)
loc_commands = radio_with_labels(
    "1c. LOC Commands",
    [0, 1, 2],
    {0: "Performs both", 1: "Performs one", 2: "Performs none"},
    key="nihss_locc",
    help_text="Open/close eyes, make a fist",
)

gaze = radio_with_labels(
    "2. Best Gaze",
    [0, 1, 2],
    {0: "Normal", 1: "Partial gaze palsy", 2: "Forced deviation"},
    key="nihss_gaze",
    help_text="Test horizontal eye movement",
)
visual = radio_with_labels(
    "3. Visual Field",
    [0, 1, 2, 3],
    {0: "No visual loss", 1: "Partial hemianopia", 2: "Complete hemianopia", 3: "Bilateral hemianopia"},
    key="nihss_visual",
    help_text="Confrontation testing",
)
facial = radio_with_labels(
    "4. Facial Palsy",
    [0, 1, 2, 3],
    {0: "Normal", 1: "Minor", 2: "Partial", 3: "Complete"},
    key="nihss_facial",
    help_text="Show teeth, raise eyebrows",
)

motor_arm_left = radio_with_labels(
    "5a. Motor Arm Left",
    [0, 1, 2, 3, 4],
    {0: "No drift", 1: "Drift", 2: "Cannot resist", 3: "No effort against gravity", 4: "No movement"},
    key="nihss_arm_l",
    help_text="Hold at 90° for 10s",
)
motor_arm_right = radio_with_labels(
    "5b. Motor Arm Right",
    [0, 1, 2, 3, 4],
    {0: "No drift", 1: "Drift", 2: "Cannot resist", 3: "No effort against gravity", 4: "No movement"},
    key="nihss_arm_r",
    help_text="Hold at 90° for 10s",
)

motor_leg_left = radio_with_labels(
    "6a. Motor Leg Left",
    [0, 1, 2, 3, 4],
    {0: "No drift", 1: "Drift", 2: "Cannot resist", 3: "No effort", 4: "No movement"},
    key="nihss_leg_l",
    help_text="Hold at 30° for 5s",
)
motor_leg_right = radio_with_labels(
    "6b. Motor Leg Right",
    [0, 1, 2, 3, 4],
    {0: "No drift", 1: "Drift", 2: "Cannot resist", 3: "No effort", 4: "No movement"},
    key="nihss_leg_r",
    help_text="Hold at 30° for 5s",
)

limb_at = radio_with_labels(
    "7. Limb Ataxia",
    [0, 1, 2],
    {0: "Absent", 1: "One limb", 2: "Two limbs"},
    key="nihss_ataxia",
    help_text="Finger-nose-finger / heel-shin",
)
sensory = radio_with_labels(
    "8. Sensory",
    [0, 1, 2],
    {0: "Normal", 1: "Mild loss", 2: "Severe loss"},
    key="nihss_sensory",
    help_text="Pinprick sensation",
)

language = radio_with_labels(
    "9. Best Language",
    [0, 1, 2, 3],
    {0: "Normal", 1: "Mild aphasia", 2: "Severe aphasia", 3: "Mute"},
    key="nihss_language",
    help_text="Comprehension and expression",
)
dysarthria = radio_with_labels(
    "10. Dysarthria",
    [0, 1, 2],
    {0: "Normal", 1: "Mild", 2: "Severe"},
    key="nihss_dysarthria",
    help_text="Speech clarity",
)

extinction = radio_with_labels(
    "11. Extinction / Neglect",
    [0, 1, 2],
    {0: "Normal", 1: "Partial neglect", 2: "Complete neglect"},
    key="nihss_extinction",
    help_text="Double simultaneous stimulation",
)

if st.button("Calculate NIHSS Score", type="primary"):

    # Package values for scoring
    stroke_data = {
        "loc": loc,
        "loc_questions": loc_questions,
        "loc_commands": loc_commands,
        "gaze": gaze,
        "visual": visual,
        "facial": facial,
        "motor_arm_left": motor_arm_left,
        "motor_arm_right": motor_arm_right,
        "motor_leg_left": motor_leg_left,
        "motor_leg_right": motor_leg_right,
        "limb_at": limb_at,
        "sensory": sensory,
        "language": language,
        "dysarthria": dysarthria,
        "extinction": extinction
    }

    nihss_total = calculate_nihss(stroke_data)

    # Save individual NIHSS category values to DB (service normalises keys)
    nihss_scores = {
        "consciousness": (
            stroke_data.get("loc", 0)
            + stroke_data.get("loc_questions", 0)
            + stroke_data.get("loc_commands", 0)
        ),
        "gaze": stroke_data.get("gaze", 0),
        "visual": stroke_data.get("visual", 0),
        "facial": stroke_data.get("facial", 0),
        "motor_arm_left": stroke_data.get("motor_arm_left", 0),
        "motor_arm_right": stroke_data.get("motor_arm_right", 0),
        "motor_leg_left": stroke_data.get("motor_leg_left", 0),
        "motor_leg_right": stroke_data.get("motor_leg_right", 0),
        "ataxia": stroke_data.get("limb_at", 0),
        "sensory": stroke_data.get("sensory", 0),
        "language": stroke_data.get("language", 0),
        "dysarthria": stroke_data.get("dysarthria", 0),
        "extinction": stroke_data.get("extinction", 0),
    }

    with get_db_context() as db:
        save_nihss_scores(db, visit_id, nihss_scores)

    # Update visit NIHSS score (also saved above by save_nihss_scores)
    update_visit(visit_id, nihss_score=nihss_total)

    # Persist state for post-calc buttons/render
    st.session_state["nihss_calculated"] = True
    st.session_state["nihss_total"] = nihss_total

    st.success(f"NIHSS Score Saved Successfully: {nihss_total}")

# After calculation, show decision buttons
if st.session_state.get("nihss_calculated"):
    st.markdown("### Next Steps")
    st.info(f"Calculated NIHSS Score: {st.session_state.get('nihss_total', '')}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Upload Scan", type="primary", key="btn_upload_scan"):
            st.switch_page("pages/t_upload_scan.py")
    with col2:
        if st.button("Skip Scan Upload (Review & Send)", key="btn_skip_scan"):
            st.switch_page("pages/t_review_and_send.py")
