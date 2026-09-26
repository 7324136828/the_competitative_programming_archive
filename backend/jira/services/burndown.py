from datetime import datetime, timezone

from ..db import db
from ..util import now_ms, parse_ms
from .history import get_status_category
from .metrics import get_sprint_events, member_at, category_at, _ms_to_iso


def get_sprint_burndown_data(sprint_id: str):
    sprint = db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)
    if not sprint:
        return None

    issues = db.q('SELECT * FROM issues WHERE sprint_id = ?', sprint_id)
    total_points = sum(float(i['story_points'] or 0) for i in issues)
    completed_points = sum(
        float(i['story_points'] or 0) for i in issues
        if get_status_category(i['project_id'], i['status']) == 'DONE'
    )
    remaining_points = total_points - completed_points

    snapshots = db.q('SELECT * FROM sprint_snapshots WHERE sprint_id = ? ORDER BY date ASC', sprint_id)

    now = now_ms()
    start_ms = _parse_date_or_now(sprint.get('start_date'), now)
    end_ms = _parse_date_or_now(sprint.get('end_date'), now + 14 * 24 * 3600 * 1000)
    diff_days = max(1, round((end_ms - start_ms) / (1000 * 3600 * 24)))

    base = {
        'sprint': sprint,
        'totalPoints': total_points,
        'completedPoints': completed_points,
        'remainingPoints': remaining_points,
        'totalIssues': len(issues),
        'completedIssues': sum(1 for i in issues if get_status_category(i['project_id'], i['status']) == 'DONE'),
        'committedPoints': sprint.get('committed_points'),
    }

    if not sprint.get('started_at'):
        timeline = []
        snapshot_map = {s['date']: s for s in snapshots}
        for i in range(diff_days + 1):
            d = start_ms + i * 24 * 3600 * 1000
            date_str = _ms_to_iso(d)[:10]
            ideal = max(0, round(total_points - (total_points / diff_days) * i, 1))
            if date_str in snapshot_map:
                actual = snapshot_map[date_str]['remaining_points']
            elif d <= now:
                actual = remaining_points
            else:
                actual = None
            timeline.append({'day': i, 'date': date_str, 'ideal': ideal, 'actual': actual})
        return {**base, 'timeline': timeline}

    # Event-based burndown for started sprints
    started_ms = parse_ms(sprint['started_at'])
    completed_ms = parse_ms(sprint.get('completed_at'))
    events = get_sprint_events(sprint_id)
    committed = sprint['committed_points'] if sprint.get('committed_points') is not None else total_points

    event_issue_ids = list(dict.fromkeys(e['issue_id'] for e in events))
    all_issue_ids = list(dict.fromkeys(event_issue_ids + [i['id'] for i in issues]))
    points_by_id = {}
    status_by_id = {}
    project_by_id = {}
    for iid in all_issue_ids:
        row = db.q1('SELECT id, story_points, status, project_id FROM issues WHERE id = ?', iid)
        if row:
            points_by_id[iid] = float(row['story_points'] or 0)
            status_by_id[iid] = row['status']
            project_by_id[iid] = row['project_id']

    last_relevant_ms = min(completed_ms if completed_ms is not None else now, now)
    timeline = []
    for i in range(diff_days + 1):
        day_start = start_ms + i * 24 * 3600 * 1000
        day_end = day_start + 24 * 3600 * 1000 - 1
        date_str = _ms_to_iso(day_start)[:10]
        ideal = max(0, round(committed - (committed / diff_days) * i, 1))

        actual = None
        t = min(day_end, completed_ms if completed_ms is not None else float('inf'), now)
        if t >= started_ms and day_start <= last_relevant_ms:
            total = 0.0
            for iid in all_issue_ids:
                if not member_at(events, iid, t):
                    continue
                cat = category_at(iid, project_by_id[iid], t, status_by_id[iid])
                if cat != 'DONE':
                    total += points_by_id.get(iid, 0)
            actual = total
        timeline.append({'day': i, 'date': date_str, 'ideal': ideal, 'actual': actual})

    return {**base, 'committedPoints': committed, 'timeline': timeline}


def _parse_date_or_now(v, fallback_ms: float) -> float:
    if v:
        try:
            return datetime.fromisoformat(str(v)[:10] + 'T00:00:00+00:00').timestamp() * 1000
        except ValueError:
            pass
        p = parse_ms(str(v))
        if p is not None:
            return p
    return fallback_ms
