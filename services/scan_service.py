import os
import uuid
from pathlib import Path
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from models.visit import Visit
from services.tpa_service import evaluate_tpa_eligibility
from core.database import get_db_context
from core.annotation_utils import delete_all_visit_annotations
_ML_AVAILABLE = True
try:
    # Try lightweight import to detect if ML stack is available.
    from ml.predict import predict_scan  # type: ignore
except Exception:
    predict_scan = None  # type: ignore
    _ML_AVAILABLE = False


# Base folder where scans are stored
UPLOAD_DIR = Path("data/uploads")


def _ensure_upload_dir_exists() -> None:
    """
    Make sure the uploads directory exists.

    This runs every time we save a scan, just in case.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_uploaded_scan(uploaded_file) -> str:
    """
    Save the uploaded scan file to disk and return the file path.

    Parameters
    ----------
    uploaded_file : file-like
        The object returned by Streamlit's st.file_uploader (has .name and .read()).

    Returns
    -------
    str
        Path to the saved scan file (relative to project root).
    """
    _ensure_upload_dir_exists()

    # Get extension from original file name, default to .png if missing
    original_name = uploaded_file.name or "scan.png"
    ext = os.path.splitext(original_name)[1] or ".png"

    # Generate a unique file name so we do not overwrite anything
    filename = f"scan_{uuid.uuid4().hex}{ext}"
    dest_path = UPLOAD_DIR / filename

    # Save bytes to disk
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.read())

    # Return string path (you can store this directly in the DB)
    return str(dest_path)


def run_model_on_scan(scan_path: str) -> Tuple[str, float, list]:
    """
    Run the ML model on the saved scan and return (label, confidence).

    Parameters
    ----------
    scan_path : str
        Path to the scan image on disk.

    Returns
    -------
    (label, confidence)
        label: predicted class label as a string
        confidence: prediction confidence as a float between 0 and 1
    """
    # If ML stack is unavailable (e.g., missing NumPy/PyTorch), return
    # empty prediction values rather than raising — the UI can still show
    # the uploaded scan and allow manual review.
    if not _ML_AVAILABLE or predict_scan is None:
        return None, None, []

    try:
        result = predict_scan(scan_path)
        label = result.get("label")
        confidence = result.get("confidence")
        probabilities = result.get("probabilities", [])
        return label, confidence, probabilities
    except Exception:
        # On any runtime failure inside the model/predict code, do not
        # raise — return empty prediction so the caller can continue.
        return None, None, []


def process_scan_for_visit(db: Session, visit_id: int, uploaded_file) -> Dict:
    """
    Full pipeline for handling an uploaded scan for a given visit.

    Steps:
    1. Fetch the Visit row.
    2. Save the uploaded scan to disk.
    3. Run the ML model to get diagnosis + confidence.
    4. Evaluate tPA eligibility using tpa_service.
    5. Update and commit the Visit row.
    6. Return a result dict for the UI.

    Parameters
    ----------
    db : Session
        SQLAlchemy session.
    visit_id : int
        ID of the Visit record.
    uploaded_file : file-like
        The uploaded scan file from Streamlit.

    Returns
    -------
    dict
        {
          "visit_id": int,
          "scan_path": str,
          "prediction": str,
          "confidence": float,
          "tpa_eligible": bool,
          "tpa_reason": str,
        }

    Raises
    ------
    ValueError
        If the visit is not found or the file is missing.
    """
    if uploaded_file is None:
        raise ValueError("No scan file provided.")

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        raise ValueError(f"Visit with id {visit_id} not found.")

    # 1) Save scan to disk
    scan_path = save_uploaded_scan(uploaded_file)

    # 2) Run ML model (may return None values if the ML stack is unavailable)
    prediction_label, prediction_conf, probabilities = run_model_on_scan(scan_path)

    # 3) Update visit with scan and ML outputs
    old_scan_path = getattr(visit, 'scan_path', None)
    visit.scan_path = scan_path
    # Map to Visit model fields
    visit.prediction_label = prediction_label
    visit.prediction_confidence = prediction_conf

    db.commit()
    db.refresh(visit)

    # Delete old annotations if scan path changed
    if old_scan_path and old_scan_path != scan_path:
        delete_all_visit_annotations(visit)

    # 4) Evaluate tPA eligibility based on updated visit
    tpa_result = evaluate_tpa_eligibility(db, visit.id)

    # Only persist a definitive eligible flag when evaluate_tpa_eligibility
    # returns True/False. If it returns None (indeterminate due to missing
    # imaging), persist only the reason and leave tpa_eligible unset.
    if tpa_result.get("eligible") is None:
        visit.tpa_reason = tpa_result.get("reason", "")
    else:
        visit.tpa_eligible = tpa_result.get("eligible", False)
        visit.tpa_reason = tpa_result.get("reason", "")
    # Optional: mark status to show this visit is processed
    if not visit.status:
        visit.status = "analysis_completed"

    db.commit()
    db.refresh(visit)

    # 5) Build clean response for the UI
    return {
        "visit_id": visit.id,
        "scan_path": visit.scan_path,
        "prediction": visit.prediction_label,
        "confidence": float(visit.prediction_confidence or 0.0),
        "probabilities": probabilities,
        "tpa_eligible": bool(visit.tpa_eligible),
        "tpa_reason": visit.tpa_reason or "",
    }


def process_scan(visit_id: int, file) -> Dict:
    """
    Convenience wrapper used by Streamlit pages: opens a DB session
    and calls `process_scan_for_visit`.

    Keeps the page code simple: `process_scan(visit_id=..., file=uploaded_file)`
    """
    with get_db_context() as db:
        return process_scan_for_visit(db, visit_id, file)
