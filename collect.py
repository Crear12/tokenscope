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


def enrich_session_titles(rows, codex_home='~/.codex', claude_projects='~/.claude/projects', desktop_roots=None):
    """Read saved conversation names only; never synthesize titles from messages."""
    wanted = {r.get('session_id') for r in rows if r.get('session_id')}
    codex_titles, claude_titles = {}, {}
    home = pathlib.Path(codex_home).expanduser()
    index = home / 'session_index.jsonl'
    if index.exists():
        with index.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get('id') and entry.get('thread_name'):
                    codex_titles[entry['id']] = entry['thread_name']
    databases = sorted(home.glob('state_*.sqlite'),
                       key=lambda p: int(p.stem.split('_')[-1]) if p.stem.split('_')[-1].isdigit() else -1,
                       reverse=True)
    if databases:
        db = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
        try:
            columns = {r[1] for r in db.execute('PRAGMA table_info(threads)')}
            # In desktop state, title can be the original prompt; name is the UI title.
            if {'id', 'name'} <= columns:
                ids = sorted(wanted)
                for offset in range(0, len(ids), 500):
                    chunk = ids[offset:offset+500]
                    for sid, name in db.execute('SELECT id,name FROM threads WHERE id IN (' + ','.join('?' for _ in chunk) + ')', chunk):
                        if name and name.strip():
                            codex_titles[sid] = name
                if 'source' in columns:
                    for offset in range(0, len(ids), 500):
                        chunk = ids[offset:offset+500]
                        for sid, source in db.execute('SELECT id,source FROM threads WHERE id IN (' + ','.join('?' for _ in chunk) + ')', chunk):
                            if not source or not source.lstrip().startswith('{'):
                                continue
                            metadata = json.loads(source)
                            subagent = metadata.get('subagent')
                            spawn = subagent.get('thread_spawn') if isinstance(subagent, dict) else None
                            parent = spawn.get('parent_thread_id') if isinstance(spawn, dict) else None
                            if not parent:
                                continue
                            saved = db.execute('SELECT name FROM threads WHERE id=?', (parent,)).fetchone()
                            title = saved[0] if saved and saved[0] and saved[0].strip() else codex_titles.get(parent)
                            codex_titles[sid] = 'Subagent of: ' + (title or 'Parent title unavailable')
        finally:
            db.close()
    root = pathlib.Path(claude_projects).expanduser()
    requests = {r.get('request_id') for r in rows if r['app_type'] in ('claude', 'claude-desktop')}
    message_sessions = {}
    for path in root.glob('*/*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get('type') == 'assistant' and isinstance(entry.get('message'), dict):
                    mid = entry['message'].get('id')
                    sid = entry.get('sessionId')
                    if isinstance(mid, str) and isinstance(sid, str) and sid:
                        key = 'session:' + mid
                        if key in requests:
                            message_sessions.setdefault(key, set()).add(sid)
                if entry.get('type') == 'custom-title' and entry.get('sessionId') == path.stem:
                    title = entry.get('customTitle')
                    if isinstance(title, str) and title.strip():
                        claude_titles[path.stem] = title
    # Newer CLI title files and desktop title metadata contain no usage accounting.
    for path in root.glob('*/*/custom-title.json'):
        title = json.loads(path.read_text(encoding='utf-8')).get('customTitle')
        if isinstance(title, str) and title.strip():
            claude_titles[path.parent.name] = title
    if desktop_roots is None:
        support = pathlib.Path(os.environ.get('APPDATA', str(pathlib.Path.home() / 'Library/Application Support')))
        desktop_roots = [support / app / 'claude-code-sessions' for app in ('Claude-3p', 'Claude')]
    desktop_titles = {}
    for directory in desktop_roots:
        for path in pathlib.Path(directory).expanduser().glob('**/*.json'):
            entry = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(entry, dict):
                continue
            sid, title = entry.get('cliSessionId'), entry.get('title')
            if isinstance(sid, str) and isinstance(title, str) and title.strip():
                desktop_titles.setdefault(sid, set()).add(title)
    for sid, titles in desktop_titles.items():
        if len(titles) == 1:
            claude_titles[sid] = next(iter(titles))
    linked = ambiguous = 0
    for row in rows:
        if row['app_type'] not in ('claude', 'claude-desktop'):
            continue
        candidates = message_sessions.get(row.get('request_id'), set())
        if len(candidates) > 1:
            ambiguous += 1
        elif len(candidates) == 1:
            sid = next(iter(candidates))
            if row.get('session_id') != sid:
                row['session_id'] = sid
                linked += 1
    matched = 0
    for row in rows:
        titles = codex_titles if row['app_type'] == 'codex' else claude_titles if row['app_type'] in ('claude', 'claude-desktop') else {}
        title = titles.get(row.get('session_id'))
        if title:
            row['session_title'] = title
            matched += 1
    return {'requests_with_saved_title': matched, 'requests_linked_by_message_id': linked,
            'ambiguous_message_id_requests': ambiguous}


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


def collect(database, session_roots=None, codex_home='~/.codex', claude_projects='~/.claude/projects'):
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
    result['session_titles'] = enrich_session_titles(result['proxy_request_logs'], codex_home, claude_projects)
    result['session_metadata'] = enrich_session_providers(result['proxy_request_logs'],
        session_roots if session_roots is not None else ['~/.codex/sessions', '~/.codex/archived_sessions'])
    return result


if __name__ == '__main__':
    print(json.dumps(collect(sys.argv[1] if len(sys.argv) > 1 else '~/.cc-switch/cc-switch.db')))
