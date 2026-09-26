import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import db
from .config import resolve_upload_dir, _is_test
from .seed import seed_demo_data, ensure_bootstrap_data
from .middleware import ActivityMiddleware
from .routers import (
    projects, issues, sprints, workflows, automation, dev, filters, dashboard,
    versions, custom_fields, attachments, users, metrics, ai, activity, admin,
)
from ..study.router import router as study_router

SERVER_DIR = Path(__file__).resolve().parent.parent
CLIENT_DIST = (SERVER_DIR.parent / 'client' / 'dist').resolve()

def initialize_jira_data():
    """Seed only after the unified database has had a chance to import data."""
    if _is_test() or os.environ.get('SEED_DEMO') == 'true':
        seed_demo_data()
    ensure_bootstrap_data()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# User activity audit trail (records API steps; skips noisy polls)
app.add_middleware(ActivityMiddleware)


@app.middleware('http')
async def scope_api_middleware(request: Request, call_next):
    # Equivalent of app.use('/api', activityMiddleware): nothing needed beyond
    # ActivityMiddleware; this stub exists only to normalize 404s for /api paths
    # to Express-style JSON instead of FastAPI's {"detail": ...}.
    response = await call_next(request)
    if response.status_code == 404 and request.url.path.startswith('/api'):
        return JSONResponse({'error': 'Not found'}, 404)
    return response


# Static uploads
_upload_dir = resolve_upload_dir()
os.makedirs(_upload_dir, exist_ok=True)
app.mount('/uploads', StaticFiles(directory=_upload_dir), name='uploads')

# API routes
app.include_router(projects.router, prefix='/api/projects')
app.include_router(issues.router, prefix='/api/issues')
app.include_router(sprints.router, prefix='/api/sprints')
app.include_router(workflows.router, prefix='/api/workflows')
app.include_router(automation.router, prefix='/api/automation')
app.include_router(dev.router, prefix='/api/dev')
app.include_router(filters.router, prefix='/api/filters')
app.include_router(dashboard.router, prefix='/api/dashboard')
app.include_router(versions.router, prefix='/api/versions')
app.include_router(custom_fields.router, prefix='/api/custom-fields')
app.include_router(attachments.router, prefix='/api/attachments')
app.include_router(metrics.router, prefix='/api/metrics')
app.include_router(ai.router, prefix='/api/ai')
app.include_router(activity.router, prefix='/api/activity')
app.include_router(admin.router, prefix='/api/admin')
app.include_router(users.router, prefix='/api')
app.include_router(study_router, prefix='/api')


@app.get('/api/health')
def health_check():
    journal_mode = 'memory'
    foreign_keys = True
    fts5 = False
    try:
        journal_mode = (db.q1('PRAGMA journal_mode') or {}).get('journal_mode') or 'memory'
        foreign_keys = (db.q1('PRAGMA foreign_keys') or {}).get('foreign_keys') == 1
        fts5 = bool(db.q1(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'issues_fts'"))
    except Exception:
        pass
    display_path = ':memory:' if db.path == ':memory:' else os.path.relpath(db.path, str(SERVER_DIR))
    from .util import now_iso
    return {
        'status': 'ok',
        'timestamp': now_iso(),
        'db': {
            'path': display_path,
            'journalMode': journal_mode,
            'foreignKeys': foreign_keys,
            'fts5': fts5,
        },
    }


# Serve frontend client dist if built, with SPA fallback
if CLIENT_DIST.is_dir():
    app.mount('/assets', StaticFiles(directory=str(CLIENT_DIST / 'assets')), name='client-assets')

    @app.get('/{full_path:path}', include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith(('api', 'uploads')):
            return JSONResponse({'error': 'Not found'}, 404)
        candidate = (CLIENT_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(CLIENT_DIST)):
            return FileResponse(str(candidate))
        index = CLIENT_DIST / 'index.html'
        if index.is_file():
            return FileResponse(str(index))
        return JSONResponse({'error': 'Not found'}, 404)


def start_tool_registration():
    from . import config as cfg
    if not cfg.register_tools_enabled():
        return
    from .services.ai.registration import register_tools_with_connector, ensure_tools_registered

    def _register():
        try:
            out = register_tools_with_connector()
            print(f"Connector tool registration: {len(out['registered'])} registered, {len(out['failed'])} failed")
        except Exception as err:
            print(f'Connector tool registration failed: {err}')
        interval = cfg.register_interval_ms()
        if interval > 0:
            def _loop():
                while True:
                    time.sleep(interval / 1000)
                    try:
                        ensure_tools_registered()
                    except Exception:
                        pass
            threading.Thread(target=_loop, daemon=True).start()

    threading.Thread(target=_register, daemon=True).start()


if not _is_test():
    @app.on_event('startup')
    def _on_startup():
        initialize_jira_data()
        start_tool_registration()
