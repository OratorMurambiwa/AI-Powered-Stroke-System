import unittest
from benchmarks.statistics import summary
class Statistics(unittest.TestCase):
    def test_nearest_rank_and_actual_elapsed_throughput(self):
        s=summary(list(range(1,31)),15);self.assertEqual((s['p50Ms'],s['p95Ms']),(15,29));self.assertEqual(s['completedPerSecond'],2)
    def test_bad_samples_or_elapsed_are_rejected(self):
        for v in ([],[-1],[float('nan')],[True]):
            with self.assertRaises(ValueError):summary(v)
        for seconds in (0,-1,float('inf')):
            with self.assertRaises(ValueError):summary([1],seconds)
