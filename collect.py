"""Read-only, allowlisted CC-Switch exporter; standard library only, runs on each host."""
import datetime
import json
import pathlib
import sys
import os
import hashlib

# Conda on Windows may need this process-local search directory outside activation.
_dll_dir = pathlib.Path(sys.prefix) / 'Library' / 'bin'
_dll_handle = os.add_dll_directory(str(_dll_dir)) if os.name == 'nt' and _dll_dir.is_dir() else None
import sqlite3


def enrich_session_providers(rows, roots):
    """Join Codex headers by session ID; never export session text or paths."""
    wanted = {r.get('session_id') for r in rows if r.get('data_source') == 'codex_session'} - {None, ''}
    providers = {}
    inspected = 0
    for root in roots:
        for path in pathlib.Path(root).expanduser().glob('**/*.jsonl'):
            # Standard rollout filenames end with the session UUID.
            if path.stem[-36:] not in wanted:
                continue
            with path.open(encoding='utf-8') as stream:
                line = stream.readline()
            if not line.strip():
                continue
            header = json.loads(line)
            inspected += 1
            meta = header.get('payload', {})
            if header.get('type') != 'session_meta' or meta.get('id') not in wanted:
                continue
            provider = meta.get('model_provider')
            if provider:
                sid = meta['id']
                if sid in providers and providers[sid] != provider:
                    raise ValueError('Conflicting providers in duplicate session headers')
                providers[sid] = provider
    matched = 0
    for row in rows:
        provider = providers.get(row.get('session_id')) if row.get('data_source') == 'codex_session' else None
        if provider:
            row['session_provider'] = provider
            matched += 1
        sid = row.pop('session_id', None)
        if isinstance(sid, str) and sid.strip() and sid.strip().lower() not in {'unknown', 'none', 'null', 'default'}:
            row['session_key'] = hashlib.sha256(sid.encode()).hexdigest()
    return {'headers_read': inspected, 'sessions_matched': len(providers), 'requests_matched': matched,
            'sessions_unmatched': len(wanted - providers.keys())}


def collect(database, session_roots=None):
    path = pathlib.Path(database).expanduser().resolve()
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('BEGIN')  # consistent snapshot across tables, including WAL
    fields = {
        'proxy_request_logs': 'request_id provider_id app_type model session_id input_tokens output_tokens cache_read_tokens cache_creation_tokens input_token_semantics total_cost_usd latency_ms first_token_ms duration_ms status_code created_at data_source',
        'usage_daily_rollups': 'date provider_id app_type model request_model pricing_model request_count success_count input_tokens output_tokens cache_read_tokens cache_creation_tokens input_token_semantics total_cost_usd',
        'providers': 'id app_type name',
    }
    result = {'collected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'host_timezone': str(datetime.datetime.now().astimezone().tzinfo)}
    for table, names in fields.items():
        columns = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
        if not columns:
            raise RuntimeError('Required CC-Switch table missing: ' + table)
        required = set(names.split()) - {'session_id', 'input_token_semantics', 'duration_ms', 'first_token_ms', 'request_model', 'pricing_model'}
        if required - columns:
            raise RuntimeError('Unsupported schema: ' + table + ' missing ' + str(required - columns))
        selected = [n for n in names.split() if n in columns]
        result[table] = [dict(r) for r in db.execute('SELECT ' + ','.join(selected) + ' FROM ' + table)]
    # SQLite localtime matches CC-Switch's own chart bucketing on this host.
    dates = dict(db.execute("SELECT request_id,datetime(created_at,'unixepoch','localtime') FROM proxy_request_logs"))
    for row in result['proxy_request_logs']:
        row['date'] = dates[row['request_id']][:10]
        row['local_datetime'] = dates[row['request_id']]
    db.close()
    result['session_metadata'] = enrich_session_providers(result['proxy_request_logs'],
        session_roots if session_roots is not None else ['~/.codex/sessions', '~/.codex/archived_sessions'])
    return result


if __name__ == '__main__':
    print(json.dumps(collect(sys.argv[1] if len(sys.argv) > 1 else '~/.cc-switch/cc-switch.db')))
