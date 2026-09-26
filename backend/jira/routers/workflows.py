from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id
from ..services.workflows import (
    get_project_workflow, get_workflow_statuses, get_workflow_transitions,
    add_workflow_transition, delete_workflow_transition, get_allowed_transitions_for_status,
)

router = APIRouter()


@router.get('/project/{project_id}')
def get_workflow(project_id: str):
    wf = get_project_workflow(project_id)
    if not wf:
        return JSONResponse({'error': 'Workflow not found'}, 404)
    return {
        'workflow': wf,
        'statuses': get_workflow_statuses(wf['id']),
        'transitions': get_workflow_transitions(wf['id']),
    }


@router.get('/project/{project_id}/allowed-transitions')
def allowed_transitions(project_id: str, status: str | None = None):
    if not status:
        return JSONResponse({'error': 'Status query param required'}, 400)
    return get_allowed_transitions_for_status(project_id, status)


@router.post('/transitions', status_code=201)
def create_transition(body: dict):
    body = body or {}
    if not all(body.get(k) for k in ('workflowId', 'fromStatus', 'toStatus', 'name')):
        return JSONResponse({'error': 'workflowId, fromStatus, toStatus, and name are required'}, 400)
    try:
        return add_workflow_transition(body['workflowId'], body['fromStatus'], body['toStatus'], body['name'])
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.delete('/transitions/{id}')
def delete_transition(id: str):
    delete_workflow_transition(id)
    return {'success': True}


@router.post('/statuses', status_code=201)
def create_status(body: dict):
    body = body or {}
    if not body.get('workflowId') or not body.get('name'):
        return JSONResponse({'error': 'workflowId and name are required'}, 400)
    sid = new_id('status')
    db.run(
        'INSERT INTO workflow_statuses (id, workflow_id, name, category, position) VALUES (?, ?, ?, ?, 99)',
        sid, body['workflowId'], body['name'], body.get('category') or 'IN_PROGRESS',
    )
    return {'id': sid, 'workflowId': body['workflowId'], 'name': body['name'],
            'category': body.get('category')}
