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


def _json_value(value, fallback):
    if isinstance(value, type(fallback)):
        return value
    try:
        parsed = json.loads(value or '')
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _short_text(value, limit=2000):
    text = str(value or '')
    return text if len(text) <= limit else text[:limit] + '…'


def _archive_available():
    return bool(db.q1("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'problems'"))


def _study_context():
    # Imported lazily so Jira-only processes do not initialize study storage
    # merely by importing the assistant tool registry.
    from ....study.state import get_active_workspace_id, get_content_store
    return get_content_store(), get_active_workspace_id()


def _resolve_study_workspace(args):
    store, active_id = _study_context()
    workspaces = store.list_all_workspaces()
    selector = str((args or {}).get('workspace') or '').strip()
    if not selector:
        workspace = next((item for item in workspaces if item['id'] == active_id), None)
        return store, workspace, None if workspace else 'No study sets have been imported'

    folded = selector.casefold()
    exact = [item for item in workspaces if str(item['id']).casefold() == folded
             or str(item['name']).casefold() == folded]
    if len(exact) == 1:
        return store, exact[0], None
    partial = [item for item in workspaces if folded in str(item['name']).casefold()]
    if len(partial) == 1:
        return store, partial[0], None
    if len(exact) > 1 or len(partial) > 1:
        matches = exact or partial
        return store, None, {
            'message': f'Study set "{selector}" is ambiguous',
            'matches': [{'id': item['id'], 'name': item['name']} for item in matches[:10]],
        }
    return store, None, f'Study set "{selector}" not found'


def _handle_search_coding_problems(args, ctx):
    if not _archive_available():
        return {'error': 'The coding problem archive is not initialized'}
    args = args or {}
    limit = min(max(int(args.get('limit') or 10), 1), 25)
    clauses = []
    params = []
    query = str(args.get('query') or '').strip()
    if query:
        clauses.append('(p.title LIKE ? OR p.problem_statements LIKE ? OR p.tags LIKE ?)')
        term = f'%{query}%'
        params.extend([term, term, term])
    if args.get('difficulty'):
        clauses.append('lower(p.difficulty) = lower(?)')
        params.append(str(args['difficulty']))
    if args.get('language'):
        clauses.append('lower(p.language) = lower(?)')
        params.append(str(args['language']))
    solved = str(args.get('solved') or 'all').lower()
    if solved not in ('all', 'solved', 'unsolved'):
        return {'error': 'solved must be all, solved, or unsolved'}
    accepted = "EXISTS (SELECT 1 FROM submissions s WHERE s.problem_id = p.id AND s.status = 'Accepted' AND s.verified = 1)"
    if solved == 'solved':
        clauses.append(accepted)
    elif solved == 'unsolved':
        clauses.append(f'NOT {accepted}')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db.q(
        f"""SELECT p.id, p.title, p.difficulty, p.language, p.tags, p.source,
                   {accepted} AS is_solved,
                   (SELECT COUNT(*) FROM submissions s WHERE s.problem_id = p.id) AS attempt_count,
                   (SELECT s.status FROM submissions s WHERE s.problem_id = p.id ORDER BY s.id DESC LIMIT 1) AS last_verdict,
                   i.key AS story_key
            FROM problems p LEFT JOIN issues i ON i.problem_id = p.id
            {where}
            ORDER BY CASE WHEN lower(p.title) = lower(?) THEN 0 ELSE 1 END, p.id DESC LIMIT ?""",
        *params, query, limit,
    )
    return {
        'count': len(rows),
        'problems': [{
            'id': row['id'], 'title': row['title'], 'difficulty': row['difficulty'],
            'language': row['language'], 'tags': _json_value(row.get('tags'), []),
            'source': row.get('source'), 'solved': bool(row['is_solved']),
            'attemptCount': row['attempt_count'], 'lastVerdict': row['last_verdict'],
            'storyKey': row['story_key'],
        } for row in rows],
    }


def _handle_get_coding_problem(args, ctx):
    if not _archive_available():
        return {'error': 'The coding problem archive is not initialized'}
    problem_id = (args or {}).get('problemId')
    try:
        problem_id = int(problem_id)
    except (TypeError, ValueError):
        return {'error': 'problemId must be an integer'}
    problem = db.q1(
        """SELECT p.*,
                  EXISTS(SELECT 1 FROM submissions s WHERE s.problem_id = p.id
                         AND s.status = 'Accepted' AND s.verified = 1) AS is_solved,
                  i.key AS story_key
           FROM problems p LEFT JOIN issues i ON i.problem_id = p.id WHERE p.id = ?""",
        problem_id,
    )
    if not problem:
        return {'error': f'Coding problem {problem_id} not found'}
    submissions = db.q(
        """SELECT id, language, status, verified, runtime_ms, error, phase, created_at
           FROM submissions WHERE problem_id = ? ORDER BY id DESC LIMIT 5""",
        problem_id,
    )
    return {
        'id': problem['id'], 'title': problem['title'],
        'statement': _short_text(problem['problem_statements'], 12000),
        'sampleInputOutput': _json_value(problem.get('sample_input_output'), []),
        'hints': _json_value(problem.get('hints'), []),
        'tags': _json_value(problem.get('tags'), []),
        'difficulty': problem['difficulty'], 'language': problem['language'],
        'source': problem.get('source'), 'solved': bool(problem['is_solved']),
        'storyKey': problem['story_key'],
        'recentAttempts': [{
            'id': row['id'], 'language': row['language'], 'status': row['status'],
            'verified': bool(row['verified']), 'runtimeMs': row['runtime_ms'],
            'error': _short_text(row.get('error'), 500), 'phase': row['phase'],
            'createdAt': row['created_at'],
        } for row in submissions],
    }


