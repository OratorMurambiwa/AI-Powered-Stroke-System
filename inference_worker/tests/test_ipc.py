"""Real OS pipe fault boundaries, without model or synthetic response mocks."""
import json,os,subprocess,sys,time,unittest
from inference_worker.server import _line

class IpcDeadlines(unittest.TestCase):
    def child(self,code):
        p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,bufsize=0)
        def close():
            if p.poll() is None:p.kill()
            p.wait(timeout=3);p.stdout.close()
        self.addCleanup(close);return p
    def test_readable_partial_line_cannot_escape_total_deadline(self):
        p=self.child("import sys,time;sys.stdout.write('READY\\n{');sys.stdout.flush();time.sleep(2)")
        self.assertEqual(p.stdout.readline(),b'READY\n')
        tick=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'inference_deadline'):_line(p,.05)
        self.assertLess(time.monotonic()-tick,.5)
    def test_coalesced_messages_are_preserved_without_waiting_for_more_bytes(self):
        p=self.child("import sys,time;sys.stdout.write('{\"started\":7}\\n{\"result\":42}\\n');sys.stdout.flush();time.sleep(2)")
        self.assertEqual(_line(p,1),{'started':7});self.assertEqual(_line(p,.1),{'result':42})
    def test_unterminated_oversize_and_closed_partial_messages_fail_closed(self):
        for payload in ('x'*8193,'{'):
            p=self.child('import sys;sys.stdout.write('+repr(payload)+');sys.stdout.flush()')
            with self.assertRaisesRegex(RuntimeError,'inference_failed'):_line(p,1)
    def test_invalid_json_never_returns_a_result(self):
        p=self.child("print('not-json',flush=True)")
        with self.assertRaises(ValueError):_line(p,1)
