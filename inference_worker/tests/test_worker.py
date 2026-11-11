import base64
import hashlib
import unittest
from inference_worker.server import run_job, synthetic
from inference_worker.probe import image
from inference_worker.model import MODEL_SHA256, LABELS

class RealCpuWorker(unittest.TestCase):
    def test_actual_black_and_gradient_cpu_predictions(self):
        for pattern in ('black','gradient'):
            raw=image(pattern)
            result=run_job({'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()})
            self.assertEqual(result['modelSha256'],MODEL_SHA256)
            self.assertIn(result['predictedClass'],LABELS.values())
            self.assertAlmostEqual(sum(result['scores']),1,places=5)
            self.assertEqual(result['rawScore'],max(result['scores']))
            self.assertEqual(result['scanSha256'],hashlib.sha256(raw).hexdigest())

    def test_actual_invalid_image_fails_without_prediction(self):
        raw=b'<svg onload="alert(1)"/>'
        with self.assertRaisesRegex(RuntimeError,'inference_failed'):
            run_job({'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()})

    def test_actual_scan_hash_mismatch_fails(self):
        command={**synthetic(),'scanSha256':'0'*64}
        with self.assertRaisesRegex(RuntimeError,'inference_failed'):
            run_job(command)

    def test_actual_child_deadline_kills_job_and_next_job_can_run(self):
        with self.assertRaisesRegex(RuntimeError,'inference_deadline'):
            run_job(synthetic(),timeout=0.001)
        self.assertEqual(run_job(synthetic())['modelSha256'],MODEL_SHA256)

    def test_child_offline_environment_does_not_forward_service_credentials(self):
        import os
        from unittest.mock import patch
        from inference_worker.server import child_environment
        with patch.dict(os.environ,{'JWT_SECRET':'synthetic-private','INFERENCE_SERVICE_KEY':'synthetic-private','HTTP_PROXY':'synthetic-proxy'}):
            environment=child_environment()
        self.assertEqual(environment['YOLO_OFFLINE'],'true')
        for key in ['JWT_SECRET','INFERENCE_SERVICE_KEY','HTTP_PROXY']:
            self.assertNotIn(key,environment)
