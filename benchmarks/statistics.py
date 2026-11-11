"""Small-sample descriptive summaries, never clinical accuracy metrics."""
import math

def summary(values, seconds=None):
    if not values or any(type(v) not in {int,float} or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('nonempty finite nonnegative sample required')
    ordered=sorted(values)
    result={'n':len(values),'p50Ms':ordered[math.ceil(.50*len(values))-1],
            'p95Ms':ordered[math.ceil(.95*len(values))-1],'minMs':ordered[0],'maxMs':ordered[-1]}
    if seconds is not None:
        if not math.isfinite(seconds) or seconds<=0:raise ValueError('positive elapsed seconds required')
        result['completedPerSecond']=len(values)/seconds
    return result
