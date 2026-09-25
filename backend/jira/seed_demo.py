"""Port of src/db/seedDemo.ts — populate the database with the demo dataset."""
from .db import db
from .seed import seed_demo_data, ensure_bootstrap_data


def main():
    seed_demo_data()
    ensure_bootstrap_data()
    users = db.q1('SELECT COUNT(*) as c FROM users')['c']
    projects = db.q1('SELECT COUNT(*) as c FROM projects')['c']
    issues = db.q1('SELECT COUNT(*) as c FROM issues')['c']
    print(f'Demo seed complete: {users} user(s), {projects} project(s), {issues} issue(s).')


if __name__ == '__main__':
    main()
