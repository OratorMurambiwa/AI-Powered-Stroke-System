"""Explicitly trusted fingerprint only; no legacy YOLO loader or unsafe fallback."""
import hashlib
import io
import os
from pathlib import Path

MODEL_SHA256 = '200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595'
MODEL_VERSION = 'medstroke-checkpoint-2025-10-27-ultralytics-8.3.221'
PREPROCESS_VERSION = 'rgb-resize-short224-bilinear-centercrop224-tensor01-v1'
LABELS = {0:'bleeding',1:'ischemia',2:'normal'}

def load():
    path = Path('/artifact/MedStroke.pt')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as stream:
        raw = stream.read(3000001)
    if len(raw) != 2966344 or hashlib.sha256(raw).hexdigest() != MODEL_SHA256:
        raise ValueError('model_fingerprint_mismatch')
    import torch
    from torch import nn
    from torchvision.transforms import Compose, Resize, CenterCrop, ToTensor, Normalize, InterpolationMode
    from ultralytics.nn.tasks import ClassificationModel
    from ultralytics.nn.modules import Conv, C2f, Bottleneck, Classify
    allowed = [set,nn.SiLU,nn.BatchNorm2d,nn.ModuleList,nn.Sequential,nn.Conv2d,nn.Dropout,nn.Linear,
               nn.AdaptiveAvgPool2d,Compose,Resize,CenterCrop,ToTensor,Normalize,InterpolationMode,
               ClassificationModel,Conv,C2f,Bottleneck,Classify]
    with torch.serialization.safe_globals(allowed):
        checkpoint = torch.load(io.BytesIO(raw),map_location='cpu',weights_only=True)
    model = checkpoint['model']
    if type(model) is not ClassificationModel or checkpoint['version'] != '8.3.221' or model.names != LABELS:
        raise ValueError('model_metadata_mismatch')
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    return model.float().cpu().eval()

def predict(raw):
    from clinical_api.png import validate_png
    validate_png(raw)
    import torch
    from PIL import Image
    from torchvision.transforms import Compose, Resize, CenterCrop, ToTensor, InterpolationMode
    model = load()
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    tensor = Compose([Resize(224,interpolation=InterpolationMode.BILINEAR,antialias=True),CenterCrop(224),ToTensor()])(image).unsqueeze(0)
    with torch.inference_mode():
        output = model(tensor)
    probabilities = output[0] if isinstance(output,tuple) else output
    values = probabilities[0].tolist()
    if len(values) != 3 or any(not 0 <= x <= 1 for x in values) or abs(sum(values)-1) > 0.0001:
        raise ValueError('invalid_model_output')
    index = max(range(3),key=values.__getitem__)
    return {'predictedClass':LABELS[index],'rawScore':values[index],'scores':values,
            'modelSha256':MODEL_SHA256,'modelVersion':MODEL_VERSION,'preprocessingVersion':PREPROCESS_VERSION}
