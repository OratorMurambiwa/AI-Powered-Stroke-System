import json
import re
from uuid import UUID
from typing import Any
from .errors import ClinicalError

ISSUER = "urn:stroke-platform:identity:v1"
ROLES = {"patient", "doctor", "technician", "admin"}

def uuid_id(value: Any) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ClinicalError(400, "invalid_identifier") from None
    return value

def subject_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24}", value):
        raise ClinicalError(400, "invalid_subject")
    return value

def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ClinicalError(400, "invalid_integer")
    return value

def text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ClinicalError(400, "invalid_text")
    return value.strip()

def fields(value: Any, required: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        raise ClinicalError(400, "invalid_contract")
    if type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise ClinicalError(400, "unsupported_contract_version")
    return value

def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def strict_json(raw: bytes) -> Any:
    def invalid_constant(_value: str):
        raise ValueError("invalid JSON constant")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid_constant)
