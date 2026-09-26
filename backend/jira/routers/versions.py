from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id

router = APIRouter()


@router.get('/projects/{project_id}')
def list_versions(project_id: str):
    return db.q(
        """SELECT v.*,
                  COUNT(i.id) as total_issues,
                  SUM(CASE WHEN sc.category = 'DONE' THEN 1 ELSE 0 END) as done_issues,
                  SUM(COALESCE(i.story_points, 0)) as total_points,
                  SUM(CASE WHEN sc.category = 'DONE' THEN COALESCE(i.story_points, 0) ELSE 0 END) as done_points
           FROM versions v
           LEFT JOIN issues i ON v.id = i.version_id
           LEFT JOIN issue_status_categories sc ON sc.issue_id = i.id
           WHERE v.project_id = ?
           GROUP BY v.id
           ORDER BY v.release_date ASC""",
        project_id,
    )


@router.post('/projects/{project_id}', status_code=201)
def create_version(project_id: str, body: dict):
    body = body or {}
    if not body.get('name'):
        return JSONResponse({'error': 'Version name is required'}, 400)
    vid = new_id('ver')
    db.run(
        'INSERT INTO versions (id, project_id, name, description, release_date, status) VALUES (?, ?, ?, ?, ?, ?)',
        vid, project_id, body['name'], body.get('description') or '',
        body.get('releaseDate') or None, body.get('status') or 'unreleased',
    )
    return db.q1('SELECT * FROM versions WHERE id = ?', vid)


@router.patch('/{id}/status')
def set_status(id: str, body: dict):
    body = body or {}
    status = body.get('status')
    if status not in ('unreleased', 'released', 'archived'):
        return JSONResponse({'error': 'Invalid status'}, 400)
    db.run('UPDATE versions SET status = ? WHERE id = ?', status, id)
    return db.q1('SELECT * FROM versions WHERE id = ?', id)
