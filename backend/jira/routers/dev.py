import random

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.dev import get_linked_pull_requests, link_pull_request, update_pull_request_status
from ..services.issues import get_issue_by_id

router = APIRouter()


@router.get('/issues/{issue_id}/prs')
def list_prs(issue_id: str):
    return get_linked_pull_requests(issue_id)


@router.post('/issues/{issue_id}/prs', status_code=201)
def create_pr(issue_id: str, body: dict):
    body = body or {}
    if not body.get('repo') or not body.get('prNumber') or not body.get('title'):
        return JSONResponse({'error': 'repo, prNumber, and title are required'}, 400)
    pr_number = body['prNumber']
    return link_pull_request(
        issue_id=issue_id,
        repo=body['repo'],
        pr_number=int(pr_number),
        title=body['title'],
        branch=body.get('branch') or 'main',
        status=body.get('status') or 'OPEN',
        url=body.get('url') or f"https://{body['repo']}/pull/{pr_number}",
    )


@router.post('/simulate-pr', status_code=201)
def simulate_pr(body: dict):
    body = body or {}
    issue_key = body.get('issueKey')
    if not issue_key:
        return JSONResponse({'error': 'issueKey is required'}, 400)
    issue = get_issue_by_id(issue_key)
    if not issue:
        return JSONResponse({'error': f'Issue {issue_key} not found'}, 404)
    pr_number = random.randint(100, 999)
    return link_pull_request(
        issue_id=issue['id'],
        repo='github.com/company/core-service',
        pr_number=pr_number,
        title=body.get('title') or f"feat({issue['key'].lower()}): {issue['summary']}",
        branch=body.get('branch') or f"feature/{issue['key'].lower()}-implementation",
        status='OPEN',
        url=f'https://github.com/company/core-service/pull/{pr_number}',
    )


@router.patch('/prs/{id}/status')
def pr_status(id: str, body: dict):
    body = body or {}
    update_pull_request_status(id, body.get('status'))
    return {'success': True, 'status': body.get('status')}
