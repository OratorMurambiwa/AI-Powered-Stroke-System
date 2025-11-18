import os
from ultralytics import YOLO

_model = None


def load_model():
    """Load YOLO model only once."""
    global _model
    if _model is None:
        model_path = os.path.join(os.path.dirname(__file__), "MedStroke.pt")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at {model_path}")
        _model = YOLO(model_path)
    return _model


def get_model():
    """Alias to load_model() for compatibility."""
    return load_model()
