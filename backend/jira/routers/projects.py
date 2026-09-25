import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..services.projects import create_project_with_default_workflow
from ..services.users import resolve_acting_user_id, can_configure_project

router = APIRouter()


@router.get('')
def list_projects():
    return db.q(
        """SELECT p.*, u.name as lead_name, u.avatar as lead_avatar,
                  (SELECT COUNT(*) FROM issues WHERE project_id = p.id) as total_issues,
                  (SELECT COUNT(*) FROM issues i JOIN issue_status_categories sc ON sc.issue_id = i.id
                    WHERE i.project_id = p.id AND sc.category = 'DONE') as completed_issues
           FROM projects p
           LEFT JOIN users u ON p.lead_id = u.id
           ORDER BY p.name ASC"""
    )


@router.get('/{id}')
def get_project(id: str):
    project = db.q1(
        """SELECT p.*, u.name as lead_name, u.avatar as lead_avatar
           FROM projects p LEFT JOIN users u ON p.lead_id = u.id
           WHERE p.id = ? OR p.key = ?""",
        id, id,
    )
    if not project:
        return JSONResponse({'error': 'Project not found'}, 404)
    return project


@router.post('', status_code=201)
def create_project(request: Request, body: dict):
    acting = resolve_acting_user_id(request)
    if not can_configure_project(acting):
        return JSONResponse({'error': 'Permission denied: Admin role required'}, 403)

    body = body or {}
    key, name = body.get('key'), body.get('name')
    if not key or not name:
        return JSONResponse({'error': 'Key and Name are required'}, 400)

    upper_key = str(key).upper()
    if not re.match(r'^[A-Z][A-Z0-9]{1,9}$', upper_key):
        return JSONResponse({'error': 'Project key must match ^[A-Z][A-Z0-9]{1,9}$'}, 400)

    if db.q1('SELECT id FROM projects WHERE key = ?', upper_key):
        return JSONResponse({'error': 'A project with this key already exists'}, 409)

    lead = body.get('leadId')
    if lead and not db.q1('SELECT id FROM users WHERE id = ?', lead):
        lead = None
    if not lead:
        lead = acting

    try:
        project = create_project_with_default_workflow(
            key=upper_key, name=name, description=body.get('description') or '', lead_id=lead)
        return db.q1(
            """SELECT p.*, u.name as lead_name, u.avatar as lead_avatar,
                      0 as total_issues, 0 as completed_issues
               FROM projects p LEFT JOIN users u ON p.lead_id = u.id WHERE p.id = ?""",
            project['id'],
        )
    except Exception as err:
        return JSONResponse({'error': str(err)}, 400)
