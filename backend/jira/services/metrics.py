from datetime import datetime, timezone

from ..db import db
from ..util import to_iso, parse_ms, now_ms
from .history import get_status_category


def get_issue_events(issue_id: str) -> list[dict]:
    return db.q(
        """SELECT h.*, u.name as changed_by_name
           FROM issue_status_history h
           LEFT JOIN users u ON h.changed_by = u.id
           WHERE h.issue_id = ?
           ORDER BY h.changed_at ASC, h.rowid ASC""",
        issue_id,
    )


def _ms_to_iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def compute_issue_metrics(issue: dict, events: list[dict], worklogs: list[dict], now: float | None = None) -> dict:
    now = now_ms() if now is None else now
    evts = list(events)
    if not evts:
        created_at = to_iso(issue.get('created_at')) or _ms_to_iso(now)
        evts = [{
            'id': 'synthetic', 'issue_id': issue['id'], 'from_status': None,
            'to_status': issue['status'], 'from_category': None,
            'to_category': get_status_category(issue['project_id'], issue['status']),
            'changed_by': None, 'changed_by_name': None, 'source': 'system',
            'changed_at': created_at,
        }]
    elif evts[0]['from_status'] is not None:
        # Legacy partial history: synthesize the creation event covering
        # [issue.created_at, first recorded transition) in the first from_status.
        first = evts[0]
        issue_created = to_iso(issue.get('created_at'))
        first_ms = parse_ms(first['changed_at'])
        issue_created_ms = parse_ms(issue_created)
        if issue_created_ms is not None and first_ms is not None and issue_created_ms < first_ms:
            at = issue_created
        else:
            at = first['changed_at'] if first_ms is not None else (issue_created or first['changed_at'])
        evts = [{
            'id': 'synthetic', 'issue_id': issue['id'], 'from_status': None,
            'to_status': first['from_status'], 'from_category': None,
            'to_category': first['from_category'] or get_status_category(issue['project_id'], first['from_status']),
            'changed_by': first['changed_by'], 'changed_by_name': first.get('changed_by_name'),
            'source': 'system', 'changed_at': at,
        }] + evts

    created_at = evts[0]['changed_at']
    created_ms = parse_ms(created_at)
    if created_ms is None:
        created_ms = now

    # Resolved = last event is DONE; resolution instant is start of trailing DONE run.
    resolved_at = None
    resolved_ms = None
    if evts[-1]['to_category'] == 'DONE':
        i = len(evts) - 1
        while i - 1 >= 0 and evts[i - 1]['to_category'] == 'DONE':
            i -= 1
        resolved_at = evts[i]['changed_at']
        resolved_ms = parse_ms(resolved_at)

    clock_end_ms = resolved_ms if resolved_ms is not None else now

    status_ms: dict[str, float] = {}
    category_ms: dict[str, float] = {'TODO': 0, 'IN_PROGRESS': 0, 'DONE': 0}
    timeline = []
    active_ms = 0.0
    active_intervals = []

    for i, e in enumerate(evts):
        start = parse_ms(e['changed_at'])
        nxt = parse_ms(evts[i + 1]['changed_at']) if i + 1 < len(evts) else clock_end_ms
        end = min(nxt, clock_end_ms)
        dur = end - start
        if e['to_category'] == 'IN_PROGRESS' and end > start:
            active_intervals.append({'start': start, 'end': end})
        if dur <= 0:
            continue
        status_ms[e['to_status']] = status_ms.get(e['to_status'], 0) + dur
        category_ms[e['to_category']] = category_ms.get(e['to_category'], 0) + dur
        if e['to_category'] == 'IN_PROGRESS':
            active_ms += dur
        timeline.append({
            'status': e['to_status'],
            'category': e['to_category'],
            'from': e['changed_at'],
            'to': _ms_to_iso(end),
            'seconds': round(dur / 1000),
            'changedByName': e.get('changed_by_name'),
            'source': e['source'],
        })

    first_started_at = None
    for e in evts:
        t = parse_ms(e['changed_at'])
        if e['to_category'] == 'IN_PROGRESS' and t <= clock_end_ms:
            first_started_at = e['changed_at']
            break

    time_in_status = {k: round(v / 1000) for k, v in status_ms.items() if round(v / 1000) > 0}
    time_in_category = {k: round(v / 1000) for k, v in category_ms.items()}

    reopen_count = sum(1 for e in evts if e['from_category'] == 'DONE' and e['to_category'] != 'DONE')
    transition_count = sum(1 for e in evts if e['from_status'] is not None)

    logged_minutes = sum(w.get('time_spent_minutes') or 0 for w in worklogs)
    original_estimate = issue.get('original_estimate_minutes') or 0

    return {
        'issueId': issue['id'],
        'key': issue['key'],
        'summary': issue.get('summary'),
        'type': issue.get('type'),
        'priority': issue.get('priority'),
        'storyPoints': issue.get('story_points'),
        'currentStatus': evts[-1]['to_status'],
        'currentStatusCategory': evts[-1]['to_category'],
        'currentStatusSince': evts[-1]['changed_at'],
        'isResolved': resolved_at is not None,
        'createdAt': created_at,
        'firstStartedAt': first_started_at,
        'resolvedAt': resolved_at,
        'leadTimeSeconds': round((resolved_ms - created_ms) / 1000) if resolved_ms is not None else None,
        'cycleTimeSeconds': round((resolved_ms - parse_ms(first_started_at)) / 1000)
            if resolved_ms is not None and first_started_at else None,
        'elapsedSeconds': round((clock_end_ms - created_ms) / 1000),
        'activeTimeSeconds': round(active_ms / 1000),
        'waitTimeSeconds': time_in_category['TODO'],
        'doneTimeSeconds': time_in_category['DONE'],
        'timeInStatus': time_in_status,
        'timeInCategory': time_in_category,
        'reopenCount': reopen_count,
        'transitionCount': transition_count,
        'loggedMinutes': logged_minutes,
        'originalEstimateMinutes': original_estimate,
        'remainingEstimateMinutes': issue.get('remaining_estimate_minutes') or 0,
        'estimateAccuracy': round(logged_minutes / original_estimate * 100) / 100 if original_estimate > 0 else None,
        'timeline': timeline,
        '_activeIntervals': active_intervals,
    }


