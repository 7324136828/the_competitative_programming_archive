import json
from urllib.parse import quote

from ...db import db
from ...util import now_iso
from ...config import jira_public_url, ai_tools_token
from .client import register_agent_tool, list_agent_tools
from .tools import TOOLS


def get_last_registration():
    row = db.q1("SELECT value FROM app_settings WHERE key = 'connector.last_registration'")
    if not row:
        return None
    try:
        return json.loads(row['value'])
    except Exception:
        return None


def register_tools_with_connector() -> dict:
    registered = []
    failed = []
    token = ai_tools_token()
    for t in TOOLS:
        endpoint = f"{jira_public_url()}/api/ai/tools/{t['name']}"
        if token:
            endpoint += f'?token={quote(token)}'
        name = f"jira_{t['name']}"
        try:
            register_agent_tool(name=name, description=f"[Jira] {t['description']}",
                                parameters=t['parameters'], endpoint=endpoint)
            registered.append(name)
        except Exception as err:
            failed.append({'name': name, 'error': str(err)})
    try:
        db.run(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('connector.last_registration', ?, ?)",
            json.dumps({'at': now_iso(), 'registered': len(registered), 'failed': len(failed)}), now_iso(),
        )
    except Exception:
        pass
    return {'registered': registered, 'failed': failed}


def ensure_tools_registered():
    try:
        agent_tools = list_agent_tools()
        have = {t['name'] for t in agent_tools}
        missing = any(f"jira_{t['name']}" not in have for t in TOOLS)
        if missing:
            out = register_tools_with_connector()
            print(f"Connector tool re-registration: {len(out['registered'])} registered, {len(out['failed'])} failed")
    except Exception:
        pass
