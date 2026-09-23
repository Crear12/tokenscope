import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collect import enrich_codex_timing
from update import fetch

SID = '00000000-0000-0000-0000-000000000001'
BASE = 1767225600  # 2026-01-01 UTC


def event(second, kind, **payload):
    import datetime
    return dict(timestamp=datetime.datetime.fromtimestamp(BASE+second, datetime.timezone.utc).isoformat(),
                type=kind, payload=payload)


def usage():
    return dict(input_tokens=100, cached_input_tokens=80, output_tokens=60)


def request(second, **extra):
    return dict(session_id=SID, data_source='codex_session', created_at=BASE+second,
                input_tokens=100, output_tokens=60, cache_read_tokens=80, **extra)


def response(start, end, counted, call=False, native=True):
    records = [event(start, 'response_item', type='message', role='user'),
               event(end, 'response_item', **(dict(type='function_call',call_id='tool') if call else dict(type='message',role='assistant')))]
    if native:
        records.append(event(end+.1, 'token_usage_record', usage=usage()))
    if call:
        records.append(event(counted-.1, 'response_item',type='function_call_output',call_id='tool'))
    records.append(event(counted, 'event_msg',type='token_count', info=dict(last_token_usage=usage())))
    return records


class NativeTPS(unittest.TestCase):
    def run_enrichment(self, records, rows):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/('rollout-'+SID+'.jsonl')
            path.write_text('\n'.join(json.dumps(r) for r in [
                event(0,'session_meta',id=SID), *records])+'\n')
            result=enrich_codex_timing(rows,[root])
        return result

    def test_tools_and_day_idle_excluded(self):
        records = response(1,4,100,call=True)
        records += [event(102,'response_item',type='message',role='assistant'),
                    event(102.1,'token_usage_record',usage=usage()),
                    event(103,'event_msg',type='token_count',info=dict(last_token_usage=usage())),
                    event(104,'event_msg',type='task_complete')]
        records += response(86401,86403,86404)
        rows=[request(100),request(103),request(86404)]
        original=copy.deepcopy(rows)
        self.assertEqual(self.run_enrichment(records,rows)['requests_matched'],3)
        self.assertAlmostEqual(rows[0]['native_response_ms'],3000)
        self.assertAlmostEqual(rows[1]['native_response_ms'],2100,places=2)
        self.assertAlmostEqual(rows[2]['native_response_ms'],2000)
        for before,after in zip(original,rows):
            self.assertEqual(before,{k:v for k,v in after.items() if k!='native_response_ms'})

    def test_legacy_and_ambiguous_and_missing(self):
        rows=[request(5),request(8),request(12),request(99)]
        records=response(1,4,5,native=False)
        records+=response(6,7,8)
        records+=[event(8.5,'event_msg',type='token_count',info=dict(last_token_usage=usage()))]
        records+=[event(12,'event_msg',type='token_count',info=dict(last_token_usage=usage()))]
        self.assertEqual(self.run_enrichment(records,rows)['requests_matched'],1)
        self.assertEqual(rows[0]['native_response_ms'],3000)
        self.assertTrue(all('native_response_ms' not in r for r in rows[1:]))

    def test_no_nearest_time_or_token_guess(self):
        records=response(1,4,5)
        rows=[request(6),request(5)]
        rows[1]['output_tokens']=61
        self.assertEqual(self.run_enrichment(records,rows)['requests_matched'],0)

    def test_duplicate_destination_and_interrupted(self):
        rows=[request(5),request(5),request(12)]
        records=response(1,4,5)
        records += [event(10,'response_item',type='message',role='user'),
                    event(11,'event_msg',type='turn_aborted'),
                    event(12,'event_msg',type='token_count',info=dict(last_token_usage=usage()))]
        self.assertEqual(self.run_enrichment(records,rows)['requests_matched'],0)

    def test_default_on_and_config_off(self):
        snapshot=dict(proxy_request_logs=[],usage_daily_rollups=[])
        with patch('update.collect',return_value=snapshot.copy()) as collect:
            fetch(('sample',{'transport':'local'}))
            self.assertIs(collect.call_args.args[-1],True)
            fetch(('sample',{'transport':'local','codex_native_tps':'false'}))
            self.assertIs(collect.call_args.args[-1],False)
        with self.assertRaises(ValueError):
            fetch(('sample',{'transport':'local','codex_native_tps':'invalid'}))


if __name__ == '__main__':
    unittest.main()
