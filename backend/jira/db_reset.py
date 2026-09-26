"""Port of src/db/reset.ts — wipe the SQLite DB + uploads and re-bootstrap.

Usage:
    python -m app.db_reset           # dry run: list what would be deleted
    python -m app.db_reset --yes     # actually delete
    python -m app.db_reset --force --yes   # skip the "server running" check
"""
import os
import sys
import urllib.request

from .config import _is_test, resolve_db_path, resolve_upload_dir


def main():
    if _is_test():
        print('Refusing to reset the database while JIRA_ENV=test.', file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    force = '--force' in args
    yes = '--yes' in args

    db_path = resolve_db_path()
    upload_dir = resolve_upload_dir()

    port = os.environ.get('PORT', '3001')
    if not force:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as res:
                if res.status == 200:
                    print(f'A server is responding at http://127.0.0.1:{port}/api/health. '
                          'Stop it before resetting (or pass --force).', file=sys.stderr)
                    sys.exit(1)
        except Exception:
            pass  # no server running - safe to proceed

    sidecars = [f'{db_path}-wal', f'{db_path}-shm']
    upload_files = ([f for f in os.listdir(upload_dir) if f != '.gitkeep']
                    if os.path.isdir(upload_dir) else [])

    if not yes:
        print('The following would be deleted:')
        print(f'  database: {db_path}')
        for s in sidecars:
            if os.path.exists(s):
                print(f'  sidecar:  {s}')
        print(f'  uploads:  {len(upload_files)} file(s) in {upload_dir} (directory kept)')
        print('\nRe-run with --yes to proceed.')
        sys.exit(1)

    for f in [db_path, *sidecars]:
        if not os.path.exists(f):
            continue
        try:
            os.remove(f)
        except OSError as err:
            print(f'Cannot delete {f}: the database file is in use; stop the server first.',
                  file=sys.stderr)
            sys.exit(1)

    if os.path.isdir(upload_dir):
        for f in upload_files:
            try:
                os.remove(os.path.join(upload_dir, f))
            except OSError as err:
                print(f'Could not delete upload {f}: {err}', file=sys.stderr)

    # Recreate schema + bootstrap data (import opens a fresh connection on the new file)
    from .db import db
    from .seed import ensure_bootstrap_data

    ensure_bootstrap_data()
    users = db.q1('SELECT COUNT(*) as c FROM users')['c']
    projects = db.q1('SELECT COUNT(*) as c FROM projects')['c']
    print(f'Database reset complete: {users} user(s), {projects} project(s).')


if __name__ == '__main__':
    main()
