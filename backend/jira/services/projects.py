from ..db import db
from ..util import new_id

DEFAULT_STATUSES = [
    {'name': 'To Do', 'category': 'TODO', 'position': 0},
    {'name': 'In Progress', 'category': 'IN_PROGRESS', 'position': 1},
    {'name': 'In Review', 'category': 'IN_PROGRESS', 'position': 2},
    {'name': 'Done', 'category': 'DONE', 'position': 3},
]

DEFAULT_TRANSITIONS = [
    {'from': 'To Do', 'to': 'In Progress', 'name': 'Start Work'},
    {'from': 'In Progress', 'to': 'In Review', 'name': 'Submit for Review'},
    {'from': 'In Review', 'to': 'Done', 'name': 'Approve & Close'},
    {'from': 'In Review', 'to': 'In Progress', 'name': 'Request Changes'},
    {'from': 'In Progress', 'to': 'To Do', 'name': 'Stop Work'},
    {'from': 'Done', 'to': 'To Do', 'name': 'Reopen'},
]


def create_project_with_default_workflow(key: str, name: str, description: str = '', lead_id=None):
    import re
    key = key.upper()
    pid = f'proj_{key.lower()}'

    def _work():
        db.run(
            'INSERT INTO projects (id, key, name, description, lead_id) VALUES (?, ?, ?, ?, ?)',
            pid, key, name, description or '', lead_id,
        )
        wf_id = f'wf_{key.lower()}'
        db.run(
            'INSERT INTO workflows (id, project_id, name, is_default) VALUES (?, ?, ?, 1)',
            wf_id, pid, f'{name} Default Workflow',
        )
        for s in DEFAULT_STATUSES:
            db.run(
                'INSERT INTO workflow_statuses (id, workflow_id, name, category, position) VALUES (?, ?, ?, ?, ?)',
                f"{wf_id}_{re.sub(r'\s+', '_', s['name']).lower()}", wf_id, s['name'], s['category'], s['position'],
            )
        for t in DEFAULT_TRANSITIONS:
            db.run(
                'INSERT INTO workflow_transitions (id, workflow_id, from_status, to_status, name) VALUES (?, ?, ?, ?, ?)',
                new_id('tr'), wf_id, t['from'], t['to'], t['name'],
            )
        return db.q1('SELECT * FROM projects WHERE id = ?', pid)

    return db.with_transaction(_work)
