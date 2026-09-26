import json

import httpx

from ...db import db
from ...util import new_id, now_iso, now_ms
from ...config import (
    connector_url,
    connector_api_key,
    connector_timeout_ms,
    resolve_model as resolve_configured_model,
)


class ConnectorError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = None


def _url(path: str) -> str:
    return f"{connector_url().rstrip('/')}{path}"


def log_ai_request(feature: str, model=None, user_id=None, project_id=None,
                   status='ok', latency_ms=None, usage=None, error=None) -> str:
    rid = new_id('air')
    db.run(
        """INSERT INTO ai_requests
             (id, feature, model, user_id, project_id, status, latency_ms,
              prompt_tokens, completion_tokens, total_tokens, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rid, feature, model, user_id, project_id, status, latency_ms,
        (usage or {}).get('prompt_tokens'), (usage or {}).get('completion_tokens'),
        (usage or {}).get('total_tokens'), error, now_iso(),
    )
    return rid


def _request(path: str, method: str = 'GET', body=None, timeout_ms: int | None = None) -> httpx.Response:
    return httpx.request(
        method, _url(path),
        content=json.dumps(body) if body is not None else None,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {connector_api_key()}',
        },
        timeout=(timeout_ms or connector_timeout_ms()) / 1000,
    )


def _parse_error(res: httpx.Response) -> ConnectorError:
    code = 'connector_error'
    message = f'Connector returned HTTP {res.status_code}'
    try:
        body = res.json()
        err = body.get('error') if isinstance(body, dict) else None
        if isinstance(err, str):
            message = err
        elif isinstance(err, dict):
            code = err.get('code') or code
            message = err.get('message') or message
        elif isinstance(body, dict) and body.get('message'):
            message = body['message']
    except Exception:
        pass
    return ConnectorError(res.status_code, code, message)


def chat_completion(model: str, messages: list, tools=None, tool_choice=None,
                    feature: str = 'unknown', user_id=None, project_id=None) -> dict:
    body = {'model': model, 'messages': messages}
    if tools is not None:
        body['tools'] = tools
    if tool_choice is not None:
        body['tool_choice'] = tool_choice

    started = now_ms()
    try:
        res = _request('/v1/chat/completions', 'POST', body)
    except Exception as err:
        latency = now_ms() - started
        error = ConnectorError(0, 'connector_unreachable', f'Connector unreachable: {err}')
        error.request_id = log_ai_request(feature, model, user_id, project_id,
                                          status='error', latency_ms=latency, error=str(error))
        raise error
    latency = now_ms() - started

    if res.status_code >= 400:
        err = _parse_error(res)
        err.request_id = log_ai_request(feature, model, user_id, project_id,
                                        status='error', latency_ms=latency, error=str(err))
        raise err

    data = res.json()
    message = (data.get('choices') or [{}])[0].get('message') or {}
    usage = data.get('usage')
    request_id = log_ai_request(feature, model, user_id, project_id,
                                status='ok', latency_ms=latency, usage=usage)
    return {'message': message, 'usage': usage, 'raw': data, 'requestId': request_id, 'latencyMs': latency}


def list_models() -> list:
    res = _request('/v1/models', timeout_ms=10000)
    if res.status_code >= 400:
        raise _parse_error(res)
    return res.json().get('data') or []


def resolve_model(request_model: str | None = None, available_models: list | None = None) -> dict:
    """Resolve to a model that is actually active in the Connector."""
    resolved = resolve_configured_model(request_model)
    if available_models is None:
        try:
            records = list_models()
        except Exception:
            return resolved
    else:
        records = available_models
    model_ids = [
        record.get('id') if isinstance(record, dict) else record
        for record in records
    ]
    model_ids = [model_id for model_id in model_ids if isinstance(model_id, str) and model_id]
    if not model_ids or resolved['model'] in model_ids:
        return resolved
    return {'model': model_ids[0], 'modelSource': 'connector'}


def health() -> dict:
    res = _request('/api/health', timeout_ms=5000)
    if res.status_code >= 400:
        raise _parse_error(res)
    return res.json()


def list_agent_tools() -> list:
    res = _request('/api/agent/tools', timeout_ms=10000)
    if res.status_code >= 400:
        raise _parse_error(res)
    return res.json()


def register_agent_tool(name: str, description: str, parameters: dict, endpoint: str):
    res = _request('/api/agent/register-tool', 'POST',
                   {'name': name, 'description': description, 'parameters': parameters, 'endpoint': endpoint},
                   timeout_ms=10000)
    if res.status_code >= 400:
        raise _parse_error(res)
    return res.status_code
