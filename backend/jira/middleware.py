import json
import time

from starlette.middleware.base import BaseHTTPMiddleware

from .db import db
from .services.users import resolve_acting_user_id
from .services.activity import log_activity
from .config import activity_log_enabled

# High-frequency polls and internal endpoints that are not user "steps".
SKIPPED = {'GET /api/notifications', 'GET /api/health', 'POST /api/activity'}


def _summarize_body(body) -> str | None:
    if not isinstance(body, dict) or not body:
        return None
    out = {}
    for k in list(body.keys())[:10]:
        v = body[k]
        if v is None:
            continue
        out[k] = v[:200] if isinstance(v, str) else json.dumps(v)[:200] if _jsonable(v) else None
    try:
        return json.dumps(out)[:600]
    except Exception:
        return None


def _jsonable(v) -> bool:
    try:
        json.dumps(v)
        return True
    except Exception:
        return False


def _summarize_query(query: dict) -> str | None:
    if not query:
        return None
    try:
        return json.dumps(dict(query))[:300]
    except Exception:
        return None


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not activity_log_enabled() or request.method in ('OPTIONS', 'HEAD'):
            return await call_next(request)
        full_path = request.url.path
        if f'{request.method} {full_path}' in SKIPPED:
            return await call_next(request)

        start = time.time() * 1000
        # Read + cache the body so downstream handlers still see it
        body_bytes = await request.body()
        body_obj = None
        if body_bytes and request.headers.get('content-type', '').startswith('application/json'):
            try:
                body_obj = json.loads(body_bytes)
            except Exception:
                body_obj = None

        response = await call_next(request)

        try:
            user_id = resolve_acting_user_id(request)
            user = db.q1('SELECT id, name, role FROM users WHERE id = ?', user_id) or {}
            log_activity(
                user_id=user_id,
                user_name=user.get('name'),
                user_role=user.get('role'),
                method=request.method,
                path=full_path,
                status_code=response.status_code,
                duration_ms=int(time.time() * 1000 - start),
                detail=_summarize_body(body_obj) or _summarize_query(dict(request.query_params)),
            )
        except Exception as err:
            print(f'Activity log error: {err}')
        return response
