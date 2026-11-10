"""Public signup cannot provision clinical or administrative privileges."""

def require_patient_registration(role: str) -> None:
    if role != "patient":
        raise ValueError("Staff accounts must be provisioned by an authorized operator.")
