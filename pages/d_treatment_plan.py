import streamlit as st
import openai
import os
import re
from dotenv import load_dotenv
from core.session_manager import require_role
from core.database import get_db
from models.visit import Visit
from models.patient import Patient
from models.treatment import Treatment
from core.helpers import render_doctor_sidebar


def main():
    require_role("doctor")
    render_doctor_sidebar()

    
    try:
        load_dotenv()
    except Exception:
        pass
    if not getattr(openai, "api_key", None):
        key = os.getenv("OPENAI_API_KEY")
        if key:
            openai.api_key = key

    db = next(get_db())
    visit_id = st.session_state.get("open_visit_id")

    if not visit_id:
        st.error("No visit selected.")
        return

    st.title("AI Treatment Plan")

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    patient = db.query(Patient).filter(Patient.id == visit.patient_id).first()

    st.write("### Patient Summary")
    st.write(f"- **Name:** {patient.name}")
    st.write(f"- **Age:** {patient.age}")
    diag = getattr(visit, "prediction_label", None) or "—"
    st.write(f"- **Diagnosis:** {diag}")
    st.write(f"- **NIHSS:** {visit.nihss_score}")
    st.write(f"- **Eligibility:** {visit.tpa_eligible}")

    # Load existing plan if any
    existing = db.query(Treatment).filter(Treatment.visit_id == visit_id).first()
    if "draft_treatment_plan" not in st.session_state:
        st.session_state["draft_treatment_plan"] = existing.plan_text if existing and existing.plan_text else ""

    # Utilities
    def _severity_from_nihss(score):
        try:
            s = int(score)
        except Exception:
            return "unknown"
        if s <= 5:
            return "mild"
        if s <= 14:
            return "moderate"
        if s <= 24:
            return "severe"
        return "very severe"

    def _sanitize_plain_five_points(text: str) -> str:
        if not text:
            return ""
        # Strip code fences and HTML
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        # Remove common markdown tokens
        text = text.replace("**", "").replace("*", "").replace("##", "").replace("#", "")
        # Try to parse numbered/bulleted lines first
        points = []
        for line in text.splitlines():
            m = re.match(r"^\s*(?:[-*•–]|\d+[\.)])\s+(.+)$", line)
            if m:
                points.append(m.group(1).strip())
        if not points:
            # Fallback: split by sentences
            parts = re.split(r"(?<=[.!?])\s+", text.strip())
            for p in parts:
                if p:
                    points.append(p.strip())
        # Clean markdown emphasis/backticks from points
        clean = []
        for p in points:
            p = re.sub(r"[#*_`]+", "", p)
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                clean.append(p)
            if len(clean) >= 5:
                break
        # Ensure exactly 5 items by truncating or padding with blanks
        clean = clean[:5]
        # Format as numbered 1-5
        return "\n".join(f"{i+1}. {p}" for i, p in enumerate(clean))

    # Reserve place for the editor so it stays above the buttons
    editor_container = st.container()

    # Init UI state
    if "generating_plan" not in st.session_state:
        st.session_state["generating_plan"] = False

    col1, col2, col3 = st.columns(3)

    with col1:
        gen_disabled = bool(st.session_state.get("generating_plan", False))
        if st.button("Generate Treatment Plan", disabled=gen_disabled):
            st.session_state["generating_plan"] = True
            severity = _severity_from_nihss(visit.nihss_score)
            scan_result = (diag or "normal").lower()
            prompt = f"""You are an experienced stroke care physician. Generate a brief, practical treatment plan for the following stroke patient.

Patient Information:
- Name: {patient.name}
- Age: {patient.age} years
- Gender: {patient.gender}

Vital Signs:
- Blood Pressure: {visit.systolic_bp if visit.systolic_bp is not None else 'N/A'}/{visit.diastolic_bp if visit.diastolic_bp is not None else 'N/A'} mmHg
- Heart Rate: {visit.heart_rate if visit.heart_rate is not None else 'N/A'} bpm
- Temperature: {visit.temperature if visit.temperature is not None else 'N/A'}°C
- Oxygen Saturation: {visit.oxygen_saturation if visit.oxygen_saturation is not None else 'N/A'}%

Stroke Assessment:
- NIHSS Score: {visit.nihss_score} ({severity} stroke)
- CT/MRI Scan Result: {scan_result.capitalize()} stroke pattern
- tPA Eligible: {'Yes' if visit.tpa_eligible else 'No'}

Generate exactly 5 concise treatment recommendations. Each point should be actionable and specific to this patient's presentation. Format as a numbered list (1-5) with plain text only - no bold, italics, asterisks, or special formatting. Keep each point to 1-2 sentences maximum. Focus on immediate care priorities, monitoring parameters, and specific interventions based on the scan results and tPA eligibility."""

            try:
                with st.spinner("Generating plan..."):
                    completion = openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert stroke physician providing clear, actionable treatment plans. Use plain text only with no markdown formatting."
                            },
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=500,
                        temperature=0.3,
                    )
                    plan = completion.choices[0].message.content if completion and completion.choices else ""
                plan = _sanitize_plain_five_points(plan)
                st.session_state["draft_treatment_plan"] = plan
                st.success("Draft generated. Review and click Save when ready.")
            except Exception as e:
                st.error(f"Failed to generate plan: {e}")
            finally:
                st.session_state["generating_plan"] = False

    with col2:
        if st.button("Save Treatment Plan"):
            text = (st.session_state.get("draft_treatment_plan") or "").strip()
            if not text:
                st.warning("Plan is empty. Please enter or generate content before saving.")
            else:
                treatment = db.query(Treatment).filter(Treatment.visit_id == visit_id).first()
                if not treatment:
                    treatment = Treatment(visit_id=visit_id)
                treatment.plan_text = text
                db.add(treatment)
                db.commit()
                st.success("Treatment plan saved.")
                st.switch_page("pages/d_view_case.py")

    with col3:
        if st.button("Back"):
            st.switch_page("pages/d_view_case.py")

    # Editor (rendered after handling button actions so latest state is shown)
    with editor_container:
        st.subheader("Plan Editor")
        st.text_area(
            "Edit or paste the treatment plan",
            height=300,
            key="draft_treatment_plan",
        )


if __name__ == "__main__":
    main()
