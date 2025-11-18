"""
ICD Code Lookup Service using the National Library of Medicine API.
"""

import requests
from sqlalchemy.orm import Session
from models.visit import Visit


def fetch_icd10_from_api(query: str) -> dict:
    """
    Calls the clinicaltables API to fetch ICD-10 codes.
    """

    url = (
        "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
        f"?sf=code,name&terms={query}"
    )

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except Exception as e:
        return {"error": f"API request failed: {str(e)}"}

    data = response.json()

    # Data format:
    # [ total_count, [ codes ], [ names ] ]
    if len(data) < 3 or not data[1]:
        return {"error": "No ICD-10 matches found"}

    codes = data[1]
    descriptions = data[2]

    # Take the first/best match
    return {
        "icd_code": codes[0],
        "description": descriptions[0]
    }


def generate_icd_code(db: Session, visit_id: int) -> dict:
    """
    Generate ICD-10 code using real NLM API.
    Saves the code into Visit.icd_code.
    """

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        raise ValueError("Visit not found")

    diagnosis = visit.prediction_label or "stroke"

    # Search using model diagnosis
    result = fetch_icd10_from_api(diagnosis)

    if "error" in result:
        # fallback search using broader term
        result = fetch_icd10_from_api("stroke")

        if "error" in result:
            final_code = "R69"
            final_desc = "Illness, unspecified"
        else:
            final_code = result["icd_code"]
            final_desc = result["description"]

    else:
        final_code = result["icd_code"]
        final_desc = result["description"]

    # Save to DB
    visit.icd_code = final_code
    db.commit()
    db.refresh(visit)

    return {
        "visit_id": visit_id,
        "icd_code": final_code,
        "description": final_desc
    }