def _handle_get_coding_history(args, ctx):
    if not _archive_available():
        return {'error': 'The coding problem archive is not initialized'}
    args = args or {}
    limit = min(max(int(args.get('limit') or 20), 1), 50)
    clauses = []
    params = []
    if args.get('problemId') is not None:
        try:
            params.append(int(args['problemId']))
        except (TypeError, ValueError):
            return {'error': 'problemId must be an integer'}
        clauses.append('s.problem_id = ?')
    if args.get('verdict'):
        clauses.append('lower(s.status) = lower(?)')
        params.append(str(args['verdict']))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db.q(
        f"""SELECT s.id, s.problem_id, p.title, s.language, s.status, s.verified,
                   s.runtime_ms, s.error, s.phase, s.created_at
            FROM submissions s JOIN problems p ON p.id = s.problem_id
            {where} ORDER BY s.id DESC LIMIT ?""",
        *params, limit,
    )
    return {
        'count': len(rows),
        'attempts': [{
            'id': row['id'], 'problemId': row['problem_id'], 'title': row['title'],
            'language': row['language'], 'status': row['status'],
            'verified': bool(row['verified']), 'runtimeMs': row['runtime_ms'],
            'error': _short_text(row.get('error'), 500), 'phase': row['phase'],
            'createdAt': row['created_at'],
        } for row in rows],
    }


def _handle_list_study_sets(args, ctx):
    store, active_id = _study_context()
    uploads = store.list_uploads()
    study_sets = []
    for upload in uploads:
        for workspace in upload['studySets']:
            story = db.q1('SELECT key FROM issues WHERE id = ?', workspace.get('story_id')) \
                if workspace.get('story_id') else None
            study_sets.append({
                'id': workspace['id'], 'name': workspace['name'],
                'library': upload['name'], 'originalFilename': upload['originalFilename'],
                'active': workspace['id'] == active_id, 'storyId': workspace.get('story_id'),
                'storyKey': story['key'] if story else None,
                'progress': workspace['progress'],
            })
    return {'count': len(study_sets), 'studySets': study_sets}


def _handle_get_study_material(args, ctx):
    args = args or {}
    store, workspace, error = _resolve_study_workspace(args)
    if error:
        return {'error': error['message'], 'matches': error['matches']} if isinstance(error, dict) else {'error': error}
    kind = str(args.get('kind') or '').strip().lower()
    manifest = store.manifest(workspace['id'])
    if not kind:
        return {'workspace': {'id': workspace['id'], 'name': workspace['name']}, 'kinds': manifest['kinds']}
    if kind not in manifest['kinds']:
        return {'error': f'Unknown study material kind "{kind}"', 'allowedKinds': sorted(manifest['kinds'])}
    filename = str(args.get('file') or '').strip()
    if not filename:
        return {
            'workspace': {'id': workspace['id'], 'name': workspace['name']},
            'kind': kind, 'documents': manifest['kinds'][kind],
        }
    try:
        body, content_type = store.read_content(workspace['id'], kind, filename)
    except FileNotFoundError:
        return {'error': f'{kind} document "{filename}" not found in {workspace["name"]}'}
    try:
        text = body.decode('utf-8-sig')
    except UnicodeDecodeError:
        return {'error': 'Binary study assets cannot be returned through this text tool'}
    truncated = len(text) > 16000
    text = text[:16000]
    try:
        content = json.loads(text) if not truncated else text
    except json.JSONDecodeError:
        content = text
    return {
        'workspace': {'id': workspace['id'], 'name': workspace['name']},
        'kind': kind, 'file': filename, 'contentType': content_type,
        'truncated': truncated, 'content': content,
    }


