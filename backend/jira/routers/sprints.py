from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..services.sprints import create_sprint, start_sprint, complete_sprint
from ..services.burndown import get_sprint_burndown_data

router = APIRouter()


def _err(err: Exception):
    return JSONResponse({'error': str(err)}, 404 if isinstance(err, LookupError) else 400)


@router.get('/projects/{project_id}')
def list_sprints(project_id: str):
    return db.q(
        """SELECT s.*,
                  COUNT(i.id) as issue_count,
                  SUM(COALESCE(i.story_points, 0)) as total_points,
                  SUM(CASE WHEN sc.category = 'DONE' THEN COALESCE(i.story_points, 0) ELSE 0 END) as completed_points
           FROM sprints s
           LEFT JOIN issues i ON s.id = i.sprint_id
           LEFT JOIN issue_status_categories sc ON sc.issue_id = i.id
           WHERE s.project_id = ?
           GROUP BY s.id
           ORDER BY s.created_at ASC""",
        project_id,
    )


@router.post('/projects/{project_id}', status_code=201)
def create_sprint_route(project_id: str, body: dict):
    if not body.get('name'):
        return JSONResponse({'error': 'Sprint name is required'}, 400)
    try:
        return create_sprint(project_id, body['name'], body.get('goal'),
                             body.get('startDate'), body.get('endDate'))
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)


@router.post('/{id}/start')
def start_sprint_route(id: str, body: dict | None = None):
    body = body or {}
    try:
        return start_sprint(id, body.get('startDate'), body.get('endDate'))
    except Exception as err:
        return _err(err)


@router.post('/{id}/complete')
def complete_sprint_route(id: str, body: dict | None = None):
    body = body or {}
    try:
        return complete_sprint(id, body.get('moveIncompleteToNextSprint'), body.get('nextSprintId'))
    except Exception as err:
        return _err(err)


@router.get('/{id}/burndown')
def burndown(id: str):
    data = get_sprint_burndown_data(id)
    if not data:
        return JSONResponse({'error': 'Sprint not found'}, 404)
    return data