def median(values: list) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    m = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return round(m)


def stats(values: list) -> dict:
    nums = [v for v in values if v is not None]
    if not nums:
        return {'avg': None, 'median': None, 'min': None, 'max': None}
    return {
        'avg': round(sum(nums) / len(nums)),
        'median': median(nums),
        'min': min(nums),
        'max': max(nums),
    }


def get_sprint_events(sprint_id: str) -> list[dict]:
    return db.q(
        'SELECT * FROM sprint_issue_events WHERE sprint_id = ? ORDER BY changed_at ASC, rowid ASC',
        sprint_id,
    )


def member_at(events: list[dict], issue_id: str, t: float) -> bool:
    member = False
    for e in events:
        if e['issue_id'] != issue_id:
            continue
        et = parse_ms(e['changed_at'])
        if et is None or et > t:
            break
        if e['event'] in ('committed', 'added'):
            member = True
        elif e['event'] == 'removed':
            member = False
    return member


def category_at(issue_id: str, project_id: str, t: float, fallback_status: str) -> str:
    iso = _ms_to_iso(t)
    evt = db.q1(
        """SELECT to_category FROM issue_status_history
           WHERE issue_id = ? AND changed_at <= ?
           ORDER BY changed_at DESC, rowid DESC LIMIT 1""",
        issue_id, iso,
    )
    if evt:
        return evt['to_category']
    earliest = db.q1(
        """SELECT from_category, from_status FROM issue_status_history
           WHERE issue_id = ? ORDER BY changed_at ASC, rowid ASC LIMIT 1""",
        issue_id,
    )
    if earliest and earliest['from_category']:
        return earliest['from_category']
    if earliest and earliest['from_status']:
        return get_status_category(project_id, earliest['from_status'])
    return get_status_category(project_id, fallback_status)


