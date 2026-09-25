from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..seed import ensure_bootstrap_data


router = APIRouter()


# Child tables must be emptied before their parents because foreign-key
# enforcement stays enabled throughout the purge.
PURGE_TABLES = (
    'editor_drafts',
    'problem_translations',
    'problem_solution_traces',
    'problem_audio_assets',
    'submissions',
    'problems',
    'chat_messages',
    'ai_ticket_links',
    'automation_logs',
    'custom_field_values',
    'watchers',
    'worklogs',
    'attachments',
    'comments',
    'issue_links',
    'sprint_issue_events',
    'issue_status_history',
    'pull_requests',
    'notifications',
    'saved_filters',
    'sprint_snapshots',
    'issues',
    'workflow_transitions',
    'workflow_statuses',
    'automation_rules',
    'custom_fields',
    'sprints',
    'versions',
    'workflows',
    'ai_requests',
    'activity_log',
    'projects',
    'app_settings',
    'users',
)


def _purge_jira_data(admin: dict) -> dict:
    counts = {
        'projects': db.q1('SELECT COUNT(*) AS c FROM projects')['c'],
        'issues': db.q1('SELECT COUNT(*) AS c FROM issues')['c'],
        'users': db.q1('SELECT COUNT(*) AS c FROM users')['c'],
        'problems': db.q1('SELECT COUNT(*) AS c FROM problems')['c'],
        'submissions': db.q1('SELECT COUNT(*) AS c FROM submissions')['c'],
    }

    def purge():
        for table in PURGE_TABLES:
            db.run(f'DELETE FROM {table}')
        # Keep the authenticated administrator so the clean installation is
        # still accessible after this request finishes.
        db.run(
            'INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)',
            admin['id'], admin['name'], admin['email'], admin.get('avatar'), 'Admin',
        )

    db.with_transaction(purge)
    ensure_bootstrap_data()
    return counts


@router.post('/purge')
def purge_database(request: Request, body: dict):
    # Unlike the persona-oriented routes, this destructive operation must not
    # fall back to the default admin when the identity header is missing.
    acting_id = request.headers.get('x-user-id')
    admin = db.q1(
        'SELECT id, name, email, avatar, role FROM users WHERE id = ?',
        acting_id or '',
    )
    if not admin or admin['role'] != 'Admin':
        return JSONResponse({'error': 'Permission denied: Admin role required'}, 403)
    if not isinstance(body, dict) or body.get('confirmation') != 'PURGE':
        return JSONResponse({'error': 'Type PURGE to confirm permanent database deletion'}, 400)

    archive_lock = getattr(request.app.state, 'archive_mutation_lock', None)
    if archive_lock is None:
        return JSONResponse({'error': 'Database lock is unavailable'}, 503)
    with archive_lock:
        counts = _purge_jira_data(admin)
    return {
        'success': True,
        'message': 'Database purged. A clean project and your admin account were recreated.',
        'deleted': {
            **counts,
        },
    }
