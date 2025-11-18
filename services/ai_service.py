"""
AI Treatment Plan Generator

Uses OpenAI (or any LLM) to generate a clinical treatment plan
based on the Visit + Patient info.
"""

import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy.orm import Session
import openai
from models.visit import Visit
from models.patient import Patient
from models.treatment import Treatment


# Load .env so OPENAI_API_KEY is available even when running via Streamlit
try:
    load_dotenv()
except Exception:
    pass
openai.api_key = os.getenv("OPENAI_API_KEY")


def generate_treatment_plan(db: Session, visit_id: int) -> dict:
    """
    Build a clinical treatment plan using LLM (OpenAI).
    Saves the plan to DB and returns it.
    """

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        raise ValueError("Visit not found")

    patient = db.query(Patient).filter(Patient.id == visit.patient_id).first()
    if not patient:
        raise ValueError("Patient not found")

    # Severity helper
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

    severity = _severity_from_nihss(visit.nihss_score)
    scan_result = (visit.prediction_label or "normal").lower()

    # Build the prompt blending patient + visit context
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

    # Call the model
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

    plan_text = completion.choices[0].message["content"]

    # Sanitize to plain text with max five concise points
    def _sanitize_plain_five_points(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("**", "").replace("*", "").replace("##", "").replace("#", "")
        points = []
        for line in text.splitlines():
            m = re.match(r"^\s*(?:[-*•–]|\d+[\.)])\s+(.+)$", line)
            if m:
                points.append(m.group(1).strip())
        if not points:
            parts = re.split(r"(?<=[.!?])\s+", text.strip())
            for p in parts:
                if p:
                    points.append(p.strip())
        clean = []
        for p in points:
            p = re.sub(r"[#*_`]+", "", p)
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                clean.append(p)
            if len(clean) >= 5:
                break
        clean = clean[:5]
        return "\n".join(f"{i+1}. {p}" for i, p in enumerate(clean))

    plan_text = _sanitize_plain_five_points(plan_text)

    # Save to database
    t = Treatment(
        visit_id=visit_id,
        plan_text=plan_text
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    return {
        "visit_id": visit_id,
        "icd_code": visit.icd_code,
        "treatment_plan": t.plan_text
    }
