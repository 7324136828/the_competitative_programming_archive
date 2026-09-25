from ..db import db
from ..util import new_id, now_iso, now_ms
from .history import get_status_category, record_sprint_event


def create_sprint(project_id: str, name: str, goal: str = '', start_date=None, end_date=None):
    sid = new_id('sprint')
    db.run(
        """INSERT INTO sprints (id, project_id, name, goal, start_date, end_date, state)
           VALUES (?, ?, ?, ?, ?, ?, 'planned')""",
        sid, project_id, name, goal or '', start_date, end_date,
    )
    return db.q1('SELECT * FROM sprints WHERE id = ?', sid)


def start_sprint(sprint_id: str, start_date=None, end_date=None):
    sprint = db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)
    if not sprint:
        raise LookupError('Sprint not found')
    if sprint['state'] == 'active':
        raise ValueError('Sprint already started')
    if sprint['state'] == 'closed':
        raise ValueError('Sprint already closed')

    now = now_iso()
    from datetime import datetime, timezone, timedelta
    start = start_date or now.split('T')[0]
    end = end_date or (datetime.fromtimestamp(now_ms() / 1000, tz=timezone.utc) + timedelta(days=14)).date().isoformat()

    def _work():
        members = db.q('SELECT * FROM issues WHERE sprint_id = ?', sprint_id)
        committed_points = sum(float(i['story_points'] or 0) for i in members)
        db.run(
            """UPDATE sprints
               SET state = 'active', start_date = ?, end_date = ?, started_at = ?,
                   committed_issue_count = ?, committed_points = ?
               WHERE id = ?""",
            start, end, now, len(members), committed_points, sprint_id,
        )
        for issue in members:
            record_sprint_event(sprint_id, issue['id'], 'committed',
                                story_points=issue['story_points'], status=issue['status'], at=now)
        return db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)

    return db.with_transaction(_work)


def complete_sprint(sprint_id: str, move_incomplete_to_next_sprint=False, next_sprint_id=None):
    sprint = db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)
    if not sprint:
        raise LookupError('Sprint not found')
    if sprint['state'] != 'active':
        raise ValueError('Sprint already closed' if sprint['state'] == 'closed' else 'Sprint has not been started')

    next_sprint = None
    if move_incomplete_to_next_sprint and next_sprint_id:
        next_sprint = db.q1('SELECT * FROM sprints WHERE id = ?', next_sprint_id)
        if not next_sprint:
            raise ValueError('Target sprint not found')
        if next_sprint['state'] == 'closed':
            raise ValueError('Target sprint is closed')

    now = now_iso()

    def _work():
        members = db.q('SELECT * FROM issues WHERE sprint_id = ?', sprint_id)
        completed_points = 0.0
        completed_count = 0
        for issue in members:
            category = get_status_category(sprint['project_id'], issue['status'])
            if category == 'DONE':
                record_sprint_event(sprint_id, issue['id'], 'completed',
                                    story_points=issue['story_points'], status=issue['status'], at=now)
                completed_points += float(issue['story_points'] or 0)
                completed_count += 1
            else:
                record_sprint_event(sprint_id, issue['id'], 'carried_over',
                                    story_points=issue['story_points'], status=issue['status'], at=now)
                if next_sprint:
                    record_sprint_event(next_sprint['id'], issue['id'], 'added',
                                        story_points=issue['story_points'], status=issue['status'], at=now)
                    db.run('UPDATE issues SET sprint_id = ? WHERE id = ?', next_sprint['id'], issue['id'])
                else:
                    db.run('UPDATE issues SET sprint_id = NULL WHERE id = ?', issue['id'])
        db.run(
            """UPDATE sprints
               SET state = 'closed', completed_at = ?, completed_points = ?, completed_issue_count = ?
               WHERE id = ?""",
            now, completed_points, completed_count, sprint_id,
        )
        return db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)

    return db.with_transaction(_work)
