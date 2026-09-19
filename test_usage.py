import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from update import fresh, effective, build, canonical_model, monthly_leaders
from collect import enrich_session_providers


def row(**kw):
    r = dict(app_type='codex', input_tokens=1000, output_tokens=20,
             cache_read_tokens=600, cache_creation_tokens=100,
             input_token_semantics=0, status_code=200, created_at=1000,
             model='model', data_source='codex_session')
    r.update(kw)
    return r


class Accounting(unittest.TestCase):
    def test_monthly_leaders_use_summed_tokens_and_preserve_ties(self):
        rows = [dict(date='2026-01-01', model='a', total_tokens=4),
                dict(date='2026-01-02', model='a', total_tokens=4),
                dict(date='2026-01-02', model='b', total_tokens=6),
                dict(date='2026-02-01', model='a', total_tokens=2),
                dict(date='2026-02-01', model='b', total_tokens=2)]
        for r in rows:
            r['cost_usd'] = '0.10' if r['model'] == 'a' else '0.90'
        leaders = monthly_leaders(rows)
        self.assertEqual(leaders[0]['cost_usd_by_model'], {'a': '0.20'})
        self.assertEqual(leaders[1]['cost_usd_by_model'], {'a': '0.10', 'b': '0.90'})
        self.assertEqual(leaders[0]['models'], ['a'])
        self.assertEqual(leaders[0]['tokens'], 8)
        self.assertEqual(leaders[0]['share'], 8 / 14)
        self.assertEqual(leaders[1]['models'], ['a', 'b'])

    def test_model_labels_are_preserved(self):
        for model in ('example-model', 'example-model:cloud', 'vendor/example-model', 'unknown'):
            self.assertEqual(canonical_model(row(model=model)), model)
        self.assertEqual(canonical_model(row(model=None)), 'unknown')

    def test_header_provider_join(self):
        sid = '00000000-0000-0000-0000-000000000001'
        rows = [row(session_id=sid), row(session_id='missing')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ('rollout-' + sid + '.jsonl')
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': sid, 'model_provider': 'ollama'}}) + '\nnot parsed session content\n')
            audit = enrich_session_providers(rows, [directory])
        self.assertEqual(rows[0]['session_provider'], 'ollama')
        self.assertNotIn('session_provider', rows[1])
        self.assertNotIn('session_id', rows[0])
        self.assertEqual(audit['sessions_unmatched'], 1)

    def test_models_and_costs_remain_separate(self):
        requests = [row(request_id=str(i), provider_id='_session', date='2026-09-01',
                        model=model, total_cost_usd=cost, session_provider='ollama')
                    for i, (model, cost) in enumerate([('a', '0.10'), ('b', '0.20')])]
        data = dict(collected_at='2026-09-02', host_timezone='UTC', providers=[], proxy_request_logs=requests, usage_daily_rollups=[])
        with tempfile.TemporaryDirectory() as directory, patch('update.render'):
            result = build([('one', data)], Path(directory))
        self.assertEqual(result['total_cost_usd'], '0.30')
        self.assertEqual([r['model'] for r in result['by_model']], ['a', 'b'])

    def test_cache_semantics(self):
        self.assertEqual(fresh(row()), 400)
        self.assertEqual(fresh(row(input_token_semantics=1)), 300)
        self.assertEqual(fresh(row(input_token_semantics=2)), 1000)
        self.assertEqual(fresh(row(app_type='claude')), 1000)

    def test_proxy_duplicate_and_window(self):
        p = row(data_source='proxy')
        self.assertEqual(len(effective([p, row()])), 1)
        self.assertEqual(len(effective([p, row(created_at=1601)])), 2)
        self.assertEqual(len(effective([row(data_source='proxy', status_code=500), row()])), 2)

    def test_claude_desktop_dedup(self):
        p = row(app_type='claude-desktop', data_source='proxy')
        s = row(app_type='claude', data_source='session_log')
        self.assertEqual(effective([p, s]), [p])

    def test_codex_unknown_cache_write(self):
        p = row(data_source='proxy')
        self.assertEqual(effective([p, row(cache_creation_tokens=0)]), [p])

    def test_cross_host_identity_and_rollup_accounting(self):
        request = row(request_id='same', provider_id='_session', date='2026-09-01', total_cost_usd='0')
        rollup = row(provider_id='_session', date='2026-08-01', request_count=3, total_cost_usd='0')
        data = dict(collected_at='2026-09-02', host_timezone='UTC', providers=[], proxy_request_logs=[request], usage_daily_rollups=[rollup])
        with tempfile.TemporaryDirectory() as directory, patch('update.render'):
            result = build([('one', data), ('two', data)], Path(directory))
        # One unique request plus two retained rollups; identical aggregates are flagged.
        self.assertEqual(result['cross_host_duplicates_removed'], 1)
        self.assertEqual(result['matching_cross_host_rollups_retained'], 1)
        self.assertEqual(result['requests'], 7)
        self.assertEqual(result['total_tokens'], 3 * (400 + 600 + 100 + 20))


if __name__ == '__main__':
    unittest.main()
