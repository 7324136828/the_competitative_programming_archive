import json
from ..db import db, SQL_NOW
from ..util import new_id, now_iso
from .users import get_default_user_id, is_user_eligible_for_assignment
from .workflows import is_transition_allowed
from .automation import run_automation_trigger
from .notifications import notify_watchers
from .history import record_status_change, record_sprint_event


def _json_value(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value if isinstance(value, list) else default


def ensure_archive_problem(input: dict) -> dict:
    """Return an existing archive problem or create one from story-shaped data."""
    requested_id = input.get('problemId') or input.get('problem_id') or input.get('id')
    if requested_id is not None:
        try:
            existing = db.q1('SELECT * FROM problems WHERE id = ?', int(requested_id))
        except (TypeError, ValueError):
            existing = None
        if existing:
            return existing

    title = str(input.get('title') or input.get('summary') or 'Untitled Problem').strip()
    description = str(input.get('problem_statements') or input.get('description') or '')
    exact = db.q1(
        """SELECT p.* FROM problems p
           LEFT JOIN issues i ON i.problem_id = p.id
           WHERE p.title = ? AND p.problem_statements = ? AND i.id IS NULL
           ORDER BY p.id LIMIT 1""",
        title, description,
    )
    if exact:
        return exact
    cursor = db.run(
        """INSERT INTO problems (title, problem_statements, sample_input_output, hints,
                                 language, difficulty, tags, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        title,
        description,
        json.dumps(_json_value(input.get('sample_input_output') or input.get('sampleIo') or input.get('samples'), [])),
        json.dumps(_json_value(input.get('hints'), [])),
        input.get('language') or 'en',
        input.get('difficulty') or 'Medium',
        json.dumps(_json_value(input.get('tags'), [])),
        input.get('source') or 'story',
    )
    return db.q1('SELECT * FROM problems WHERE id = ?', cursor.lastrowid)


def get_issue_by_problem_id(problem_id: int | str):
    try:
        row = db.q1('SELECT id FROM issues WHERE problem_id = ?', int(problem_id))
    except (TypeError, ValueError):
        return None
    return get_issue_by_id(row['id']) if row else None


def generate_issue_key(project_id: str) -> str:
    project = db.q1('SELECT key FROM projects WHERE id = ?', project_id)
    if not project:
        raise ValueError(f'Project {project_id} not found')
    prefix = f"{project['key']}-"
    max_num = 0
    for row in db.q('SELECT key FROM issues WHERE project_id = ?', project_id):
        if row['key'].startswith(prefix):
            try:
                num = int(row['key'][len(prefix):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"{project['key']}-{max_num + 1}"


def create_issue(input: dict, creator_id: str | None = None, source: str = 'user'):
    if not input.get('summary') or not str(input['summary']).strip():
        raise ValueError('Validation error: Issue summary is required.')
    creator_id = creator_id or get_default_user_id()

    assignee_id = input.get('assigneeId')
    if assignee_id and not is_user_eligible_for_assignment(assignee_id):
        raise ValueError(f'Assignee {assignee_id} is not eligible for assignment.')

    issue_id = new_id('issue')
    now = now_iso()
    project_id = input['projectId']

    issue_type = input.get('type') or 'Story'
    story_type = input.get('storyType') or input.get('story_type')
    if issue_type == 'Story' and not story_type:
        story_type = 'coding'

    difficulty = input.get('difficulty') or 'Medium'
    problem_id = input.get('problemId') or input.get('problem_id')

    sample_io = input.get('sample_io_json') or input.get('sample_input_output') or input.get('sampleIo') or []
    if not isinstance(sample_io, str):
        sample_io = json.dumps(sample_io)

    hints = input.get('hints_json') or input.get('hints') or []
    if not isinstance(hints, str):
        hints = json.dumps(hints)

    tags = input.get('tags_json') or input.get('tags') or []
    if not isinstance(tags, str):
        tags = json.dumps(tags)

    submission_status = input.get('submissionStatus') or input.get('submission_status') or 'Unsolved'

    def _work():
        resolved_problem_id = problem_id
        if issue_type == 'Story' and story_type == 'coding':
            problem = ensure_archive_problem({**input, 'title': input.get('summary')})
            resolved_problem_id = problem['id']
            linked = db.q1('SELECT id, key FROM issues WHERE problem_id = ?', resolved_problem_id)
            if linked:
                raise ValueError(
                    f"Archive problem {resolved_problem_id} is already linked to story {linked['key']}."
                )
        key = generate_issue_key(project_id)
        max_rank = db.q1('SELECT MAX(rank) as max_rank FROM issues WHERE project_id = ?', project_id)
        rank = (max_rank['max_rank'] or 0) + 1.0

        db.run(
            """INSERT INTO issues (
                 id, key, project_id, type, story_type, summary, description, status, priority,
                 difficulty, assignee_id, reporter_id, parent_id, sprint_id, version_id,
                 rank, story_points, start_date, due_date, problem_id, sample_io_json,
                 hints_json, tags_json, submission_status, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            issue_id, key, project_id,
            issue_type,
            story_type,
            str(input['summary']).strip(),
            input.get('description') or '',
            'To Do',
            input.get('priority') or 'Medium',
            difficulty,
            assignee_id or None,
            input.get('reporterId') or creator_id,
            input.get('parentId') or None,
            input.get('sprintId') or None,
            input.get('versionId') or None,
            rank,
            input.get('storyPoints'),
            input.get('startDate') or None,
            input.get('dueDate') or None,
            resolved_problem_id,
            sample_io,
            hints,
            tags,
            submission_status,
            now, now,
        )

        record_status_change(issue_id, project_id, None, 'To Do',
                             changed_by=creator_id, source=source, at=now)

        if input.get('sprintId'):
            record_sprint_event(input['sprintId'], issue_id, 'added',
                                story_points=input.get('storyPoints'), status='To Do', at=now)

        try:
            db.run('INSERT OR IGNORE INTO watchers (issue_id, user_id) VALUES (?, ?)',
                   issue_id, input.get('reporterId') or creator_id)
        except Exception:
            pass

        run_automation_trigger('ISSUE_CREATED', issue_id, project_id, creator_id)
        return get_issue_by_id(issue_id)

    return db.with_transaction(_work)


def ensure_story_for_problem(problem_id: int | str, project_id: str | None = None,
                             parent_id: str | None = None, creator_id: str | None = None):
    existing = get_issue_by_problem_id(problem_id)
    if existing:
        return existing
    problem = db.q1('SELECT * FROM problems WHERE id = ?', int(problem_id))
    if not problem:
        raise ValueError(f'Archive problem {problem_id} not found')
    project = db.q1('SELECT id FROM projects WHERE id = ?', project_id) if project_id else None
    if not project:
        project = db.q1('SELECT id FROM projects ORDER BY created_at, rowid LIMIT 1')
    if not project:
        raise ValueError('A project is required before creating a linked story')
    return create_issue({
        'projectId': project['id'],
        'type': 'Story',
        'storyType': 'coding',
        'summary': problem['title'],
        'description': problem['problem_statements'],
        'difficulty': problem['difficulty'],
        'parentId': parent_id,
        'problemId': problem['id'],
        'sampleIo': _json_value(problem['sample_input_output'], []),
        'hints': _json_value(problem['hints'], []),
        'tags': _json_value(problem['tags'], []),
        'submissionStatus': 'Unsolved',
    }, creator_id, source='system')


def backfill_coding_story_problem_links() -> int:
    """Create an archive problem for every legacy coding Story without one."""
    missing = db.q(
        """SELECT * FROM issues
           WHERE type = 'Story' AND COALESCE(story_type, 'coding') = 'coding'
             AND problem_id IS NULL
           ORDER BY created_at, rowid"""
    )
    if not missing:
        return 0

    def _work():
        for story in missing:
            problem = ensure_archive_problem({
                'summary': story['summary'],
                'description': story['description'] or '',
                'difficulty': story['difficulty'] or 'Medium',
                'sample_input_output': story['sample_io_json'] or '[]',
                'hints': story['hints_json'] or '[]',
                'tags': story['tags_json'] or '[]',
                'source': 'story-backfill',
            })
            db.run(
                'UPDATE issues SET problem_id = ?, updated_at = ? WHERE id = ?',
                problem['id'], now_iso(), story['id'],
            )

    db.with_transaction(_work)
    return len(missing)


def backfill_archive_story_links(project_id: str | None = None, creator_id: str | None = None) -> int:
    """Create a coding story for every unlinked archive problem."""
    missing = db.q(
        """SELECT p.*,
             EXISTS(SELECT 1 FROM submissions s WHERE s.problem_id = p.id
                    AND s.status = 'Accepted' AND s.verified = 1) AS is_solved
           FROM problems p
           LEFT JOIN issues i ON i.problem_id = p.id
           WHERE i.id IS NULL ORDER BY p.id"""
    )
    if not missing:
        return 0
    project = db.q1('SELECT id, key FROM projects WHERE id = ?', project_id) if project_id else None
    if not project:
        project = db.q1('SELECT id, key FROM projects ORDER BY created_at, rowid LIMIT 1')
    if not project:
        raise ValueError('A project is required before creating linked stories')
    creator_id = creator_id or get_default_user_id()
    next_key = int(generate_issue_key(project['id']).rsplit('-', 1)[1])
    max_rank = db.q1('SELECT MAX(rank) AS value FROM issues WHERE project_id = ?', project['id'])
    rank = float(max_rank['value'] or 0)
    now = now_iso()

    def _work():
        nonlocal next_key, rank
        for problem in missing:
            issue_id = new_id('issue')
            key = f"{project['key']}-{next_key}"
            next_key += 1
            rank += 1.0
            solved = bool(problem['is_solved'])
            difficulty = problem['difficulty'] or 'Medium'
            points = 3 if difficulty == 'Easy' else 8 if difficulty == 'Hard' else 5
            db.run(
                """INSERT INTO issues (
                     id, key, project_id, type, story_type, summary, description, status,
                     priority, difficulty, reporter_id, rank, story_points, problem_id,
                     sample_io_json, hints_json, tags_json, submission_status, created_at, updated_at
                   ) VALUES (?, ?, ?, 'Story', 'coding', ?, ?, ?, 'Medium', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                issue_id, key, project['id'], problem['title'], problem['problem_statements'],
                'Done' if solved else 'To Do', difficulty, creator_id, rank, points,
                problem['id'], problem['sample_input_output'] or '[]', problem['hints'] or '[]',
                problem['tags'] or '[]', 'Accepted' if solved else 'Unsolved', now, now,
            )
            record_status_change(issue_id, project['id'], None, 'Done' if solved else 'To Do',
                                 changed_by=creator_id, source='system', at=now)
            db.run('INSERT OR IGNORE INTO watchers (issue_id, user_id) VALUES (?, ?)',
                   issue_id, creator_id)

    db.with_transaction(_work)
    return len(missing)



def get_issue_by_id(issue_id: str):
    issue = db.q1(
        """SELECT i.*,
             p.name as project_name, p.key as project_key,
             u_assignee.name as assignee_name, u_assignee.avatar as assignee_avatar,
             u_reporter.name as reporter_name, u_reporter.avatar as reporter_avatar,
             s.name as sprint_name,
             v.name as version_name,
             parent.key as parent_key, parent.summary as parent_summary
           FROM issues i
           JOIN projects p ON i.project_id = p.id
           LEFT JOIN users u_assignee ON i.assignee_id = u_assignee.id
           LEFT JOIN users u_reporter ON i.reporter_id = u_reporter.id
           LEFT JOIN sprints s ON i.sprint_id = s.id
           LEFT JOIN versions v ON i.version_id = v.id
           LEFT JOIN issues parent ON i.parent_id = parent.id
           WHERE i.id = ? OR i.key = ?""",
        issue_id, issue_id,
    )
    if not issue:
        return None

    issue['subtasks'] = db.q(
        """SELECT s.*, u.name as assignee_name, u.avatar as assignee_avatar
           FROM issues s LEFT JOIN users u ON s.assignee_id = u.id
           WHERE s.parent_id = ? ORDER BY s.created_at ASC""",
        issue['id'],
    )

    outward = db.q(
        """SELECT l.id as link_id, l.link_type, i.id, i.key, i.summary, i.status, i.type, i.priority, 'outward' as direction
           FROM issue_links l JOIN issues i ON l.target_id = i.id WHERE l.source_id = ?""",
        issue['id'],
    )
    inward = db.q(
        """SELECT l.id as link_id, l.link_type, i.id, i.key, i.summary, i.status, i.type, i.priority, 'inward' as direction
           FROM issue_links l JOIN issues i ON l.source_id = i.id WHERE l.target_id = ?""",
        issue['id'],
    )

    def rel(l, direction):
        lt = l['link_type']
        if direction == 'outward':
            return {'blocks': 'blocks', 'duplicates': 'duplicates'}.get(lt, 'relates to')
        return {'blocks': 'is blocked by', 'duplicates': 'is duplicated by'}.get(lt, 'relates to')

    issue['links'] = (
        [{**l, 'displayRelation': rel(l, 'outward')} for l in outward]
        + [{**l, 'displayRelation': rel(l, 'inward')} for l in inward]
    )

    issue['customFieldValues'] = db.q(
        """SELECT cf.id, cf.name, cf.field_type, cf.options_json, cfv.value
           FROM custom_fields cf
           LEFT JOIN custom_field_values cfv ON cf.id = cfv.field_id AND cfv.issue_id = ?
           WHERE cf.project_id = ?""",
        issue['id'], issue['project_id'],
    )

    issue['watchers'] = db.q(
        """SELECT u.id, u.name, u.email, u.avatar
           FROM watchers w JOIN users u ON w.user_id = u.id WHERE w.issue_id = ?""",
        issue['id'],
    )

    total = db.q1('SELECT SUM(time_spent_minutes) as total FROM worklogs WHERE issue_id = ?', issue['id'])
    issue['totalTimeSpentMinutes'] = (total and total['total']) or 0

    if issue.get('sample_io_json'):
        try:
            issue['sample_input_output'] = json.loads(issue['sample_io_json'])
        except Exception:
            issue['sample_input_output'] = []
    if issue.get('hints_json'):
        try:
            issue['hints'] = json.loads(issue['hints_json'])
        except Exception:
            issue['hints'] = []
    if issue.get('tags_json'):
        try:
            issue['tags'] = json.loads(issue['tags_json'])
        except Exception:
            issue['tags'] = []

    issue['archived_problem'] = None
    has_problem_table = db.q1(
        "SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'problems'"
    )
    if issue.get('problem_id') is not None and has_problem_table:
        problem = db.q1(
            """SELECT id, title, problem_statements, language, difficulty, source
               FROM problems WHERE id = ?""",
            issue['problem_id'],
        )
        if problem:
            audio = db.q1(
                'SELECT url, status, updated_at FROM problem_audio_assets WHERE problem_id = ?',
                issue['problem_id'],
            )
            issue['archived_problem'] = {
                **problem,
                'audio': audio,
                'archive_url': f"#problems/{problem['id']}",
            }

    return issue


def assign_issue(issue_id: str, assignee_id):
    if assignee_id is not None and not is_user_eligible_for_assignment(assignee_id):
        raise ValueError(f'User {assignee_id} is not eligible for assignment.')
    issue = db.q1('SELECT * FROM issues WHERE id = ?', issue_id)
    if not issue:
        raise ValueError(f'Issue {issue_id} not found')
    db.run(f'UPDATE issues SET assignee_id = ?, updated_at = {SQL_NOW} WHERE id = ?', assignee_id, issue_id)
    name = db.q1('SELECT name FROM users WHERE id = ?', assignee_id)['name'] if assignee_id else 'Unassigned'
    notify_watchers(issue_id, 'Issue Assigned', f"Issue {issue['key']} was assigned to {name}.")
    return get_issue_by_id(issue_id)


def create_subtask(parent_id: str, summary: str, assignee_id=None, story_points=None, creator_id=None):
    parent = db.q1('SELECT * FROM issues WHERE id = ?', parent_id)
    if not parent:
        raise ValueError(f'Parent issue {parent_id} not found')
    return create_issue({
        'projectId': parent['project_id'],
        'type': 'Subtask',
        'summary': summary,
        'parentId': parent['id'],
        'sprintId': parent['sprint_id'],
        'assigneeId': assignee_id,
        'storyPoints': story_points,
    }, creator_id or get_default_user_id())


def link_issues(source_id: str, target_id: str, link_type: str):
    if source_id == target_id:
        raise ValueError('An issue cannot link to itself.')
    source = db.q1('SELECT id, key FROM issues WHERE id = ?', source_id)
    target = db.q1('SELECT id, key FROM issues WHERE id = ?', target_id)
    if not source or not target:
        raise ValueError('Source or Target issue not found.')
    existing = db.q1(
        """SELECT id FROM issue_links
           WHERE (source_id = ? AND target_id = ?) OR (source_id = ? AND target_id = ?)""",
        source_id, target_id, target_id, source_id,
    )
    if existing:
        raise ValueError('These issues are already linked.')
    link_id = new_id('link')
    db.run('INSERT INTO issue_links (id, source_id, target_id, link_type) VALUES (?, ?, ?, ?)',
           link_id, source_id, target_id, link_type)
    return {'id': link_id, 'sourceId': source_id, 'targetId': target_id, 'linkType': link_type}


def delete_link(link_id: str):
    db.run('DELETE FROM issue_links WHERE id = ?', link_id)


def reorder_issue(issue_id: str, target_rank: float):
    db.run(f'UPDATE issues SET rank = ?, updated_at = {SQL_NOW} WHERE id = ?', target_rank, issue_id)
    return get_issue_by_id(issue_id)


def update_story_points(issue_id: str, points):
    if points is not None:
        try:
            points = float(points)
        except (TypeError, ValueError):
            raise ValueError('Story points must be a non-negative number.')
        if points < 0:
            raise ValueError('Story points must be a non-negative number.')
    db.run(f'UPDATE issues SET story_points = ?, updated_at = {SQL_NOW} WHERE id = ?', points, issue_id)
    return get_issue_by_id(issue_id)


def set_issue_sprint(issue_id: str, sprint_id):
    issue = db.q1('SELECT * FROM issues WHERE id = ?', issue_id)
    if not issue:
        raise ValueError(f'Issue {issue_id} not found')
    now = now_iso()

    def _work():
        if (issue['sprint_id'] or None) != (sprint_id or None):
            if issue['sprint_id']:
                record_sprint_event(issue['sprint_id'], issue_id, 'removed',
                                    story_points=issue['story_points'], status=issue['status'], at=now)
            if sprint_id:
                record_sprint_event(sprint_id, issue_id, 'added',
                                    story_points=issue['story_points'], status=issue['status'], at=now)
        db.run(f'UPDATE issues SET sprint_id = ?, updated_at = {SQL_NOW} WHERE id = ?', sprint_id, issue_id)

    db.with_transaction(_work)
    return get_issue_by_id(issue_id)


def update_issue_status(issue_id: str, new_status: str, user_id=None, source: str = 'user'):
    issue = db.q1('SELECT * FROM issues WHERE id = ?', issue_id)
    if not issue:
        raise ValueError(f'Issue {issue_id} not found')

    # Requirement: Change of status for story related to coding will depend on completely by submission status and also the testing results.
    if issue.get('type') == 'Story' and issue.get('story_type') == 'coding' and source not in ('submission', 'system', 'automation'):
        cat_row = db.q1(
            """SELECT ws.category FROM workflow_statuses ws
               JOIN workflows w ON ws.workflow_id = w.id
               WHERE w.project_id = ? AND ws.name = ?""",
            issue['project_id'], new_status
        )
        cat = (cat_row['category'] if cat_row else '').upper()
        if cat == 'DONE' or new_status == 'Done':
            sub_status = (issue.get('submission_status') or '').strip().lower()
            if sub_status != 'accepted':
                raise ValueError(
                    'Change of status for coding stories depends entirely on submission status and testing results. '
                    'Please submit an Accepted solution in the Activity Screen to move this story to Done.'
                )

    if not is_transition_allowed(issue['project_id'], issue['status'], new_status):
        raise ValueError(f'Transition from "{issue["status"]}" to "{new_status}" is not permitted by workflow.')


    old_status = issue['status']

    def _work():
        if old_status != new_status:
            record_status_change(issue_id, issue['project_id'], old_status, new_status,
                                 changed_by=user_id, source=source)
        db.run(f'UPDATE issues SET status = ?, updated_at = {SQL_NOW} WHERE id = ?', new_status, issue_id)

    db.with_transaction(_work)
    notify_watchers(issue_id, f'Status Changed: {new_status}',
                    f'Issue {issue["key"]} was moved from "{old_status}" to "{new_status}".', user_id)
    run_automation_trigger('STATUS_CHANGED', issue_id, issue['project_id'], user_id)
    return get_issue_by_id(issue_id)


def update_coding_story_submission(issue_id_or_problem_id, verdict: str, test_results=None, user_id=None):
    clean_verdict = (verdict or '').strip()
    issue = db.q1(
        'SELECT * FROM issues WHERE id = ? OR problem_id = ? OR key = ?',
        str(issue_id_or_problem_id), issue_id_or_problem_id, str(issue_id_or_problem_id)
    )
    if not issue:
        return None
    issue_id = issue['id']
    db.run(f'UPDATE issues SET submission_status = ?, updated_at = {SQL_NOW} WHERE id = ?', clean_verdict, issue_id)

    if clean_verdict.lower() == 'accepted':
        # Find project's Done status
        done_status = 'Done'
        ws = db.q1(
            """SELECT ws.name FROM workflow_statuses ws
               JOIN workflows w ON ws.workflow_id = w.id
               WHERE w.project_id = ? AND ws.category = 'DONE'
               ORDER BY ws.position DESC LIMIT 1""",
            issue['project_id']
        )
        if ws:
            done_status = ws['name']
        if issue['status'] != done_status:
            try:
                update_issue_status(issue_id, done_status, user_id=user_id, source='submission')
            except Exception:
                old_status = issue['status']
                record_status_change(issue_id, issue['project_id'], old_status, done_status, changed_by=user_id, source='submission')
                db.run(f'UPDATE issues SET status = ?, updated_at = {SQL_NOW} WHERE id = ?', done_status, issue_id)
    else:
        if issue['status'] == 'To Do':
            in_prog = 'In Progress'
            ws = db.q1(
                """SELECT ws.name FROM workflow_statuses ws
                   JOIN workflows w ON ws.workflow_id = w.id
                   WHERE w.project_id = ? AND ws.category = 'IN_PROGRESS'
                   ORDER BY ws.position ASC LIMIT 1""",
                issue['project_id']
            )
            if ws:
                in_prog = ws['name']
            try:
                update_issue_status(issue_id, in_prog, user_id=user_id, source='submission')
            except Exception:
                old_status = issue['status']
                record_status_change(issue_id, issue['project_id'], old_status, in_prog, changed_by=user_id, source='submission')
                db.run(f'UPDATE issues SET status = ?, updated_at = {SQL_NOW} WHERE id = ?', in_prog, issue_id)

    return get_issue_by_id(issue_id)



def add_comment(issue_id: str, author_id: str, body: str):
    if not body or not str(body).strip():
        raise ValueError('Comment body cannot be empty.')
    cid = new_id('c')
    db.run('INSERT INTO comments (id, issue_id, author_id, body) VALUES (?, ?, ?, ?)',
           cid, issue_id, author_id, str(body).strip())
    notify_watchers(issue_id, 'New Comment', 'New comment posted on issue.', author_id)
    return db.q1(
        """SELECT c.*, u.name as author_name, u.avatar as author_avatar
           FROM comments c JOIN users u ON c.author_id = u.id WHERE c.id = ?""",
        cid,
    )


def get_comments(issue_id: str):
    return db.q(
        """SELECT c.*, u.name as author_name, u.avatar as author_avatar
           FROM comments c JOIN users u ON c.author_id = u.id
           WHERE c.issue_id = ? ORDER BY c.created_at ASC""",
        issue_id,
    )


def delete_comment(comment_id: str):
    db.run('DELETE FROM comments WHERE id = ?', comment_id)


def toggle_watch(issue_id: str, user_id: str) -> bool:
    existing = db.q1('SELECT 1 FROM watchers WHERE issue_id = ? AND user_id = ?', issue_id, user_id)
    if existing:
        db.run('DELETE FROM watchers WHERE issue_id = ? AND user_id = ?', issue_id, user_id)
        return False
    db.run('INSERT INTO watchers (issue_id, user_id) VALUES (?, ?)', issue_id, user_id)
    return True


def log_work(issue_id: str, author_id: str, time_spent_minutes, description=None, started_at=None):
    if not time_spent_minutes or time_spent_minutes <= 0:
        raise ValueError('Time spent must be greater than zero.')
    wid = new_id('wl')
    from datetime import datetime, timezone
    date_str = started_at or datetime.now(timezone.utc).date().isoformat()
    db.run(
        """INSERT INTO worklogs (id, issue_id, author_id, time_spent_minutes, description, started_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        wid, issue_id, author_id, time_spent_minutes, description or '', date_str,
    )
    return db.q1(
        """SELECT w.*, u.name as author_name, u.avatar as author_avatar
           FROM worklogs w JOIN users u ON w.author_id = u.id WHERE w.id = ?""",
        wid,
    )


def get_worklogs(issue_id: str):
    return db.q(
        """SELECT w.*, u.name as author_name, u.avatar as author_avatar
           FROM worklogs w JOIN users u ON w.author_id = u.id
           WHERE w.issue_id = ? ORDER BY w.started_at DESC, w.created_at DESC""",
        issue_id,
    )


def search_issues(filter: dict):
    sql = """
        SELECT i.*,
               p.name as project_name, p.key as project_key,
               u.name as assignee_name, u.avatar as assignee_avatar,
               s.name as sprint_name,
               v.name as version_name
        FROM issues i
        JOIN projects p ON i.project_id = p.id
        LEFT JOIN users u ON i.assignee_id = u.id
        LEFT JOIN sprints s ON i.sprint_id = s.id
        LEFT JOIN versions v ON i.version_id = v.id
        WHERE 1=1
    """
    params: list = []
    if filter.get('projectId'):
        sql += ' AND i.project_id = ?'
        params.append(filter['projectId'])
    if filter.get('query'):
        sql += ' AND (i.summary LIKE ? OR i.description LIKE ? OR i.key LIKE ?)'
        term = f"%{filter['query']}%"
        params += [term, term, term]
    if filter.get('unassigned'):
        sql += ' AND i.assignee_id IS NULL'
    elif filter.get('assigneeId'):
        sql += ' AND i.assignee_id = ?'
        params.append(filter['assigneeId'])
    if filter.get('status'):
        sql += ' AND i.status = ?'
        params.append(filter['status'])
    if filter.get('statusNot'):
        sql += ' AND i.status != ?'
        params.append(filter['statusNot'])
    if filter.get('priority'):
        sql += ' AND i.priority = ?'
        params.append(filter['priority'])
    if filter.get('type'):
        sql += ' AND i.type = ?'
        params.append(filter['type'])
    if 'sprintId' in filter:
        if filter['sprintId'] is None:
            sql += ' AND i.sprint_id IS NULL'
        else:
            sql += ' AND i.sprint_id = ?'
            params.append(filter['sprintId'])
    if filter.get('versionId'):
        sql += ' AND i.version_id = ?'
        params.append(filter['versionId'])
    sql += ' ORDER BY i.rank ASC, i.created_at DESC'
    return db.q(sql, *params)


def update_issue_dates(issue_id: str, start_date, due_date):
    db.run(f'UPDATE issues SET start_date = ?, due_date = ?, updated_at = {SQL_NOW} WHERE id = ?',
           start_date, due_date, issue_id)
    return get_issue_by_id(issue_id)


def set_issue_version(issue_id: str, version_id):
    db.run(f'UPDATE issues SET version_id = ?, updated_at = {SQL_NOW} WHERE id = ?', version_id, issue_id)
    return get_issue_by_id(issue_id)


def set_custom_field_value(issue_id: str, field_id: str, value):
    db.run(
        """INSERT INTO custom_field_values (issue_id, field_id, value) VALUES (?, ?, ?)
           ON CONFLICT(issue_id, field_id) DO UPDATE SET value = excluded.value""",
        issue_id, field_id, value,
    )


def delete_issue_recursive(issue_id: str):
    def _work():
        children = db.q('SELECT id FROM issues WHERE parent_id = ?', issue_id)
        for child in children:
            delete_issue_recursive(child['id'])
        db.run('DELETE FROM issues WHERE id = ?', issue_id)
    db.with_transaction(_work)


def get_cross_project_dependencies():
    return db.q(
        """SELECT l.id as link_id, l.link_type,
             src.id as source_id, src.key as source_key, src.summary as source_summary, src.status as source_status,
             src_p.id as source_project_id, src_p.key as source_project_key, src_p.name as source_project_name,
             tgt.id as target_id, tgt.key as target_key, tgt.summary as target_summary, tgt.status as target_status,
             tgt_p.id as target_project_id, tgt_p.key as target_project_key, tgt_p.name as target_project_name
           FROM issue_links l
           JOIN issues src ON l.source_id = src.id
           JOIN projects src_p ON src.project_id = src_p.id
           JOIN issues tgt ON l.target_id = tgt.id
           JOIN projects tgt_p ON tgt.project_id = tgt_p.id
           WHERE src.project_id != tgt.project_id OR l.link_type = 'blocks'
           ORDER BY l.created_at DESC"""
    )
