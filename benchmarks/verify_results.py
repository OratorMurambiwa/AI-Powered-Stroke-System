"""Validate committed synthetic measurement arithmetic and exact output parity."""
import json
from pathlib import Path
from benchmarks.statistics import summary

def main():
    root=Path('docs/performance/runs');baseline=None;runs=0;jobs=0
    for folder in sorted(root.iterdir()):
        if not (folder/'model.json').exists():continue
        data=json.loads((folder/'model.json').read_text());conditions=json.loads((folder/'conditions.json').read_text())
        assert conditions['complete'] and data['syntheticOnly'] and len(data['samples'])==30
        elapsed=data['elapsedSeconds'];values=[s['roundTripMs'] for s in data['samples']]
        assert data['roundTrip']==summary(values,elapsed)
        assert data['workerJob']==summary([s['workerJobMs'] for s in data['samples']])
        assert data['memoryAfter']['peakBytes']>=data['sampledPeakBytes']
        if baseline is None:baseline=data['outputs']
        assert data['outputs']==baseline,'changed predictions'
        ipc=json.loads((folder/'ipc.json').read_text())
        assert ipc['lineRead']['n']==200
        expected=folder.name.startswith('baseline')
        if folder.name=='final-security-1':
            assert not ipc['partialLineDeadline']['bounded']
            assert folder.name in json.loads(Path('docs/performance/probe-limitations.json').read_text())['inconclusivePartialLineProbe']
        else:
            assert ipc['partialLineDeadline']['bounded'] is not expected
        if not expected and folder.name!='final-security-1':assert ipc['partialLineDeadline']['code']=='inference_deadline'
        runs+=1;jobs+=len(data['samples'])
    for name,bounded in [('baseline',False),('candidate',True)]:
        probe=json.loads((Path('docs/performance/ipc-v2')/(name+'.json')).read_text())['partialLineDeadline']
        assert probe['watchdogStartsAfterReadiness'] and probe['bounded'] is bounded
    parity=json.loads(Path('docs/performance/parity.json').read_text());assert parity['exactEquality'] and len(parity['results'])==8
    api_runs=0
    for folder in sorted(root.iterdir()):
        if not (folder/'api.json').exists():continue
        api_runs+=1
        data=json.loads((folder/'api.json').read_text());assert data['complete'] and data['syntheticOnly']
        for value in data['api'].values():
            stats=summary(value['samplesMs']);assert all(value[k]==v for k,v in stats.items())
            assert sum(value['statusCounts'].values())==value['n']
        assert len(data['securityReliabilityChecks'])==5
    print(f'Validated {runs} model runs / {jobs} measured jobs, exact three-pattern and eight-shape parity, {api_runs} API runs with checked sample arithmetic and success markers')
if __name__=='__main__':main()
