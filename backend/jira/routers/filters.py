import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id
from ..services.users import resolve_acting_user_id

router = APIRouter()


@router.get('')
def list_filters(request: Request):
    user_id = resolve_acting_user_id(request)
    return db.q('SELECT * FROM saved_filters WHERE user_id = ? ORDER BY created_at DESC', user_id)


@router.post('', status_code=201)
def create_filter(request: Request, body: dict):
    body = body or {}
    user_id = resolve_acting_user_id(request)
    if not body.get('name') or not body.get('query'):
        return JSONResponse({'error': 'Name and query are required'}, 400)
    fid = new_id('filter')
    q = body['query']
    db.run(
        'INSERT INTO saved_filters (id, user_id, name, query_json) VALUES (?, ?, ?, ?)',
        fid, user_id, body['name'], q if isinstance(q, str) else json.dumps(q),
    )
    return db.q1('SELECT * FROM saved_filters WHERE id = ?', fid)


@router.delete('/{id}')
def delete_filter(id: str, request: Request):
    user_id = resolve_acting_user_id(request)
    db.run('DELETE FROM saved_filters WHERE id = ? AND user_id = ?', id, user_id)
    return {'success': True}
