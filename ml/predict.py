from ultralytics import YOLO
import numpy as np
from PIL import Image
from .model_loader import load_model


def predict_scan(image_file):
    """
    Core prediction function.
    Returns a dictionary with the top class and a full probability breakdown:
      {"label": str, "confidence": float(0-100), "probabilities": [{label, confidence}% ...]}
    """
    model = load_model()

    image = Image.open(image_file).convert("RGB")
    results = model.predict(image, verbose=False)[0]

    # If the model didn't return probabilities, fall back to Unknown
    if not hasattr(results, "probs") or results.probs is None or len(results.probs) == 0:
        return {"label": "Unknown", "confidence": 0.0, "probabilities": []}

    probs = results.probs.data.cpu().numpy()
    cid = int(np.argmax(probs))
    conf = float(probs[cid])

    # Resolve class names
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        id_to_name = names
    else:
        # names may be a list or missing; build a mapping
        id_to_name = {i: (names[i] if names and i < len(names) else f"class_{i}") for i in range(len(probs))}

    label = id_to_name.get(cid, f"class_{cid}")

    # Build full probability list (percentages) sorted desc
    prob_list = [
        {"label": id_to_name.get(i, f"class_{i}"), "confidence": round(float(p) * 100, 2)}
        for i, p in enumerate(probs)
    ]
    prob_list.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "label": label,
        "confidence": round(conf * 100, 2),
        "probabilities": prob_list,
    }


def run_scan_prediction(image_file):
    """
    Wrapper so imports stay consistent.
    """
    return predict_scan(image_file)