def _day_ms(date_str) -> float | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str)[:10] + 'T00:00:00+00:00').timestamp() * 1000
    except ValueError:
        return None


def get_sprint_metrics(sprint_id: str, now: float | None = None):
    now = now_ms() if now is None else now
    sprint = db.q1('SELECT * FROM sprints WHERE id = ?', sprint_id)
    if not sprint:
        return None

    events = get_sprint_events(sprint_id)
    started_ms = parse_ms(sprint.get('started_at'))
    completed_ms = parse_ms(sprint.get('completed_at'))
    clock_end_ms = completed_ms if completed_ms is not None else now

    event_issue_ids = {e['issue_id'] for e in events}
    current_issues = db.q('SELECT * FROM issues WHERE sprint_id = ?', sprint_id)
    all_ids = list(event_issue_ids | {i['id'] for i in current_issues})
    issue_rows = db.q(
        f"""SELECT i.*, u.name as assignee_name FROM issues i
            LEFT JOIN users u ON i.assignee_id = u.id
            WHERE i.id IN ({','.join('?' * len(all_ids))})""",
        *all_ids,
    ) if all_ids else []
    issue_by_id = {i['id']: i for i in issue_rows}

    last_event: dict[str, dict] = {}
    added_after_start_ids: set[str] = set()
    added_pts = {'issues': 0, 'points': 0.0}
    removed_pts = {'issues': 0, 'points': 0.0}
    carried_issues = 0
    carried_points = 0.0
    counted_added: set[str] = set()
    counted_removed: set[str] = set()

    for e in events:
        last_event[e['issue_id']] = e
        et = parse_ms(e['changed_at'])
        if started_ms is not None and et is not None and started_ms < et <= clock_end_ms:
            if e['event'] == 'added' and e['issue_id'] not in counted_added:
                counted_added.add(e['issue_id'])
                added_pts['issues'] += 1
                added_pts['points'] += float(e['story_points'] or 0)
            if e['event'] == 'removed' and e['issue_id'] not in counted_removed:
                counted_removed.add(e['issue_id'])
                removed_pts['issues'] += 1
                removed_pts['points'] += float(e['story_points'] or 0)
        if e['event'] == 'added' and started_ms is not None and et is not None and et > started_ms:
            added_after_start_ids.add(e['issue_id'])
        if e['event'] == 'carried_over':
            carried_issues += 1
            carried_points += float(e['story_points'] or 0)

    closed = sprint['state'] == 'closed'
    issue_metrics: dict[str, dict] = {}
    issue_list = []

    for iid in all_ids:
        issue = issue_by_id.get(iid)
        if not issue:
            continue
        evts = get_issue_events(iid)
        worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', iid)
        m = compute_issue_metrics(issue, evts, worklogs, now)
        issue_metrics[iid] = m

        last = last_event.get(iid)
        if last and last['event'] == 'completed':
            outcome = 'completed'
        elif last and last['event'] == 'carried_over':
            outcome = 'carried_over'
        elif last and last['event'] == 'removed' and issue['sprint_id'] != sprint_id:
            outcome = 'removed'
        else:
            cat = get_status_category(issue['project_id'], issue['status'])
            outcome = 'completed' if cat == 'DONE' else ('in_progress' if cat == 'IN_PROGRESS' else 'todo')

        issue_list.append({
            'id': issue['id'],
            'key': issue['key'],
            'summary': issue['summary'],
            'type': issue['type'],
            'status': issue['status'],
            'statusCategory': get_status_category(issue['project_id'], issue['status']),
            'storyPoints': issue['story_points'],
            'assigneeId': issue['assignee_id'],
            'assigneeName': issue.get('assignee_name'),
            'addedAfterStart': iid in added_after_start_ids,
            'outcome': outcome,
            'metrics': {
                'createdAt': m['createdAt'],
                'firstStartedAt': m['firstStartedAt'],
                'resolvedAt': m['resolvedAt'],
                'cycleTimeSeconds': m['cycleTimeSeconds'],
                'leadTimeSeconds': m['leadTimeSeconds'],
                'activeTimeSeconds': m['activeTimeSeconds'],
                'loggedMinutes': m['loggedMinutes'],
            },
        })

    completed_issues = [i for i in issue_list if i['outcome'] == 'completed']
    cycle_times = [issue_metrics[i['id']]['cycleTimeSeconds'] for i in completed_issues]
    lead_times = [issue_metrics[i['id']]['leadTimeSeconds'] for i in completed_issues]

    active_seconds_in_sprint = None
    if started_ms is not None:
        total_ms = 0.0
        for i in issue_list:
            if i['outcome'] == 'removed':
                continue
            for iv in issue_metrics[i['id']]['_activeIntervals']:
                s = max(iv['start'], started_ms)
                e = min(iv['end'], clock_end_ms)
                if e > s:
                    total_ms += e - s
        active_seconds_in_sprint = round(total_ms / 1000)

    logged_minutes = None
    if started_ms is not None:
        start_day = _ms_to_iso(started_ms)[:10]
        end_day = _ms_to_iso(clock_end_ms)[:10]
        total = 0
        for i in issue_list:
            if i['outcome'] == 'removed':
                continue
            for r in db.q(
                """SELECT time_spent_minutes FROM worklogs
                   WHERE issue_id = ? AND substr(started_at, 1, 10) >= ? AND substr(started_at, 1, 10) <= ?""",
                i['id'], start_day, end_day,
            ):
                total += r['time_spent_minutes'] or 0
        logged_minutes = total

    committed_issue_count = sprint['committed_issue_count'] if started_ms is not None else None
    committed_points = sprint['committed_points'] if started_ms is not None else None

    if closed:
        completed_issue_count = sprint['completed_issue_count'] or 0
        completed_points = sprint['completed_points'] or 0
        carried_over = {'issues': carried_issues, 'points': carried_points}
        final_scope_points = completed_points + carried_points
    else:
        done_current = [i for i in current_issues
                        if get_status_category(i['project_id'], i['status']) == 'DONE']
        completed_issue_count = len(done_current)
        completed_points = sum(float(i['story_points'] or 0) for i in done_current)
        carried_over = None
        final_scope_points = sum(float(i['story_points'] or 0) for i in current_issues)

    by_assignee: dict = {}
    for i in issue_list:
        if i['outcome'] == 'removed':
            continue
        key = i['assigneeId']
        row = by_assignee.setdefault(key, {
            'assigneeId': key,
            'assigneeName': i['assigneeName'] or 'Unassigned',
            'completedIssues': 0,
            'completedPoints': 0.0,
            'activeMs': 0.0,
        })
        if i['outcome'] == 'completed':
            row['completedIssues'] += 1
            row['completedPoints'] += float(i['storyPoints'] or 0)
        if started_ms is not None:
            for iv in issue_metrics[i['id']]['_activeIntervals']:
                s = max(iv['start'], started_ms)
                e = min(iv['end'], clock_end_ms)
                if e > s:
                    row['activeMs'] += e - s

    by_assignee_list = [
        {k: v for k, v in r.items() if k != 'activeMs'} | {'activeSeconds': round(r['activeMs'] / 1000)}
        for r in by_assignee.values()
    ]

    start_date_ms = _day_ms(sprint.get('start_date'))
    end_date_ms = _day_ms(sprint.get('end_date'))

    return {
        'id': sprint['id'],
        'projectId': sprint['project_id'],
        'name': sprint['name'],
        'goal': sprint['goal'],
        'state': sprint['state'],
        'plannedStart': sprint['start_date'],
        'plannedEnd': sprint['end_date'],
        'startedAt': sprint['started_at'],
        'completedAt': sprint['completed_at'],
        'durationSeconds': round((clock_end_ms - started_ms) / 1000) if started_ms is not None else None,
        'plannedDurationDays': round((end_date_ms - start_date_ms) / 86400000)
            if start_date_ms is not None and end_date_ms is not None else None,
        'committedIssueCount': committed_issue_count,
        'committedPoints': committed_points,
        'addedAfterStart': added_pts if started_ms is not None else {'issues': 0, 'points': 0},
        'removedAfterStart': removed_pts if started_ms is not None else {'issues': 0, 'points': 0},
        'completedIssueCount': completed_issue_count,
        'completedPoints': completed_points,
        'carriedOver': carried_over,
        'finalScopePoints': final_scope_points,
        'velocityPoints': completed_points,
        'throughput': completed_issue_count,
        'completionRatePercent': round(completed_points / committed_points * 1000) / 10
            if committed_points and committed_points > 0 else None,
        'scopeCompletionPercent': round(completed_points / final_scope_points * 1000) / 10
            if final_scope_points > 0 else None,
        'activeSecondsInSprint': active_seconds_in_sprint,
        'loggedMinutes': logged_minutes,
        'cycleTime': stats(cycle_times),
        'leadTime': stats(lead_times),
        'issues': issue_list,
        'byAssignee': by_assignee_list,
    }


