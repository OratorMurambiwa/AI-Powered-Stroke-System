from sqlalchemy.orm import Session
from models.visit import Visit


# -----------------------------------------------------
# NIHSS scoring categories (13 items)
# -----------------------------------------------------
NIHSS_FIELDS = [
    "consciousness",
    "gaze",
    "visual",
    "facial",
    "motor_arm_left",
    "motor_arm_right",
    "motor_leg_left",
    "motor_leg_right",
    "ataxia",
    "sensory",
    "language",
    "dysarthria",
    "extinction"
]


# -----------------------------------------------------
# Save or update NIHSS scores for a stroke visit
# -----------------------------------------------------
def save_nihss_scores(db: Session, visit_id: int, scores: dict):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        return None, "Visit not found"

    # Validate keys
    for key in scores.keys():
        if key not in NIHSS_FIELDS:
            return None, f"Invalid NIHSS field: {key}"

    # Assign individual NIHSS categories
    for field in NIHSS_FIELDS:
        setattr(visit, field, scores.get(field, 0))

    # Recalculate total
    visit.nihss_score = sum(scores.get(field, 0) for field in NIHSS_FIELDS)

    db.commit()
    db.refresh(visit)

    return visit, None


# -----------------------------------------------------
# Get NIHSS details for a visit
# -----------------------------------------------------
def get_nihss(db: Session, visit_id: int):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        return None

    return {
        "visit_id": visit.id,
        "nihss_total": visit.nihss_score,
        "details": {
            field: getattr(visit, field)
            for field in NIHSS_FIELDS
        }
    }


def calculate_nihss(data: dict) -> int:
    """
    Calculate NIHSS total from a dictionary of UI fields.

    UI fields expected:
      - loc, loc_questions, loc_commands (sum -> consciousness)
      - gaze, visual, facial
      - motor_arm_left, motor_arm_right, motor_leg_left, motor_leg_right
      - limb_at (maps to 'ataxia'), sensory, language, dysarthria, extinction
    """

    # Consciousness is the sum of the 3 LOC fields
    consciousness = (
        data.get("loc", 0)
        + data.get("loc_questions", 0)
        + data.get("loc_commands", 0)
    )

    mapping_fields = [
        "gaze",
        "visual",
        "facial",
        "motor_arm_left",
        "motor_arm_right",
        "motor_leg_left",
        "motor_leg_right",
        "ataxia",
        "sensory",
        "language",
        "dysarthria",
        "extinction",
    ]

    total = consciousness
    for f in mapping_fields:
        # UI uses "limb_at" for ataxia so allow that alias
        if f == "ataxia":
            total += data.get("limb_at", 0)
        else:
            total += data.get(f, 0)

    return int(total)
