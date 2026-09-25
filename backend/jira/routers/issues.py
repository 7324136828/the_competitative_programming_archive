from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db, SQL_NOW
from ..services import issues as svc
from ..services.users import resolve_acting_user_id, can_edit_issue

router = APIRouter()


def _deny():
    return JSONResponse({'error': 'Permission denied: Viewer cannot modify issues'}, 403)


@router.get('/cross-team/dependencies')
def cross_team_dependencies():
    try:
        return svc.get_cross_project_dependencies()
    except Exception as err:
        return JSONResponse({'error': str(err)}, 500)


@router.get('')
def list_issues(request: Request, projectId: str | None = None, query: str | None = None,
                assigneeId: str | None = None, status: str | None = None,
                statusNot: str | None = None, priority: str | None = None,
                type: str | None = None, sprintId: str | None = None,
                versionId: str | None = None, unassigned: str | None = None):
    try:
        filter_ = {
            'projectId': projectId,
            'query': query,
            'assigneeId': assigneeId,
            'status': status,
            'statusNot': statusNot,
            'priority': priority,
            'type': type,
            'versionId': versionId,
            'unassigned': unassigned == 'true',
        }
        if sprintId is not None:
            filter_['sprintId'] = None if sprintId == 'none' else sprintId
        return svc.search_issues(filter_)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 500)


