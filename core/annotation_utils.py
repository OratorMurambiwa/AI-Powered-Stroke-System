import os
import hashlib
import glob
from typing import Tuple, List

from core.database import BASE_DIR

ANNOTATION_DIR = os.path.join(BASE_DIR, "data", "uploads", "annotations")

def ensure_annotation_dir() -> str:
    os.makedirs(ANNOTATION_DIR, exist_ok=True)
    return ANNOTATION_DIR

def _scan_hash(scan_path: str | None) -> str:
    if not scan_path:
        return "nohash"
    try:
        h = hashlib.md5(scan_path.encode()).hexdigest()
        return h[:12]
    except Exception:
        return "nohash"

def get_annotation_paths(visit) -> Tuple[str, str]:
    """Return (img_path, json_path) for the current visit & scan.

    Filenames are unique per patient + visit + scan path hash to prevent
    collisions when visit IDs repeat or scans change.
    """
    ensure_annotation_dir()
    patient_code = getattr(getattr(visit, "patient", None), "patient_id", "PUNK")
    scan_hash = _scan_hash(getattr(visit, "scan_path", None))
    base_name = f"ann_{patient_code}_{visit.visit_id}_{scan_hash}"
    return (
        os.path.join(ANNOTATION_DIR, base_name + ".png"),
        os.path.join(ANNOTATION_DIR, base_name + ".json"),
    )

def list_all_visit_annotation_files(visit) -> List[str]:
    """List all annotation files (legacy + hashed) for a visit regardless of scan hash."""
    ensure_annotation_dir()
    patient_code = getattr(getattr(visit, "patient", None), "patient_id", "PUNK")
    legacy_png = os.path.join(ANNOTATION_DIR, f"visit_{visit.id}.png")
    legacy_json = os.path.join(ANNOTATION_DIR, f"visit_{visit.id}.json")
    pattern = os.path.join(ANNOTATION_DIR, f"ann_{patient_code}_{visit.visit_id}_*.png")
    pattern_json = os.path.join(ANNOTATION_DIR, f"ann_{patient_code}_{visit.visit_id}_*.json")
    files = []
    files.extend(glob.glob(pattern))
    files.extend(glob.glob(pattern_json))
    if os.path.exists(legacy_png):
        files.append(legacy_png)
    if os.path.exists(legacy_json):
        files.append(legacy_json)
    return files

def delete_all_visit_annotations(visit) -> int:
    """Delete all annotation files for a visit (legacy + hashed).
    Returns count of deleted files.
    """
    deleted = 0
    for f in list_all_visit_annotation_files(visit):
        try:
            os.remove(f)
            deleted += 1
        except Exception:
            pass
    return deleted
