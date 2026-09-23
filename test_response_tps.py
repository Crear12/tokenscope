import tempfile
import unittest
from pathlib import Path

from app import public_data
from test_usage import row
from update import build, response_duration_ms


class ResponseTPS(unittest.TestCase):
    def test_timing_selection(self):
        self.assertEqual(response_duration_ms({'duration_ms':2000,'latency_ms':9000}),2000)
        self.assertEqual(response_duration_ms({'duration_ms':-1,'latency_ms':3000}),3000)
        self.assertEqual(response_duration_ms({'duration_ms':float('nan')}),0)
        self.assertEqual(response_duration_ms({}),0)

    def test_response_rates_and_missing_timing(self):
        records=[]
        for index, extra in enumerate([
            {'output_tokens':100,'duration_ms':2000,'latency_ms':9000,'native_response_ms':1},
            {'output_tokens':90,'latency_ms':3000},
            {'output_tokens':800,'native_response_ms':4000},  # separate optional estimate
            {'output_tokens':100,'duration_ms':1,'status_code':500},
            {'output_tokens':0,'duration_ms':1000},
        ]):
            records.append(row(request_id=str(index),provider_id='_session',date='2026-09-01',
                               session_key='fictional',total_cost_usd='0',**extra))
        source=dict(collected_at='2026-09-02',host_timezone='UTC',providers=[],
                    proxy_request_logs=records,usage_daily_rollups=[])
        with tempfile.TemporaryDirectory() as directory:
            build([('example',source)],Path(directory),render_figures=False)
            result=public_data(Path(directory))['session_rows'][0]
        self.assertEqual(result['requests'],5)
        self.assertEqual(result['tps_count'],2)
        self.assertEqual(result['tps_sum'],80)  # 50 + 30; mean 40, not total tokens/session time
        self.assertEqual(result['tps_max'],50)
        self.assertEqual(result['native_tps_count'],1)
        self.assertEqual(result['native_tps_sum'],200)
        self.assertEqual(result['native_tps_max'],200)


if __name__ == '__main__':
    unittest.main()