@router.post('', status_code=201)
def create_issue_route(request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot create issues'}, 403)
    try:
        return svc.create_issue(body, user_id)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.get('/{id}')
def get_issue(id: str):
    issue = svc.get_issue_by_id(id)
    if not issue:
        return JSONResponse({'error': 'Issue not found'}, 404)
    return issue


@router.get('/by-problem/{problem_id}')
def get_issue_for_problem(problem_id: int):
    issue = svc.get_issue_by_problem_id(problem_id)
    if not issue:
        return JSONResponse({'error': 'No story is linked to this problem'}, 404)
    return issue


@router.post('/from-problem/{problem_id}', status_code=201)
def ensure_issue_for_problem(problem_id: int, request: Request, body: dict | None = None):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot create issues'}, 403)
    body = body or {}
    try:
        existing = svc.get_issue_by_problem_id(problem_id)
        issue = existing or svc.ensure_story_for_problem(
            problem_id,
            project_id=body.get('projectId'),
            parent_id=body.get('parentId'),
            creator_id=user_id,
        )
        return issue
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.patch('/{id}')
def patch_issue(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot edit issues'}, 403)

    updates = []
    params = []
    if 'summary' in body:
        if not str(body.get('summary') or '').strip():
            return JSONResponse({'error': 'Summary cannot be empty'}, 400)
        updates.append('summary = ?')
        params.append(str(body['summary']).strip())
    if 'description' in body:
        updates.append('description = ?')
        params.append(body['description'])
    if 'priority' in body:
        updates.append('priority = ?')
        params.append(body['priority'])
    if 'type' in body:
        updates.append('type = ?')
        params.append(body['type'])
    if 'story_type' in body or 'storyType' in body:
        updates.append('story_type = ?')
        params.append(body.get('story_type') or body.get('storyType'))
    if 'difficulty' in body:
        updates.append('difficulty = ?')
        params.append(body['difficulty'])
    if 'parentId' in body or 'parent_id' in body:
        updates.append('parent_id = ?')
        params.append(body.get('parentId') or body.get('parent_id'))
    if 'submissionStatus' in body or 'submission_status' in body:
        updates.append('submission_status = ?')
        params.append(body.get('submissionStatus') or body.get('submission_status'))

    if updates:
        updates.append(f'updated_at = {SQL_NOW}')
        params.append(id)
        db.run(f"UPDATE issues SET {', '.join(updates)} WHERE id = ?", *params)
    return svc.get_issue_by_id(id)



@router.delete('/{id}')
def delete_issue(id: str, request: Request):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot delete issues'}, 403)
    issue = db.q1('SELECT id FROM issues WHERE id = ?', id)
    if not issue:
        return JSONResponse({'error': 'Issue not found'}, 404)
    svc.delete_issue_recursive(id)
    return {'success': True}


@router.post('/{id}/assign')
def assign(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot assign issues'}, 403)
    try:
        return svc.assign_issue(id, body.get('assigneeId'))
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/subtasks', status_code=201)
def create_subtask(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot create subtasks'}, 403)
    try:
        return svc.create_subtask(id, body.get('summary'), body.get('assigneeId'), body.get('storyPoints'), user_id)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/links', status_code=201)
def create_link(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot link issues'}, 403)
    try:
        return svc.link_issues(id, body.get('targetId'), body.get('linkType') or 'blocks')
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.delete('/links/{link_id}')
def remove_link(link_id: str, request: Request):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot delete links'}, 403)
    try:
        svc.delete_link(link_id)
        return {'success': True}
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/rank')
def rank(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot rank backlog'}, 403)
    try:
        return svc.reorder_issue(id, float(body.get('targetRank')))
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/points')
def points(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot change points'}, 403)
    pts = body.get('points')
    try:
        return svc.update_story_points(id, float(pts) if pts is not None else None)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/sprint')
def sprint(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot change sprint'}, 403)
    try:
        return svc.set_issue_sprint(id, body.get('sprintId') or None)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/status')
def status(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot update status'}, 403)
    try:
        return svc.update_issue_status(id, body.get('status'), user_id)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.get('/{id}/comments')
def comments(id: str):
    return svc.get_comments(id)


@router.post('/{id}/comments', status_code=201)
def create_comment(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot comment'}, 403)
    try:
        return svc.add_comment(id, user_id, body.get('body'))
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.delete('/comments/{comment_id}')
def remove_comment(comment_id: str, request: Request):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot delete comment'}, 403)
    svc.delete_comment(comment_id)
    return {'success': True}


@router.post('/{id}/watch')
def watch(id: str, request: Request):
    user_id = resolve_acting_user_id(request)
    return {'isWatching': svc.toggle_watch(id, user_id)}


@router.get('/{id}/worklogs')
def worklogs(id: str):
    return svc.get_worklogs(id)


@router.post('/{id}/worklogs', status_code=201)
def create_worklog(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot log work'}, 403)
    try:
        return svc.log_work(id, user_id, float(body.get('timeSpentMinutes') or 0),
                            body.get('description'), body.get('startedAt'))
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/dates')
def dates(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot change dates'}, 403)
    try:
        return svc.update_issue_dates(id, body.get('startDate') or None, body.get('dueDate') or None)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/version')
def version(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot change version'}, 403)
    try:
        return svc.set_issue_version(id, body.get('versionId') or None)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/custom-fields')
def custom_field(id: str, request: Request, body: dict):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot change custom fields'}, 403)
    try:
        svc.set_custom_field_value(id, body.get('fieldId'), body.get('value'))
        return {'success': True}
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/import-stories', status_code=201)
async def import_stories_route(request: Request):
    user_id = resolve_acting_user_id(request)
    if not can_edit_issue(user_id):
        return JSONResponse({'error': 'Permission denied: Viewer cannot import stories'}, 403)
    try:
        import json
        body = await request.json()
        project_id = 'proj_cp'

        epic_title = 'Competitive Programming Archive'
        stories = []
        if isinstance(body, list):
            stories = body
        elif isinstance(body, dict):
            project_id = body.get('projectId') or 'proj_cp'
            epic_title = body.get('epicTitle') or 'Competitive Programming Archive'
            stories = body.get('stories') or []

        p = db.q1('SELECT id, key FROM projects WHERE id = ?', project_id)
        if not p:
            first_p = db.q1('SELECT id, key FROM projects ORDER BY rowid ASC LIMIT 1')
            if first_p:
                project_id = first_p['id']

        # Find or create Epic (created by user / import)
        epic = db.q1("SELECT id FROM issues WHERE project_id = ? AND type = 'Epic' AND summary = ?", project_id, epic_title)
        if not epic:
            epic = svc.create_issue({
                'projectId': project_id,
                'type': 'Epic',
                'summary': epic_title,
                'description': 'User-created epic containing problem set features and stories.',
                'storyPoints': None,
            }, user_id)
        epic_id = epic['id']

        features_created = {}
        imported_issues = []

        for item in stories:
            if not isinstance(item, dict):
                continue
            title = item.get('title') or item.get('summary') or 'Untitled Story'
            desc = item.get('problem_statements') or item.get('description') or ''
            tags = item.get('tags') or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [tags]

            # Problem sets are attributed to features!
            feature_name = (tags[0] if tags else 'General Problem Set')
            if feature_name not in features_created:
                feat = db.q1("SELECT id FROM issues WHERE project_id = ? AND type = 'Feature' AND summary = ? AND parent_id = ?",
                             project_id, feature_name, epic_id)
                if not feat:
                    feat = svc.create_issue({
                        'projectId': project_id,
                        'type': 'Feature',
                        'summary': feature_name,
                        'description': f'Problem set attributed to {feature_name}',
                        'parentId': epic_id,
                    }, user_id)
                features_created[feature_name] = feat['id']
            feature_id = features_created[feature_name]

            story_type = item.get('story_type') or item.get('storyType') or 'coding'
            diff = item.get('difficulty') or 'Medium'
            samples = item.get('sample_input_output') or item.get('samples') or []
            hints = item.get('hints') or []
            pts = item.get('story_points') or (3 if diff == 'Easy' else 5 if diff == 'Medium' else 8)

            problem_id = None
            if story_type == 'coding':
                problem_id = svc.ensure_archive_problem(item)['id']
                existing_story = svc.get_issue_by_problem_id(problem_id)
                if existing_story:
                    imported_issues.append(existing_story)
                    continue

            created = svc.create_issue({
                'projectId': project_id,
                'type': 'Story',
                'storyType': story_type,
                'summary': title,
                'description': desc,
                'difficulty': diff,
                'parentId': feature_id,
                'storyPoints': pts,
                'sampleIo': samples,
                'hints': hints,
                'tags': tags,
                'submissionStatus': 'Unsolved',
                'problemId': problem_id,
            }, user_id)
            imported_issues.append(created)

        return {
            'success': True,
            'imported': len(imported_issues),
            'features': len(features_created),
            'epicId': epic_id,
            'stories': imported_issues,
        }
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/submission')
def update_submission_route(id: str, request: Request, body: dict):
    verdict = body.get('verdict') or body.get('status') or 'Accepted'
    test_results = body.get('test_results') or body.get('testResults')
    user_id = resolve_acting_user_id(request)
    try:
        updated = svc.update_coding_story_submission(id, verdict, test_results, user_id=user_id)
        if not updated:
            return JSONResponse({'error': 'Issue not found'}, 404)
        return updated
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)

