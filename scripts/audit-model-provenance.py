"""Static source audit only; never execute notebook cells or inspect stored outputs/data."""
import hashlib,json,subprocess
from pathlib import Path

def main():
    raw=subprocess.check_output(['git','show','af6fbf7:MedStroke.ipynb'])
    notebook=json.loads(raw)
    sources={i:''.join(c.get('source',[])) for i,c in enumerate(notebook['cells']) if c['cell_type']=='code'}
    assert 'ozguraslank/brain-stroke-ct-dataset' in sources[4]
    assert all("random.shuffle(imgs)" in sources[i] for i in [9,14])
    assert 'epochs=20' in sources[16] and 'imgsz=224' in sources[16]
    result={'schemaVersion':1,'sourceCommit':'af6fbf7ca5cf9fbfaefa0320d178f5a73a1ca20d',
       'notebookSha256':hashlib.sha256(raw).hexdigest(),'sourceCellSha256':{str(i):hashlib.sha256(sources[i].encode()).hexdigest() for i in [4,9,14,16,19,21,22,23]},
       'trainingDataLead':'ozguraslank/brain-stroke-ct-dataset','split':'image-level 70/15/15, random.seed(42); filesystem listing not sorted; no patient/study grouping in split code',
       'trainingCommand':{'architecture':'yolov8n-cls.pt','epochs':20,'imgsz':224},
       'checkpointLinkVerified':False,'independentTestManifestAvailable':False,
       'clinicalMetrics':{'accuracy':None,'precision':None,'recall':None,'f1':None,'confusionMatrix':None},
       'reason':'No verified checkpoint training manifest, immutable dataset version/hash, patient-grouped split or independent approved labeled test cohort.',
       'notebookExecuted':False,'notebookOutputsInspected':False,'patientFilesInspected':False}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
