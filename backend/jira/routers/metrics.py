from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..services.metrics import (
    compute_issue_metrics, get_issue_events, get_sprint_metrics, get_project_metrics,
)

router = APIRouter()


@router.get('/issues/{id_or_key}')
def issue_metrics(id_or_key: str):
    issue = db.q1('SELECT * FROM issues WHERE id = ? OR key = ?', id_or_key, id_or_key)
    if not issue:
        return JSONResponse({'error': 'Issue not found'}, 404)
    worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', issue['id'])
    metrics = compute_issue_metrics(issue, get_issue_events(issue['id']), worklogs)
    return {k: v for k, v in metrics.items() if k != '_activeIntervals'}


@router.get('/sprints/{id}')
def sprint_metrics(id: str):
    metrics = get_sprint_metrics(id)
    if not metrics:
        return JSONResponse({'error': 'Sprint not found'}, 404)
    return metrics


@router.get('/projects/{project_id}')
def project_metrics(project_id: str):
    metrics = get_project_metrics(project_id)
    if not metrics:
        return JSONResponse({'error': 'Project not found'}, 404)
    return metrics


@router.get('/projects/{project_id}/issues')
def project_issues_metrics(project_id: str):
    project = db.q1('SELECT * FROM projects WHERE id = ?', project_id)
    if not project:
        return JSONResponse({'error': 'Project not found'}, 404)
    issues = db.q('SELECT * FROM issues WHERE project_id = ? ORDER BY key ASC', project_id)
    rows = []
    for issue in issues:
        worklogs = db.q('SELECT * FROM worklogs WHERE issue_id = ?', issue['id'])
        m = compute_issue_metrics(issue, get_issue_events(issue['id']), worklogs)
        rows.append({
            'id': issue['id'],
            'key': issue['key'],
            'summary': issue['summary'],
            'type': issue['type'],
            'priority': issue['priority'],
            'storyPoints': issue['story_points'],
            'assigneeId': issue['assignee_id'],
            'currentStatus': m['currentStatus'],
            'currentStatusCategory': m['currentStatusCategory'],
            'isResolved': m['isResolved'],
            'createdAt': m['createdAt'],
            'firstStartedAt': m['firstStartedAt'],
            'resolvedAt': m['resolvedAt'],
            'leadTimeSeconds': m['leadTimeSeconds'],
            'cycleTimeSeconds': m['cycleTimeSeconds'],
            'elapsedSeconds': m['elapsedSeconds'],
            'activeTimeSeconds': m['activeTimeSeconds'],
            'waitTimeSeconds': m['waitTimeSeconds'],
            'reopenCount': m['reopenCount'],
            'transitionCount': m['transitionCount'],
            'loggedMinutes': m['loggedMinutes'],
            'estimateAccuracy': m['estimateAccuracy'],
        })
    return rows
