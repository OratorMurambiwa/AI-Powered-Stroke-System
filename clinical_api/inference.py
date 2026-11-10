"""Narrow, opt-in private worker adapter. No ML imports in the clinical API."""
import base64
import hashlib
import json
import math
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from .identity import NoRedirect
from .errors import ClinicalError
from .validation import strict_json

MODEL_SHA256='200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595'
MODEL_VERSION='medstroke-checkpoint-2025-10-27-ultralytics-8.3.221'
PREPROCESS_VERSION='rgb-resize-short224-bilinear-centercrop224-tensor01-v1'
LABELS=['bleeding','ischemia','normal']

class InferenceAdapter:
    def __init__(self,url,key):
        parts=urlsplit(url)
        if (parts.scheme!='http' or parts.hostname not in {'127.0.0.1','localhost','stroke-inference-worker'}
                or parts.username or parts.password or parts.query or parts.fragment or parts.path!='/api/v1/predict'
                or len(key)!=64 or any(c not in '0123456789abcdef' for c in key)):
            raise ValueError('Explicit private worker URL/key required')
        self.url,self.key=url,key
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def predict(self,raw,scan_sha):
        if hashlib.sha256(raw).hexdigest()!=scan_sha:
            raise ClinicalError(503,'scan_integrity_failure')
        request=Request(self.url,method='POST',data=json.dumps({'schemaVersion':1,'contentBase64':base64.b64encode(raw).decode(),
             'scanSha256':scan_sha,'modelSha256':MODEL_SHA256},separators=(',',':')).encode(),
             headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=24) as response:
                length=response.headers.get('Content-Length','')
                if (response.status!=200 or response.headers.get_content_type()!='application/json'
                        or len(response.headers.get_all('Content-Length',[]))!=1 or response.headers.get('Transfer-Encoding')
                        or not length.isdigit() or not 1<=int(length)<=4096):
                    raise ValueError
                raw_response=response.read(int(length)+1)
                if len(raw_response)!=int(length):
                    raise ValueError
                result=strict_json(raw_response)
                expected={'schemaVersion','predictedClass','rawScore','scores','modelSha256','modelVersion','preprocessingVersion','scanSha256','durationMs'}
                if (not isinstance(result,dict) or set(result)!=expected or type(result['schemaVersion']) is not int or result['schemaVersion']!=1
                        or result['modelSha256']!=MODEL_SHA256 or result['modelVersion']!=MODEL_VERSION
                        or result['preprocessingVersion']!=PREPROCESS_VERSION or result['scanSha256']!=scan_sha
                        or not isinstance(result['scores'],list) or len(result['scores'])!=3):
                    raise ValueError
                scores=result['scores']
                if any(type(x) not in {int,float} or not math.isfinite(x) or not 0<=x<=1 for x in scores) or abs(sum(scores)-1)>0.0001:
                    raise ValueError
                index=max(range(3),key=scores.__getitem__)
                if (result['predictedClass']!=LABELS[index] or type(result['rawScore']) not in {int,float}
                        or result['rawScore']!=scores[index] or type(result['durationMs']) not in {int,float}
                        or not math.isfinite(result['durationMs']) or not 0<=result['durationMs']<=20000):
                    raise ValueError
                return result
        except (HTTPError,URLError,HTTPException,OSError,ValueError,TypeError,KeyError,RecursionError):
            raise ClinicalError(503,'inference_unavailable') from None
