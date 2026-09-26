from ..db import db
from ..util import new_id


def get_project_workflow(project_id: str):
    wf = db.q1('SELECT * FROM workflows WHERE project_id = ?', project_id)
    if not wf:
        wf = db.q1('SELECT * FROM workflows WHERE is_default = 1')
    return wf


def get_workflow_statuses(workflow_id: str):
    return db.q('SELECT * FROM workflow_statuses WHERE workflow_id = ? ORDER BY position ASC', workflow_id)


def get_workflow_transitions(workflow_id: str):
    return db.q('SELECT * FROM workflow_transitions WHERE workflow_id = ?', workflow_id)


def get_allowed_transitions_for_status(project_id: str, current_status: str):
    wf = get_project_workflow(project_id)
    if not wf:
        return []
    return db.q(
        'SELECT to_status, name FROM workflow_transitions WHERE workflow_id = ? AND from_status = ?',
        wf['id'], current_status,
    )


def is_transition_allowed(project_id: str, from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    wf = get_project_workflow(project_id)
    if not wf:
        return True
    row = db.q1(
        'SELECT id FROM workflow_transitions WHERE workflow_id = ? AND from_status = ? AND to_status = ?',
        wf['id'], from_status, to_status,
    )
    return row is not None


def add_workflow_transition(workflow_id: str, from_status: str, to_status: str, name: str):
    tid = new_id('tr')
    db.run(
        'INSERT INTO workflow_transitions (id, workflow_id, from_status, to_status, name) VALUES (?, ?, ?, ?, ?)',
        tid, workflow_id, from_status, to_status, name,
    )
    return {'id': tid, 'workflowId': workflow_id, 'fromStatus': from_status, 'toStatus': to_status, 'name': name}


def delete_workflow_transition(transition_id: str):
    db.run('DELETE FROM workflow_transitions WHERE id = ?', transition_id)
