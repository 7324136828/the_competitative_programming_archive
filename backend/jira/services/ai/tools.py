import json

from ...db import db
from ...util import new_id, now_iso, now_ms, format_duration
from ..issues import (
    search_issues, get_issue_by_id, create_issue, add_comment,
    update_issue_status, delete_issue_recursive,
)
from ..workflows import get_allowed_transitions_for_status
from ..metrics import compute_issue_metrics, get_issue_events, get_sprint_metrics
from ..history import get_status_category
from .search import rank_tickets
from .normalizer import normalize_ticket


def _resolve_project_id(args: dict, ctx: dict):
    if args and args.get('projectKey'):
        p = db.q1('SELECT id FROM projects WHERE key = ? OR id = ?', args['projectKey'], args['projectKey'])
        if p:
            return p['id']
    if ctx.get('projectId'):
        return ctx['projectId']
    first = db.q1('SELECT id FROM projects ORDER BY created_at ASC LIMIT 1')
    return first['id'] if first else None


def _find_issue(key):
    if key is None:
        return None
    return db.q1('SELECT * FROM issues WHERE key = ? OR id = ?', key, key)


def record_ticket_link(issue_id: str, action: str, source: str, excerpt, ai_request_id):
    db.run(
        """INSERT INTO ai_ticket_links (id, issue_id, ai_request_id, action, source, input_excerpt, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        new_id('atl'), issue_id, ai_request_id, action, source,
        str(excerpt)[:2000] if excerpt else None, now_iso(),
    )


def _compact_issue(i: dict) -> dict:
    assignee = db.q1('SELECT name FROM users WHERE id = ?', i['assignee_id'])['name'] if i['assignee_id'] else None
    sprint = db.q1('SELECT name FROM sprints WHERE id = ?', i['sprint_id'])['name'] if i['sprint_id'] else None
    return {
        'key': i['key'], 'summary': i['summary'], 'status': i['status'],
        'priority': i['priority'], 'type': i['type'], 'assignee': assignee, 'sprint': sprint,
    }


def _handle_list_projects(args, ctx):
    return db.q(
        """SELECT p.id, p.key, p.name, p.description,
                  (SELECT COUNT(*) FROM issues WHERE project_id = p.id) as issueCount
           FROM projects p ORDER BY p.name ASC"""
    )


def _handle_list_users(args, ctx):
    return db.q('SELECT id, name, email, role FROM users ORDER BY name ASC')


def _handle_list_sprints(args, ctx):
    project_id = _resolve_project_id(args, ctx)
    if not project_id:
        return {'error': 'No project found'}
    return db.q(
        """SELECT id, name, goal, state, start_date, end_date, started_at, completed_at,
                  committed_points, completed_points
           FROM sprints WHERE project_id = ? ORDER BY created_at ASC""",
        project_id,
    )


def _handle_search_tickets(args, ctx):
    args = args or {}
    project_id = _resolve_project_id(args, ctx)
    limit = min(max(int(args.get('limit') or 10), 1), 25)

    assignee_id = None
    if args.get('assignee'):
        if args['assignee'] == 'me':
            assignee_id = ctx['userId']
        else:
            u = db.q1('SELECT id FROM users WHERE id = ? OR name = ?', args['assignee'], args['assignee'])
            if not u:
                return {'error': f'User "{args["assignee"]}" not found'}
            assignee_id = u['id']

    if args.get('query'):
        ranked = rank_tickets(args['query'], 'similar', project_id=project_id, limit=limit, include_done=True)
        rows = ranked['results']
        if args.get('status'):
            rows = [r for r in rows if r['status'] == args['status']]
        if args.get('type'):
            rows = [r for r in rows if r['type'] == args['type']]
        if args.get('priority'):
            rows = [r for r in rows if r['priority'] == args['priority']]
        if assignee_id:
            rows = [r for r in rows if (_find_issue(r['key']) or {}).get('assignee_id') == assignee_id]
        return [{
            'key': r['key'], 'summary': r['summary'], 'status': r['status'], 'priority': r['priority'],
            'type': r['type'], 'assignee': r['assigneeName'], 'sprint': r['sprintName'], 'score': r['score'],
        } for r in rows]

    rows = search_issues({
        'projectId': project_id,
        'assigneeId': assignee_id,
        'status': args.get('status'),
        'priority': args.get('priority'),
        'type': args.get('type'),
    })[:limit]
    return [_compact_issue(r) for r in rows]


def _handle_recommend(args, ctx):
    args = args or {}
    project_id = _resolve_project_id(args, ctx)
    limit = min(max(int(args.get('limit') or 5), 1), 20)
    ranked = rank_tickets(args.get('query') or '', 'fix', project_id=project_id,
                          limit=limit, include_done=bool(args.get('includeDone')))
    return {
        'results': [{
            'key': r['key'], 'summary': r['summary'], 'status': r['status'], 'priority': r['priority'],
            'type': r['type'], 'assignee': r['assigneeName'], 'score': r['score'], 'reasons': r['reasons'],
        } for r in ranked['results']],
    }


def _handle_get_ticket(args, ctx):
    row = _find_issue((args or {}).get('key'))
    if not row:
        return {'error': f'Issue {(args or {}).get("key")} not found'}
    issue = get_issue_by_id(row['id'])
    comments = db.q(
        """SELECT c.body, c.created_at, u.name as author FROM comments c
           JOIN users u ON c.author_id = u.id
           WHERE c.issue_id = ? ORDER BY c.created_at DESC LIMIT 5""",
        row['id'],
    )
    prs = db.q('SELECT repo, pr_number, title, status, url FROM pull_requests WHERE issue_id = ?', row['id'])
    worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', row['id'])
    m = compute_issue_metrics(row, get_issue_events(row['id']), worklogs, now_ms())
    return {
        'key': issue['key'],
        'summary': issue['summary'],
        'type': issue['type'],
        'status': issue['status'],
        'statusCategory': get_status_category(issue['project_id'], issue['status']),
        'priority': issue['priority'],
        'storyPoints': issue['story_points'],
        'assignee': issue['assignee_name'],
        'reporter': issue['reporter_name'],
        'sprint': issue['sprint_name'],
        'description': (issue.get('description') or '')[:2000],
        'links': issue['links'],
        'subtasks': [{'key': s['key'], 'summary': s['summary'], 'status': s['status']} for s in issue['subtasks']],
        'comments': comments,
        'pullRequests': prs,
        'metrics': {
            'createdAt': m['createdAt'],
            'firstStartedAt': m['firstStartedAt'],
            'resolvedAt': m['resolvedAt'],
            'cycleTime': format_duration(m['cycleTimeSeconds']),
            'leadTime': format_duration(m['leadTimeSeconds']),
            'activeTime': format_duration(m['activeTimeSeconds']),
            'loggedMinutes': m['loggedMinutes'],
        },
    }


def _handle_create_ticket(args, ctx):
    args = args or {}
    project_id = _resolve_project_id(args, ctx)
    if not project_id:
        return {'error': 'No project found'}
    normalized = normalize_ticket({
        'type': args.get('type'), 'summary': args.get('summary'),
        'description': args.get('description'), 'priority': args.get('priority'),
        'storyPoints': args.get('storyPoints'),
    })
    if not normalized:
        return {'error': 'A non-empty summary is required'}

    def _work():
        issue = create_issue({
            'projectId': project_id,
            'type': normalized['type'],
            'summary': normalized['summary'],
            'description': normalized['description'],
            'priority': normalized['priority'],
            'storyPoints': normalized['storyPoints'],
            'assigneeId': args.get('assigneeId'),
            'sprintId': args.get('sprintId'),
        }, ctx['userId'], source='ai')

        warnings = []
        if isinstance(args.get('relatesTo'), list):
            for key in args['relatesTo']:
                target = _find_issue(key)
                if not target:
                    warnings.append(f'Unknown issue key {key}')
                    continue
                try:
                    db.run(
                        'INSERT INTO issue_links (id, source_id, target_id, link_type) VALUES (?, ?, ?, ?)',
                        new_id('link'), issue['id'], target['id'], 'relates_to',
                    )
                except Exception as e:
                    warnings.append(f'Could not link {key}: {e}')
        record_ticket_link(issue['id'], 'created',
                           'assistant' if ctx.get('via') == 'assistant' else 'tool',
                           normalized['summary'], ctx.get('aiRequestId'))
        return issue, warnings

    issue, warnings = db.with_transaction(_work)
    return {
        'key': issue['key'], 'id': issue['id'], 'summary': issue['summary'],
        'status': issue['status'], 'warnings': warnings,
    }


def _handle_add_comment(args, ctx):
    args = args or {}
    issue = _find_issue(args.get('key'))
    if not issue:
        return {'error': f'Issue {args.get("key")} not found'}
    comment = add_comment(issue['id'], ctx['userId'], args.get('body'))
    record_ticket_link(issue['id'], 'commented',
                       'assistant' if ctx.get('via') == 'assistant' else 'tool',
                       str(args.get('body'))[:500], ctx.get('aiRequestId'))
    return {'ok': True, 'commentId': comment['id']}


def _handle_transition(args, ctx):
    args = args or {}
    issue = _find_issue(args.get('key'))
    if not issue:
        return {'error': f'Issue {args.get("key")} not found'}
    try:
        update_issue_status(issue['id'], args.get('status'), ctx['userId'], source='ai')
        return {'ok': True, 'key': issue['key'], 'status': args.get('status')}
    except Exception as err:
        allowed = get_allowed_transitions_for_status(issue['project_id'], issue['status'])
        return {'error': str(err), 'allowedTransitions': [t['to_status'] for t in allowed]}


def _handle_task_metrics(args, ctx):
    issue = _find_issue((args or {}).get('key'))
    if not issue:
        return {'error': f'Issue {(args or {}).get("key")} not found'}
    worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', issue['id'])
    m = compute_issue_metrics(issue, get_issue_events(issue['id']), worklogs, now_ms())
    return {
        'key': issue['key'],
        'status': m['currentStatus'],
        'createdAt': m['createdAt'],
        'firstStartedAt': m['firstStartedAt'],
        'resolvedAt': m['resolvedAt'],
        'leadTime': format_duration(m['leadTimeSeconds']),
        'cycleTime': format_duration(m['cycleTimeSeconds']),
        'activeTime': format_duration(m['activeTimeSeconds']),
        'waitTime': format_duration(m['waitTimeSeconds']),
        'elapsed': format_duration(m['elapsedSeconds']),
        'reopenCount': m['reopenCount'],
        'transitionCount': m['transitionCount'],
        'loggedMinutes': m['loggedMinutes'],
        'timeInStatus': {k: format_duration(v) for k, v in m['timeInStatus'].items()},
    }


def _handle_delete_ticket(args, ctx):
    issue = _find_issue((args or {}).get('key'))
    if not issue:
        return {'error': f'Issue {(args or {}).get("key")} not found'}
    child_count = db.q1('SELECT COUNT(*) as c FROM issues WHERE parent_id = ?', issue['id'])['c']
    delete_issue_recursive(issue['id'])
    return {'ok': True, 'key': issue['key'], 'summary': issue['summary'], 'deletedSubtasks': child_count}


def _handle_activity_log(args, ctx):
    args = args or {}
    limit = min(max(int(args.get('limit') or 20), 1), 100)
    clauses = []
    params = []
    if args.get('user'):
        if args['user'] == 'me':
            clauses.append('user_id = ?')
            params.append(ctx['userId'])
        else:
            clauses.append('(user_id = ? OR user_name = ?)')
            params += [str(args['user']), str(args['user'])]
    if args.get('method'):
        clauses.append('method = ?')
        params.append(str(args['method']).upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db.q(
        f"""SELECT id, created_at, user_name, user_id, method, path, status_code, duration_ms, summary
            FROM activity_log {where} ORDER BY id DESC LIMIT ?""",
        *params, limit,
    )
    return {'count': len(rows), 'rows': rows}


def _handle_sprint_metrics(args, ctx):
    args = args or {}
    sprint = None
    if args.get('sprintId'):
        sprint = db.q1('SELECT * FROM sprints WHERE id = ?', args['sprintId'])
    else:
        project_id = _resolve_project_id(args, ctx)
        if not project_id:
            return {'error': 'No project found'}
        if args.get('which') == 'last_closed':
            sprint = db.q1(
                "SELECT * FROM sprints WHERE project_id = ? AND state = 'closed' ORDER BY completed_at DESC LIMIT 1",
                project_id)
        else:
            sprint = db.q1(
                "SELECT * FROM sprints WHERE project_id = ? AND state = 'active' ORDER BY started_at DESC LIMIT 1",
                project_id) or db.q1(
                "SELECT * FROM sprints WHERE project_id = ? AND state = 'closed' ORDER BY completed_at DESC LIMIT 1",
                project_id)
    if not sprint:
        return {'error': 'No matching sprint found'}
    m = get_sprint_metrics(sprint['id'])
    fd = format_duration
    return {
        'id': m['id'], 'name': m['name'], 'state': m['state'],
        'startedAt': m['startedAt'], 'completedAt': m['completedAt'],
        'duration': fd(m['durationSeconds']),
        'committedPoints': m['committedPoints'],
        'committedIssueCount': m['committedIssueCount'],
        'completedPoints': m['completedPoints'],
        'completedIssueCount': m['completedIssueCount'],
        'addedAfterStart': m['addedAfterStart'],
        'removedAfterStart': m['removedAfterStart'],
        'carriedOver': m['carriedOver'],
        'velocityPoints': m['velocityPoints'],
        'throughput': m['throughput'],
        'completionRatePercent': m['completionRatePercent'],
        'scopeCompletionPercent': m['scopeCompletionPercent'],
        'activeTimeInSprint': fd(m['activeSecondsInSprint']),
        'loggedMinutes': m['loggedMinutes'],
        'cycleTime': {k: fd(m['cycleTime'][k]) for k in ('avg', 'median', 'min', 'max')},
        'leadTime': {k: fd(m['leadTime'][k]) for k in ('avg', 'median', 'min', 'max')},
        'issues': [{
            'key': i['key'], 'summary': i['summary'], 'status': i['status'],
            'storyPoints': i['storyPoints'], 'assignee': i['assigneeName'], 'outcome': i['outcome'],
        } for i in m['issues'][:30]],
    }


TOOLS = [
    {
        'name': 'list_projects',
        'description': 'List all Jira projects with their keys, names, and issue counts.',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'mutates': False,
        'handler': _handle_list_projects,
    },
    {
        'name': 'list_users',
        'description': 'List all users with id, name, email, and role.',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'mutates': False,
        'handler': _handle_list_users,
    },
    {
        'name': 'list_sprints',
        'description': 'List sprints for a project with state, dates, and point totals.',
        'parameters': {
            'type': 'object',
            'properties': {'projectKey': {'type': 'string', 'description': 'Project key, e.g. CP'}},
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_list_sprints,
    },
    {
        'name': 'search_tickets',
        'description': 'Search tickets by keywords and filters. Returns compact rows sorted by relevance when a query is given.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Free-text search (keywords, error text)'},
                'projectKey': {'type': 'string'},
                'status': {'type': 'string'},
                'assignee': {'type': 'string', 'description': "'me', a user id, or a user name"},
                'type': {'type': 'string'},
                'priority': {'type': 'string'},
                'limit': {'type': 'number', 'description': 'Max results (default 10, max 25)'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_search_tickets,
    },
    {
        'name': 'recommend_tickets_to_fix',
        'description': 'Rank existing tickets worth fixing for a query (keywords, error text, links). Deterministic keyword/link ranking.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'What you want to fix (keywords, error, link)'},
                'projectKey': {'type': 'string'},
                'limit': {'type': 'number', 'description': 'Default 5'},
                'includeDone': {'type': 'boolean'},
            },
            'required': ['query'],
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_recommend,
    },
    {
        'name': 'get_ticket',
        'description': 'Get full details for a ticket by key: fields, links, subtasks, recent comments, pull requests, and a metrics summary.',
        'parameters': {
            'type': 'object',
            'properties': {'key': {'type': 'string', 'description': 'Issue key, e.g. CP-1'}},
            'required': ['key'],
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_get_ticket,
    },
    {
        'name': 'create_ticket',
        'description': 'Create a new ticket. Requires at least a summary.',
        'parameters': {
            'type': 'object',
            'properties': {
                'projectKey': {'type': 'string'},
                'type': {'type': 'string', 'description': 'Bug|Story|Task|Epic'},
                'summary': {'type': 'string'},
                'description': {'type': 'string'},
                'priority': {'type': 'string', 'description': 'Highest|High|Medium|Low|Lowest'},
                'storyPoints': {'type': 'number'},
                'assigneeId': {'type': 'string'},
                'sprintId': {'type': 'string'},
                'relatesTo': {'type': 'array', 'items': {'type': 'string'},
                              'description': 'Issue keys to link as relates_to'},
            },
            'required': ['summary'],
            'additionalProperties': False,
        },
        'mutates': True,
        'handler': _handle_create_ticket,
    },
    {
        'name': 'add_comment',
        'description': 'Add a comment to a ticket.',
        'parameters': {
            'type': 'object',
            'properties': {'key': {'type': 'string'}, 'body': {'type': 'string'}},
            'required': ['key', 'body'],
            'additionalProperties': False,
        },
        'mutates': True,
        'handler': _handle_add_comment,
    },
    {
        'name': 'transition_ticket',
        'description': 'Move a ticket to a new status, enforcing the project workflow.',
        'parameters': {
            'type': 'object',
            'properties': {
                'key': {'type': 'string'},
                'status': {'type': 'string', 'description': 'Target status name, e.g. "In Progress"'},
            },
            'required': ['key', 'status'],
            'additionalProperties': False,
        },
        'mutates': True,
        'handler': _handle_transition,
    },
    {
        'name': 'get_task_metrics',
        'description': 'Get exact task-level flow metrics for a ticket (cycle/lead time, time in status, worklogs).',
        'parameters': {
            'type': 'object',
            'properties': {'key': {'type': 'string'}},
            'required': ['key'],
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_task_metrics,
    },
    {
        'name': 'delete_ticket',
        'description': 'Permanently delete a ticket and all of its subtasks (recursive). Destructive — confirm the user really wants deletion.',
        'parameters': {
            'type': 'object',
            'properties': {'key': {'type': 'string', 'description': 'Issue key, e.g. PROJ-2'}},
            'required': ['key'],
            'additionalProperties': False,
        },
        'mutates': True,
        'handler': _handle_delete_ticket,
    },
    {
        'name': 'get_activity_log',
        'description': 'Read the user activity audit trail: every step users took (HTTP requests and UI actions), who did it, and when. Most recent first.',
        'parameters': {
            'type': 'object',
            'properties': {
                'limit': {'type': 'number', 'description': 'Max rows (default 20, max 100)'},
                'user': {'type': 'string', 'description': "Filter by user id, name, or 'me'"},
                'method': {'type': 'string', 'description': 'Filter by method, e.g. POST, GET, UI'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_activity_log,
    },
    {
        'name': 'get_sprint_metrics',
        'description': 'Get sprint metrics: committed/completed points, velocity, scope changes, cycle/lead time stats.',
        'parameters': {
            'type': 'object',
            'properties': {
                'sprintId': {'type': 'string'},
                'projectKey': {'type': 'string'},
                'which': {'type': 'string',
                          'description': "'active' or 'last_closed' (default: active, falls back to last closed)"},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_sprint_metrics,
    },
]

TOOL_BY_NAME = {t['name']: t for t in TOOLS}


def openai_tool_specs(can_mutate: bool) -> list:
    return [
        {'type': 'function',
         'function': {'name': t['name'], 'description': t['description'], 'parameters': t['parameters']}}
        for t in TOOLS if can_mutate or not t['mutates']
    ]
