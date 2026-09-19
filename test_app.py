import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from datetime import datetime
from http.client import HTTPConnection
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from app import Collector, Handler, interval_value, next_boundary


class DashboardTests(unittest.TestCase):
    def test_boundaries(self):
        now = datetime(2026, 9, 19, 12, 3, 42).timestamp()
        self.assertEqual(datetime.fromtimestamp(next_boundary(now, 300)).strftime('%H:%M:%S'), '12:05:00')
        self.assertEqual(datetime.fromtimestamp(next_boundary(now, 5)).strftime('%H:%M:%S'), '12:03:45')
        self.assertEqual(next_boundary(next_boundary(now, 300), 300)-next_boundary(now, 300), 300)

    def test_interval_validation(self):
        for v in (4, 601, 5.5, True, '5', None):
            with self.assertRaises(ValueError):
                interval_value(v)
        for v in (5, 300, 600):
            self.assertEqual(interval_value(v), v)

    def test_http_controls_and_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'config.ini'
            config.write_text('[source:test]\ntransport=local\n')
            collector = Collector(config, 300, Path(tmp)/'cache.json')
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.collector = collector
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            def call(method, path, body=None, headers=None):
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
                response = conn.getresponse(); result = (response.status, response.read()); conn.close(); return result
            try:
                self.assertEqual(call('GET','/config.ini')[0],404)
                self.assertEqual(call('GET','/../config.ini')[0],404)
                self.assertEqual(call('GET','/api/status',headers={'Host':'evil.example'})[0],403)
                self.assertEqual(call('POST','/api/interval',{'seconds':5})[0],403)
                headers={'X-Usage-CSRF':collector.csrf}
                self.assertEqual(call('POST','/api/interval',{'seconds':5},headers)[0],200)
                self.assertEqual(collector.interval,5)
                self.assertEqual(call('POST','/api/interval',{'seconds':601},headers)[0],400)
                headers['Origin']='https://evil.example'
                self.assertEqual(call('POST','/api/interval',{'seconds':300},headers)[0],403)
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_no_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.ini';config.write_text('[source:test]\ntransport=local\n')
            collector=Collector(config,300,Path(tmp)/'cache.json')
            with patch('app.subprocess.Popen') as popen:
                self.assertTrue(collector.refresh())
                self.assertFalse(collector.refresh())
                self.assertEqual(popen.call_count,1)
            collector.workdir.cleanup()

    def test_failed_refresh_keeps_last_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.ini';config.write_text('[source:test]\ntransport=local\n')
            collector=Collector(config,300,Path(tmp)/'cache.json')
            old={'generated_at':'previous', 'rows':[]}
            collector.data=old
            with patch('app.subprocess.Popen') as popen, patch('app.stop_process'):
                popen.return_value.poll.return_value=1
                popen.return_value.returncode=1
                collector.thread.start()
                deadline=time.monotonic()+3
                while collector.error is None and time.monotonic()<deadline:
                    time.sleep(.02)
                collector.close()
            self.assertIs(collector.data,old)
            self.assertIn('Previous data retained',collector.error)
            self.assertFalse(list(Path(tmp).glob('web-refresh-*')))


if __name__ == '__main__':
    unittest.main()