def get_project_metrics(project_id: str, now: float | None = None):
    now = now_ms() if now is None else now
    project = db.q1('SELECT * FROM projects WHERE id = ?', project_id)
    if not project:
        return None

    sprints = db.q(
        'SELECT * FROM sprints WHERE project_id = ? ORDER BY COALESCE(started_at, start_date, created_at) ASC',
        project_id,
    )
    sprint_rows = []
    for s in sprints:
        m = get_sprint_metrics(s['id'], now)
        sprint_rows.append({
            'id': s['id'], 'name': s['name'], 'state': s['state'],
            'startedAt': s['started_at'], 'completedAt': s['completed_at'],
            'durationSeconds': m['durationSeconds'],
            'committedPoints': m['committedPoints'],
            'completedPoints': m['completedPoints'],
            'completionRatePercent': m['completionRatePercent'],
            'throughput': m['throughput'],
            'avgCycleTimeSeconds': m['cycleTime']['avg'],
        })

    closed_sprints = sorted(
        [s for s in sprints if s['state'] == 'closed' and s['completed_points'] is not None],
        key=lambda s: str(s['completed_at'] or ''), reverse=True,
    )[:3]
    last_closed = [{'id': s['id'], 'name': s['name'], 'completedPoints': s['completed_points'],
                    'completedAt': s['completed_at']} for s in closed_sprints]
    avg_velocity = round(sum(s['completed_points'] or 0 for s in closed_sprints) / len(closed_sprints) * 10) / 10 \
        if closed_sprints else None

    issues = db.q('SELECT * FROM issues WHERE project_id = ?', project_id)
    cycles = []
    leads = []
    resolved_last7 = 0
    resolved_last30 = 0
    resolved_count = 0
    for issue in issues:
        worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', issue['id'])
        m = compute_issue_metrics(issue, get_issue_events(issue['id']), worklogs, now)
        if m['isResolved']:
            resolved_count += 1
            if m['cycleTimeSeconds'] is not None:
                cycles.append(m['cycleTimeSeconds'])
            if m['leadTimeSeconds'] is not None:
                leads.append(m['leadTimeSeconds'])
            rms = parse_ms(m['resolvedAt'])
            if rms is not None:
                if now - rms <= 7 * 86400000:
                    resolved_last7 += 1
                if now - rms <= 30 * 86400000:
                    resolved_last30 += 1

    return {
        'projectId': project_id,
        'sprints': sprint_rows,
        'velocity': {'averageVelocityLast3': avg_velocity, 'lastClosedSprints': last_closed},
        'flow': {
            'openIssues': len(issues) - resolved_count,
            'resolvedIssues': resolved_count,
            'avgCycleTimeSeconds': round(sum(cycles) / len(cycles)) if cycles else None,
            'medianCycleTimeSeconds': median(cycles),
            'avgLeadTimeSeconds': round(sum(leads) / len(leads)) if leads else None,
            'medianLeadTimeSeconds': median(leads),
            'resolvedLast7Days': resolved_last7,
            'resolvedLast30Days': resolved_last30,
        },
    }
