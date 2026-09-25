import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id, generate_avatar
from ..services.users import resolve_acting_user_id, can_configure_project
from ..services.notifications import get_user_notifications, mark_notification_read

router = APIRouter()

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+$')
ROLES = ['Admin', 'Member', 'Viewer']


@router.get('/users')
def list_users():
    return db.q('SELECT id, name, email, avatar, role FROM users ORDER BY name ASC')


@router.post('/users', status_code=201)
def create_user(request: Request, body: dict):
    acting = resolve_acting_user_id(request)
    if not can_configure_project(acting):
        return JSONResponse({'error': 'Permission denied: Admin role required'}, 403)

    body = body or {}
    name, email, role = body.get('name'), body.get('email'), body.get('role')
    if not name or not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        return JSONResponse({'error': 'Name is required (1-80 characters)'}, 400)
    if not email or not EMAIL_RE.match(str(email)):
        return JSONResponse({'error': 'A valid email is required'}, 400)
    user_role = 'Member' if role is None else role
    if user_role not in ROLES:
        return JSONResponse({'error': f"Role must be one of {', '.join(ROLES)}"}, 400)
    if db.q1('SELECT id FROM users WHERE email = ?', email):
        return JSONResponse({'error': 'A user with this email already exists'}, 409)

    uid = new_id('u')
    trimmed = name.strip()
    db.run('INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)',
           uid, trimmed, email, generate_avatar(trimmed), user_role)
    return db.q1('SELECT id, name, email, avatar, role FROM users WHERE id = ?', uid)


@router.get('/notifications')
def notifications(request: Request):
    return get_user_notifications(resolve_acting_user_id(request))


@router.post('/notifications/{id}/read')
def read_notification(id: str):
    mark_notification_read(id)
    return {'success': True}