def _handle_get_study_history(args, ctx):
    args = args or {}
    store, workspace, error = _resolve_study_workspace(args)
    if error:
        return {'error': error['message'], 'matches': error['matches']} if isinstance(error, dict) else {'error': error}
    activity = str(args.get('activity') or 'all').lower()
    if activity not in ('all', 'quiz', 'qanda', 'flashcards'):
        return {'error': 'activity must be all, quiz, qanda, or flashcards'}
    limit = min(max(int(args.get('limit') or 5), 1), 20)
    result = {
        'workspace': {'id': workspace['id'], 'name': workspace['name']},
        'progress': store.get_study_progress(workspace['id']),
    }
    if activity in ('all', 'quiz'):
        attempts = store.list_quiz_attempts(workspace['id'])[:limit]
        result['quizAttempts'] = [{
            'id': item['id'], 'title': item['title'], 'file': item['quizFile'],
            'score': item['score'], 'total': item['total'], 'completedAt': item['completedAt'],
            'responses': [{
                'question': _short_text(response.get('question'), 500),
                'selectedAnswer': _short_text(response.get('selectedAnswer'), 500),
                'correctAnswer': _short_text(response.get('correctAnswer'), 500),
                'correct': bool(response.get('correct')),
                'explanation': _short_text(response.get('explanation'), 1000),
            } for response in item.get('responses', [])[:25] if isinstance(response, dict)],
        } for item in attempts]
    if activity in ('all', 'qanda'):
        sessions = store.list_qa_sessions(workspace['id'])[:limit]
        result['qandaSessions'] = [{
            'id': item['id'], 'title': item['title'], 'file': item['qaFile'],
            'status': item['status'], 'updatedAt': item['updatedAt'],
            'completedAt': item['completedAt'],
            'responses': [{
                'question': _short_text(response.get('question'), 750),
                'answer': _short_text(response.get('answer'), 2000),
            } for response in item.get('responses', [])[:25] if isinstance(response, dict)
              and str(response.get('answer') or '').strip()],
        } for item in sessions]
    if activity in ('all', 'flashcards'):
        cards = store.list_flashcard_progress(workspace['id'])[:limit]
        result['flashcards'] = []
        for item in cards:
            pair = _json_value(item.get('cardKey'), [])
            result['flashcards'].append({
                'file': item['flashcardFile'],
                'front': _short_text(pair[0], 1000) if len(pair) > 0 else item['cardKey'],
                'back': _short_text(pair[1], 2000) if len(pair) > 1 else None,
                'remembered': item['remembered'], 'updatedAt': item['updatedAt'],
            })
    return result


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
        'name': 'search_coding_problems',
        'description': 'Search the coding problem archive and show solved state, attempt count, last verdict, and linked story.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Title, statement, or tag keywords'},
                'difficulty': {'type': 'string', 'description': 'Easy, Medium, or Hard'},
                'language': {'type': 'string'},
                'solved': {'type': 'string', 'enum': ['all', 'solved', 'unsolved']},
                'limit': {'type': 'number', 'description': 'Max results (default 10, max 25)'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_search_coding_problems,
        'connectorPrefix': 'archive',
        'connectorLabel': 'Coding Archive',
    },
    {
        'name': 'get_coding_problem',
        'description': 'Get a coding problem statement, examples, hints, tags, solved state, linked story, and five recent attempts.',
        'parameters': {
            'type': 'object',
            'properties': {'problemId': {'type': 'number', 'description': 'Coding problem id'}},
            'required': ['problemId'],
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_get_coding_problem,
        'connectorPrefix': 'archive',
        'connectorLabel': 'Coding Archive',
    },
    {
        'name': 'get_coding_history',
        'description': 'Recall recent coding submissions and verdicts, optionally for one problem or verdict.',
        'parameters': {
            'type': 'object',
            'properties': {
                'problemId': {'type': 'number'},
                'verdict': {'type': 'string', 'description': 'For example Accepted or Wrong Answer'},
                'limit': {'type': 'number', 'description': 'Max attempts (default 20, max 50)'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_get_coding_history,
        'connectorPrefix': 'archive',
        'connectorLabel': 'Coding Archive',
    },
    {
        'name': 'list_study_sets',
        'description': 'List imported study sets with their library, linked story, active state, and quiz/Q&A/flashcard progress.',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'mutates': False,
        'handler': _handle_list_study_sets,
        'connectorPrefix': 'study',
        'connectorLabel': 'Study Sets',
    },
    {
        'name': 'get_study_material',
        'description': 'List or read quiz, Q&A, flashcard, report, slide, table, infographic, mind-map, or podcast study material.',
        'parameters': {
            'type': 'object',
            'properties': {
                'workspace': {'type': 'string', 'description': 'Study-set id or name; defaults to the active study set'},
                'kind': {'type': 'string', 'description': 'Material kind; omit to list all documents'},
                'file': {'type': 'string', 'description': 'Document filename; omit to list documents in the kind'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_get_study_material,
        'connectorPrefix': 'study',
        'connectorLabel': 'Study Sets',
    },
    {
        'name': 'get_study_history',
        'description': 'Recall persisted quiz answers and correctness, Q&A answers, flashcard memory state, and aggregate progress for a study set.',
        'parameters': {
            'type': 'object',
            'properties': {
                'workspace': {'type': 'string', 'description': 'Study-set id or name; defaults to the active study set'},
                'activity': {'type': 'string', 'enum': ['all', 'quiz', 'qanda', 'flashcards']},
                'limit': {'type': 'number', 'description': 'Max records per activity (default 5, max 20)'},
            },
            'additionalProperties': False,
        },
        'mutates': False,
        'handler': _handle_get_study_history,
        'connectorPrefix': 'study',
        'connectorLabel': 'Study Sets',
    },
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
