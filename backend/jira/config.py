import os
import re
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent


def _is_test() -> bool:
    return os.environ.get('NODE_ENV') == 'test' or os.environ.get('JIRA_ENV') == 'test'


def load_env_file():
    if _is_test():
        return
    env_path = SERVER_DIR / '.env'
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as err:
        print(f'Failed to parse {env_path}: {err}')


load_env_file()


def resolve_db_path() -> str:
    configured = os.environ.get('DATABASE_PATH') or os.environ.get('DB_PATH')
    if configured:
        p = Path(configured)
        return str(p if p.is_absolute() else (SERVER_DIR.parent / p).resolve())
    if _is_test():
        return ':memory:'
    from ..paths import default_database_path
    return str(default_database_path().resolve())


def resolve_upload_dir() -> str:
    if _is_test():
        return os.path.join(tempfile.gettempdir(), f'jira-test-uploads-{os.getpid()}')
    if os.environ.get('UPLOAD_DIR'):
        p = Path(os.environ['UPLOAD_DIR'])
        return str(p if p.is_absolute() else (SERVER_DIR / p).resolve())
    if os.environ.get('DATABASE_PATH') or os.environ.get('DB_PATH'):
        return os.path.join(os.path.dirname(resolve_db_path()), 'uploads')
    return str((SERVER_DIR / 'uploads').resolve())


# ---------- Connector / AI settings (read live so tests can toggle env) ----------

def connector_url() -> str:
    return os.environ.get('CONNECTOR_URL') or 'http://127.0.0.1:8301'


def connector_api_key() -> str:
    return os.environ.get('CONNECTOR_API_KEY') or 'local-placeholder'


def connector_timeout_ms() -> int:
    try:
        return int(os.environ.get('CONNECTOR_TIMEOUT_MS') or 90000)
    except ValueError:
        return 90000


def ai_enabled() -> bool:
    return (os.environ.get('AI_ENABLED') or 'true') != 'false'


def ai_assistant_max_steps() -> int:
    try:
        return int(os.environ.get('AI_ASSISTANT_MAX_STEPS') or 6)
    except ValueError:
        return 6


def ai_max_input_chars() -> int:
    try:
        return int(os.environ.get('AI_MAX_INPUT_CHARS') or 12000)
    except ValueError:
        return 12000


def jira_public_url() -> str:
    return os.environ.get('JIRA_PUBLIC_URL') or f"http://127.0.0.1:{os.environ.get('PORT', 3001)}"


def ai_tools_token() -> str | None:
    return os.environ.get('AI_TOOLS_TOKEN') or None


def ai_intake_token() -> str | None:
    return os.environ.get('AI_INTAKE_TOKEN') or None


def register_tools_enabled() -> bool:
    return (os.environ.get('CONNECTOR_REGISTER_TOOLS') or 'true') != 'false'


def register_interval_ms() -> int:
    try:
        return int(os.environ.get('CONNECTOR_REGISTER_INTERVAL_MS') or 300000)
    except ValueError:
        return 300000


def activity_log_enabled() -> bool:
    return (os.environ.get('ACTIVITY_LOG_ENABLED') or 'true') != 'false'


def activity_forward_enabled() -> bool:
    # Off under tests unless explicitly enabled, so the suite never hits a real connector.
    if _is_test():
        return os.environ.get('ACTIVITY_FORWARD_ENABLED') == 'true'
    return (os.environ.get('ACTIVITY_FORWARD_ENABLED') or 'true') != 'false'


def activity_session_title() -> str:
    return os.environ.get('ACTIVITY_SESSION_TITLE') or 'Jira Activity Log'


def get_configured_model() -> str | None:
    from .db import db
    row = db.q1("SELECT value FROM app_settings WHERE key = 'ai.model'")
    return row['value'] if row else None


def set_configured_model(model: str | None):
    from .db import db
    from .util import now_iso
    if model is None:
        db.run("DELETE FROM app_settings WHERE key = 'ai.model'")
    else:
        db.run(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('ai.model', ?, ?)",
            model, now_iso(),
        )


def resolve_model(request_model: str | None = None) -> dict:
    if request_model:
        return {'model': request_model, 'modelSource': 'request'}
    configured = get_configured_model()
    if configured:
        return {'model': configured, 'modelSource': 'settings'}
    if os.environ.get('CONNECTOR_MODEL'):
        return {'model': os.environ['CONNECTOR_MODEL'], 'modelSource': 'env'}
    return {'model': 'low-cost-mixed-model', 'modelSource': 'default'}
