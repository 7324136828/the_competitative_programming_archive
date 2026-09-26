from ..db import db
from ..util import new_id, now_iso
from .workflows import get_project_workflow


def get_status_category(project_id: str, status_name: str) -> str:
    wf = get_project_workflow(project_id)
    if wf:
        row = db.q1(
            'SELECT category FROM workflow_statuses WHERE workflow_id = ? AND name = ?',
            wf['id'], status_name,
        )
        if row:
            return row['category']
    if status_name == 'Done':
        return 'DONE'
    if status_name == 'To Do':
        return 'TODO'
    return 'IN_PROGRESS'


def record_status_change(issue_id: str, project_id: str, from_status, to_status: str,
                         changed_by=None, source: str = 'user', at: str | None = None):
    at = at or now_iso()
    from_category = get_status_category(project_id, from_status) if from_status else None
    to_category = get_status_category(project_id, to_status)
    db.run(
        """INSERT INTO issue_status_history
             (id, issue_id, from_status, to_status, from_category, to_category, changed_by, source, changed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        new_id('hist'), issue_id, from_status, to_status,
        from_category, to_category, changed_by, source or 'user', at,
    )


def record_sprint_event(sprint_id: str, issue_id: str, event: str,
                        story_points=None, status=None, at: str | None = None):
    db.run(
        """INSERT INTO sprint_issue_events (id, sprint_id, issue_id, event, story_points, status, changed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        new_id('sev'), sprint_id, issue_id, event, story_points, status, at or now_iso(),
    )
