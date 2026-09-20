import unittest
import tempfile
from pathlib import Path
from test_usage import row
from collect import enrich_session_providers
from update import build


class SessionDetails(unittest.TestCase):
    def test_exact_message_link_and_ambiguous_ids(self):
        import json
        from collect import enrich_session_titles
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'projects' / 'example'
            desktop = root / 'desktop'
            project.mkdir(parents=True); desktop.mkdir()
            for sid, mids in [('conversation-a', ['response-1', 'response-1', 'shared']), ('conversation-b', ['shared'])]:
                (project / (sid + '.jsonl')).write_text('\n'.join(json.dumps({
                    'type':'assistant', 'sessionId':sid, 'message':{'id':mid,'content':'Never export this'}}) for mid in mids))
            (desktop / 'example.json').write_text(json.dumps({'cliSessionId':'conversation-a','title':'Fictional desktop title'}))
            (project / 'conversation-b').mkdir()
            (project / 'conversation-b' / 'custom-title.json').write_text(json.dumps({'customTitle':'Fictional CLI title'}))
            rows = [row(app_type='claude-desktop',request_id='session:response-1',session_id='proxy-id'),
                    row(app_type='claude-desktop',request_id='session:shared',session_id='ambiguous'),
                    row(app_type='claude',request_id='unmatched',session_id='conversation-b'),
                    row(app_type='codex',request_id='session:response-1',session_id='codex-id')]
            before = [{k:v for k,v in r.items() if k != 'session_id'} for r in rows]
            audit = enrich_session_titles(rows, str(root/'codex'), str(root/'projects'), [desktop])
            self.assertEqual(rows[0]['session_id'], 'conversation-a')
            self.assertEqual(rows[0]['session_title'], 'Fictional desktop title')
            self.assertEqual(rows[1]['session_id'], 'ambiguous')
            self.assertNotIn('session_title', rows[1])
            self.assertEqual(rows[2]['session_title'], 'Fictional CLI title')
            self.assertEqual(rows[3]['session_id'], 'codex-id')
            self.assertEqual(audit['requests_linked_by_message_id'], 1)
            self.assertEqual(audit['ambiguous_message_id_requests'], 1)
            self.assertEqual(before, [{k:v for k,v in r.items() if k not in ('session_id','session_title')} for r in rows])

    def test_saved_titles_without_prompt_fallback(self):
        import sqlite3
        import json
        from collect import enrich_session_titles
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'codex'
            project = root / 'projects' / 'example'
            home.mkdir(); project.mkdir(parents=True)
            (home / 'session_index.jsonl').write_text(json.dumps({'id':'c1','thread_name':'Old title'})+'\n')
            db = sqlite3.connect(home / 'state_5.sqlite')
            db.execute('CREATE TABLE threads(id TEXT, name TEXT, title TEXT)')
            db.executemany('INSERT INTO threads VALUES(?,?,?)', [('c1','Saved name','Do not export prompt'),('c2',None,'Private initial prompt')])
            db.commit(); db.close()
            (project / 'a1.jsonl').write_text('\n'.join(json.dumps(r) for r in [
                {'type':'user','message':'Private message'},
                {'type':'custom-title','sessionId':'a1','customTitle':'Earlier name'},
                {'type':'custom-title','sessionId':'a1','customTitle':'Final saved name'}]))
            rows = [row(session_id='c1'), row(session_id='c2'), row(app_type='claude',session_id='a1')]
            enrich_session_titles(rows, str(home), str(root/'projects'))
            self.assertEqual(rows[0]['session_title'], 'Saved name')
            self.assertNotIn('session_title', rows[1])
            self.assertEqual(rows[2]['session_title'], 'Final saved name')

    def test_session_keys_missing_and_source_ids(self):
        rows = [row(session_id=s, data_source='proxy') for s in ('same-id', 'same-id', '', None, 'unknown')]
        enrich_session_providers(rows, [])
        self.assertEqual(rows[0]['session_key'], rows[1]['session_key'])
        self.assertTrue(all('session_key' not in r for r in rows[2:]))
        self.assertTrue(all('session_id' not in r for r in rows))

    def test_session_detail_grain_dedup_and_public_projection(self):
        from app import public_data
        requests = [row(request_id=str(i), provider_id='_session', date=date, model=model,
                        session_key='hashed-id', session_title='Fictional example', total_cost_usd='0.10')
                    for i, (date, model) in enumerate([('2026-01-31', 'a'), ('2026-02-01', 'a'), ('2026-02-01', 'b')])]
        requests.append(row(request_id='no-session', provider_id='_session', date='2026-02-01', total_cost_usd='0.20'))
        rollup = row(provider_id='_session', date='2026-01-01', request_count=10, total_cost_usd='1')
        data = dict(collected_at='2026-02-02', host_timezone='UTC', providers=[], proxy_request_logs=requests, usage_daily_rollups=[rollup])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = build([('one', data), ('two', data)], out, render_figures=False)
            public = public_data(out)
        self.assertEqual(len(public['session_rows']), 3)
        self.assertEqual({r['session_title'] for r in public['session_rows']}, {'Fictional example'})
        self.assertEqual(sum(r['requests'] for r in public['session_rows']), 3)
        self.assertEqual({r['host'] for r in public['session_rows']}, {'one'})
        self.assertEqual({r['date'] for r in public['session_rows']}, {'2026-01-31', '2026-02-01'})
        self.assertEqual(sum(r['tokens'] for r in public['session_rows']), 3*1120)
        self.assertEqual(result['cross_host_duplicates_removed'], 4)
        self.assertEqual(result['total_cost_usd'], '2.50')
        self.assertTrue(all('request_id' not in r and 'session_id' not in r for r in public['session_rows']))
        self.assertEqual(sum(r['tokens'] for r in public['rows'])-sum(r['tokens'] for r in public['session_rows']), 3*1120)

    def test_empty_session_detail_is_available(self):
        from app import public_data
        data = dict(collected_at='2026-02-02', host_timezone='UTC', providers=[], proxy_request_logs=[], usage_daily_rollups=[])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            build([('one', data)], out, render_figures=False)
            self.assertEqual(public_data(out)['session_rows'], [])
