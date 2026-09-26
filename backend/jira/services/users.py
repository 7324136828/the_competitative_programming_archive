from ..db import db


def get_default_user_id() -> str:
    admin = db.q1("SELECT id FROM users WHERE id = 'u_admin'")
    if admin:
        return admin['id']
    first_admin = db.q1("SELECT id FROM users WHERE role = 'Admin' ORDER BY rowid ASC LIMIT 1")
    if first_admin:
        return first_admin['id']
    first = db.q1('SELECT id FROM users ORDER BY rowid ASC LIMIT 1')
    return first['id'] if first else 'u_admin'


def resolve_acting_user_id(request) -> str:
    header = request.headers.get('x-user-id') if request is not None else None
    if header:
        user = db.q1('SELECT id FROM users WHERE id = ?', header)
        if user:
            return user['id']
    return get_default_user_id()


# ----- permissions -----

def get_user_role(user_id: str) -> str:
    user = db.q1('SELECT role FROM users WHERE id = ?', user_id)
    return user['role'] if user else 'Member'


def can_edit_issue(user_id: str) -> bool:
    return get_user_role(user_id) in ('Admin', 'Member')


def can_configure_project(user_id: str) -> bool:
    return get_user_role(user_id) == 'Admin'


def is_user_eligible_for_assignment(user_id: str) -> bool:
    user = db.q1('SELECT id, role FROM users WHERE id = ?', user_id)
    if not user:
        return False
    return user['role'] != 'Viewer'
