import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id
from ..services.automation import get_automation_rules, get_automation_logs

router = APIRouter()


@router.get('/rules')
def list_rules(projectId: str | None = None):
    return get_automation_rules(projectId or None)


@router.post('/rules', status_code=201)
def create_rule(body: dict):
    body = body or {}
    for f in ('name', 'triggerEvent', 'conditions', 'actions'):
        if not body.get(f):
            return JSONResponse({'error': 'Missing required fields for automation rule'}, 400)
    rid = new_id('rule')
    is_enabled = (1 if body['isEnabled'] else 0) if 'isEnabled' in body else 1
    db.run(
        """INSERT INTO automation_rules (id, project_id, name, trigger_event, conditions_json, actions_json, is_enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rid, body.get('projectId') or None, body['name'], body['triggerEvent'],
        json.dumps(body['conditions']), json.dumps(body['actions']), is_enabled,
    )
    return db.q1('SELECT * FROM automation_rules WHERE id = ?', rid)


@router.patch('/rules/{id}/toggle')
def toggle_rule(id: str):
    rule = db.q1('SELECT is_enabled FROM automation_rules WHERE id = ?', id)
    if not rule:
        return JSONResponse({'error': 'Rule not found'}, 404)
    next_state = 0 if rule['is_enabled'] else 1
    db.run('UPDATE automation_rules SET is_enabled = ? WHERE id = ?', next_state, id)
    return {'id': id, 'isEnabled': next_state == 1}


@router.delete('/rules/{id}')
def delete_rule(id: str):
    db.run('DELETE FROM automation_rules WHERE id = ?', id)
    return {'success': True}


@router.get('/logs')
def list_logs(projectId: str | None = None):
    return get_automation_logs(projectId)
