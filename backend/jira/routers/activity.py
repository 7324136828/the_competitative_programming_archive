import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..services.users import resolve_acting_user_id, can_configure_project
from ..services.activity import log_activity

router = APIRouter()


@router.get('')
def list_activity(request: Request, limit: int = 50, offset: int = 0,
                  userId: str | None = None, method: str | None = None, q: str | None = None):
    acting = resolve_acting_user_id(request)
    if not can_configure_project(acting):
        return JSONResponse({'error': 'Permission denied: Admin role required'}, 403)
    limit = min(max(int(limit or 50), 1), 200)
    offset = max(int(offset or 0), 0)
    clauses = []
    params = []
    if userId:
        clauses.append('user_id = ?')
        params.append(str(userId))
    if method:
        clauses.append('method = ?')
        params.append(str(method))
    if q:
        clauses.append('(path LIKE ? OR summary LIKE ?)')
        params.extend([f'%{q}%', f'%{q}%'])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db.q(
        f"""SELECT id, user_id, user_name, user_role, method, path, status_code, duration_ms,
                   summary, detail, forwarded, forward_error, created_at
            FROM activity_log {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
        *params, limit, offset,
    )
    total = db.q1(f'SELECT COUNT(*) as c FROM activity_log {where}', *params)['c']
    return {'total': total, 'rows': rows}


@router.post('', status_code=201)
def beacon(request: Request, body: dict):
    body = body or {}
    action = body.get('action')
    if not isinstance(action, str) or not action.strip() or len(action) > 80:
        return JSONResponse({'error': 'action must be a non-empty string (max 80 chars)'}, 400)
    user_id = resolve_acting_user_id(request)
    user = db.q1('SELECT id, name, role FROM users WHERE id = ?', user_id) or {}
    detail_str = None
    if 'detail' in body:
        try:
            detail_str = json.dumps(body['detail'])[:600]
        except Exception:
            detail_str = None
    log_activity(
        user_id=user_id,
        user_name=user.get('name'),
        user_role=user.get('role'),
        method='UI',
        path='ui:' + re.sub(r'\s+', '_', action.strip().lower()),
        summary=action.strip(),
        detail=detail_str,
    )
    return {'ok': True}
