import json
import queue
import threading

import httpx

from ..db import db
from ..util import now_iso
from ..config import (
    connector_url, connector_api_key, activity_forward_enabled, activity_session_title,
)

SESSION_KEY = 'activity.connector_session_id'


def record_activity(user_id=None, user_name=None, user_role=None, method='', path='',
                    status_code=None, duration_ms=None, summary=None, detail=None) -> int:
    cur = db.run(
        """INSERT INTO activity_log
             (user_id, user_name, user_role, method, path, status_code, duration_ms, summary, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        user_id, user_name, user_role, method, path,
        status_code, duration_ms, summary, detail, now_iso(),
    )
    return int(cur.lastrowid)


def _mark_forwarded(row_id: int, ok: bool, error: str | None = None):
    db.run('UPDATE activity_log SET forwarded = ?, forward_error = ? WHERE id = ?',
           1 if ok else -1, None if ok else (error or 'unknown'), row_id)


# ---------- Connector forwarding ----------

def _connector_fetch(path: str, method: str = 'GET', body=None, timeout_s: float = 10.0) -> httpx.Response:
    return httpx.request(
        method,
        f"{connector_url().rstrip('/')}{path}",
        content=json.dumps(body) if body is not None else None,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {connector_api_key()}',
        },
        timeout=timeout_s,
    )


def _cached_session_id() -> str | None:
    row = db.q1('SELECT value FROM app_settings WHERE key = ?', SESSION_KEY)
    return row['value'] if row else None


def _set_cached_session_id(sid: str | None):
    if sid is None:
        db.run('DELETE FROM app_settings WHERE key = ?', SESSION_KEY)
    else:
        db.run('INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)',
               SESSION_KEY, sid, now_iso())


_ACTIVITY_SESSION_CONFIG = {
    'past_memory': False,
    'context_window': 2,
    'sequences': [{'provider': 'mock', 'model': 'mock-assistant', 'retries': 0}],
}


def _ensure_activity_session() -> str:
    cached = _cached_session_id()
    if cached:
        return cached
    try:
        res = _connector_fetch('/api/sessions')
        if res.status_code == 200:
            for s in res.json():
                if s.get('title') == activity_session_title() and s.get('status') == 'active':
                    _set_cached_session_id(s['session_id'])
                    return s['session_id']
    except Exception:
        pass
    res = _connector_fetch('/api/sessions', 'POST',
                           {'title': activity_session_title(), 'config': _ACTIVITY_SESSION_CONFIG})
    if res.status_code >= 400:
        raise RuntimeError(f'Connector session create failed: HTTP {res.status_code}')
    sid = res.json().get('session_id')
    if not sid:
        raise RuntimeError('Connector session create returned no session_id')
    _set_cached_session_id(sid)
    return sid


def _send_activity_line(session_id: str, line: str) -> httpx.Response:
    return _connector_fetch('/api/chat', 'POST', {'session_id': session_id, 'message': line}, 15.0)


def _forward_once(row_id: int, line: str):
    try:
        session_id = _ensure_activity_session()
        res = _send_activity_line(session_id, line)
        if res.status_code in (404, 410):
            _set_cached_session_id(None)
            session_id = _ensure_activity_session()
            res = _send_activity_line(session_id, line)
        if res.status_code >= 400:
            raise RuntimeError(f'HTTP {res.status_code}')
        _mark_forwarded(row_id, True)
    except Exception as err:
        _mark_forwarded(row_id, False, str(err)[:300])


# Serialize forwards so the connector transcript stays in order.
_queue: queue.Queue = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _worker():
    while True:
        row_id, line = _queue.get()
        try:
            _forward_once(row_id, line)
        except Exception:
            pass
        finally:
            _queue.task_done()


def forward_activity(row_id: int, line: str):
    if not activity_forward_enabled():
        return
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            threading.Thread(target=_worker, daemon=True).start()
            _worker_started = True
    _queue.put((row_id, line))


def drain_activity_forwards(timeout: float = 10.0):
    """Test/helper hook: wait until all queued forwards have settled."""
    done = threading.Event()

    def _watch():
        _queue.join()
        done.set()

    threading.Thread(target=_watch, daemon=True).start()
    done.wait(timeout)


def format_activity_line(method: str, path: str, user_id=None, user_name=None,
                         status_code=None, duration_ms=None, summary=None, created_at=None) -> str:
    ts = created_at or now_iso()
    who = f"{user_name or 'unknown'}{f' ({user_id})' if user_id else ''}"
    status = f' -> {status_code}' if status_code is not None else ''
    ms = f' {duration_ms}ms' if duration_ms is not None else ''
    extra = f' | {summary}' if summary else ''
    return f'[{ts}] {who} {method} {path}{status}{ms}{extra}'[:1900]


def log_activity(**f) -> int:
    row_id = record_activity(**{k: f.get(k) for k in (
        'user_id', 'user_name', 'user_role', 'method', 'path',
        'status_code', 'duration_ms', 'summary', 'detail')})
    forward_activity(row_id, format_activity_line(
        f.get('method', ''), f.get('path', ''),
        user_id=f.get('user_id'), user_name=f.get('user_name'),
        status_code=f.get('status_code'), duration_ms=f.get('duration_ms'),
        summary=f.get('summary'),
    ))
    return row_id
