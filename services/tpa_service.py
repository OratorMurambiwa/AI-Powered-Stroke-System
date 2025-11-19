from sqlalchemy.orm import Session
from models.visit import Visit
from datetime import datetime, timedelta, timezone
from core.database import get_db_context
from core.time_utils import now_utc


"""
Full tPA Eligibility Service
---------------------------------
Returns:
{
    "eligible": True/False/None,  # None => indeterminate (e.g., imaging required)
    "reason": "Explanation..."
}
"""


# ---------------------------------------------------------
# Helper: Hours difference between onset time & now
# ---------------------------------------------------------
def _hours_since_onset(onset_time: datetime):
    if not onset_time:
        return None
    now = now_utc()
    # If onset_time is naive, assume it was recorded in UTC and make it aware.
    if getattr(onset_time, 'tzinfo', None) is None:
        onset_time = onset_time.replace(tzinfo=timezone.utc)
    return (now - onset_time).total_seconds() / 3600



# ---------------------------------------------------------
# Main Eligibility Function
# ---------------------------------------------------------
def evaluate_tpa_eligibility(db: Session, visit_id: int):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        return {"eligible": False, "reason": "Visit not found."}

    reasons = []

    # ---------------------------------------
    # 1. TIME SINCE ONSET
    # ---------------------------------------
    hours = _hours_since_onset(getattr(visit, 'onset_time', None))

    if hours is None:
        return {"eligible": False, "reason": "Time since onset not recorded."}

    if hours > 4.5:
        reasons.append(f"Time since onset is {hours:.1f} hours (above 4.5h window).")
        return {"eligible": False, "reason": "\n".join(reasons)}

    # ---------------------------------------
    # 2. IMAGING AVAILABILITY + SCREEN FOR HEMORRHAGE
    # ---------------------------------------
    # If imaging is not available we cannot make a definitive tPA decision.
    # Return an indeterminate result (eligible=None) so the UI can show
    # that imaging is required rather than falsely marking the patient
    # as ineligible.
    if not getattr(visit, 'scan_path', None):
        # Use a clear, clinician-friendly reason when no scan was uploaded
        reasons.append("No scan available to confirm type of stroke.")
        return {"eligible": None, "reason": "\n".join(reasons)}

    # If ML model provided a classification, screen for hemorrhage/bleeding
    if getattr(visit, 'prediction_label', None):
        label = visit.prediction_label.lower()
        hemorrhage_terms = [
            "hemorrhage", "bleeding", "intracerebral", "ich", "intraparenchymal", "subarachnoid"
        ]
        if any(term in label for term in hemorrhage_terms):
            reasons.append("Imaging indicates intracranial hemorrhage/bleeding — tPA contraindicated.")
            return {"eligible": False, "reason": "\n".join(reasons)}

    # ---------------------------------------
    # 3. NIHSS SCORE CHECK
    # ---------------------------------------
    if visit.nihss_score is None:
        return {"eligible": False, "reason": "NIHSS score missing — cannot evaluate."}

    if visit.nihss_score < 4:
        return {"eligible": False, "reason": f"NIHSS score {visit.nihss_score} is too low (<4)."}

    if visit.nihss_score > 25:
        reasons.append(f"NIHSS score {visit.nihss_score} is very high (>25) — tPA risk elevated.")
        # Not auto-fail — physician final decision

    # ---------------------------------------
    # 4. VITAL SIGNS CHECKS
    # ---------------------------------------
    if visit.systolic_bp and visit.systolic_bp > 185:
        reasons.append(f"Systolic BP {visit.systolic_bp} is above 185 mmHg.")
        return {"eligible": False, "reason": "\n".join(reasons)}

    if visit.diastolic_bp and visit.diastolic_bp > 110:
        reasons.append(f"Diastolic BP {visit.diastolic_bp} is above 110 mmHg.")
        return {"eligible": False, "reason": "\n".join(reasons)}

    if visit.inr and visit.inr > 1.7:
        reasons.append(f"INR {visit.inr} is > 1.7 (bleeding risk too high).")
        return {"eligible": False, "reason": "\n".join(reasons)}

    if visit.glucose and (visit.glucose < 50 or visit.glucose > 400):
        reasons.append(f"Glucose {visit.glucose} mg/dL is outside safe tPA range (50–400).")
        return {"eligible": False, "reason": "\n".join(reasons)}

    # ---------------------------------------
    # 5. Additional contraindications (e.g., pregnancy) could be checked via Patient data
    # Skipped here as Visit model does not contain these fields.

    # ---------------------------------------
    # 6. FINAL DECISION
    # ---------------------------------------
    if len(reasons) == 0:
        return {
            "eligible": True,
            "reason": "All criteria met. Patient is eligible for tPA."
        }

    return {
        "eligible": False,
        "reason": "\n".join(reasons)
    }


def run_tpa_eligibility(visit_id: int):
    """Convenience wrapper for pages to run eligibility without a DB session."""
    with get_db_context() as db:
        return evaluate_tpa_eligibility(db, visit_id)
