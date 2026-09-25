import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id

router = APIRouter()


@router.get('/projects/{project_id}')
def list_fields(project_id: str):
    return db.q('SELECT * FROM custom_fields WHERE project_id = ? ORDER BY created_at ASC', project_id)


@router.post('/projects/{project_id}', status_code=201)
def create_field(project_id: str, body: dict):
    body = body or {}
    if not body.get('name') or not body.get('fieldType'):
        return JSONResponse({'error': 'Name and fieldType are required'}, 400)
    fid = new_id('cf')
    db.run(
        'INSERT INTO custom_fields (id, project_id, name, field_type, options_json) VALUES (?, ?, ?, ?, ?)',
        fid, project_id, body['name'], body['fieldType'],
        json.dumps(body['options']) if body.get('options') else None,
    )
    return db.q1('SELECT * FROM custom_fields WHERE id = ?', fid)


@router.delete('/{id}')
def delete_field(id: str):
    db.run('DELETE FROM custom_fields WHERE id = ?', id)
    return {'success': True}
