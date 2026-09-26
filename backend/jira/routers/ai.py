import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id, now_iso
from .. import config as cfg
from ..services.users import resolve_acting_user_id, can_edit_issue, can_configure_project, get_user_role
from ..services.ai.client import (
    list_models,
    health,
    list_agent_tools,
    chat_completion,
    resolve_model as resolve_connector_model,
    ConnectorError,
)
from ..services.ai.registration import register_tools_with_connector, get_last_registration
from ..services.ai.service import draft_tickets, recommend_tickets, intake_report
from ..services.ai.tools import TOOLS, TOOL_BY_NAME, openai_tool_specs, record_ticket_link
from ..services.ai.text_calls import parse_text_tool_calls
from ..services.ai.normalizer import normalize_ticket
from ..services.issues import create_issue
from ..services.ai.prompts import ASSISTANT_SYSTEM

router = APIRouter()


def _err(status: int, msg: str, code=None):
    body = {'error': msg}
    if code:
        body['code'] = code
    return JSONResponse(body, status)


def _token_ok(provided: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not provided:
        return False
    try:
        return hmac.compare_digest(provided.encode(), expected.encode())
    except Exception:
        return False


@router.get('/status')
def status():
    resolved = cfg.resolve_model()
    connector = {'reachable': False}
    models = []
    tool_info = {'registered': None, 'names': [], 'lastRegistration': None}
    try:
        h = health()
        connector = {'reachable': True}
        if isinstance(h, dict) and 'version' in h:
            connector['version'] = h['version']
        try:
            model_records = list_models()
            models = [m['id'] for m in model_records]
            resolved = resolve_connector_model(available_models=model_records)
        except Exception:
            pass
        try:
            agent_tools = list_agent_tools()
            jira = [t['name'] for t in agent_tools if t.get('name', '').startswith('jira_')]
            tool_info['registered'] = len(jira) > 0
            tool_info['names'] = jira
        except Exception:
            tool_info['registered'] = None
    except Exception as err:
        connector = {'reachable': False, 'error': str(err)}
    tool_info['lastRegistration'] = get_last_registration()
    return {
        'enabled': cfg.ai_enabled(),
        'connectorUrl': cfg.connector_url(),
        'model': resolved['model'],
        'modelSource': resolved['modelSource'],
        'connector': connector,
        'models': models,
        'tools': tool_info,
        'autoRegister': cfg.register_tools_enabled(),
    }


@router.get('/settings')
def get_settings():
    try:
        resolved = resolve_connector_model()
    except Exception:
        resolved = cfg.resolve_model()
    return {'model': resolved['model'], 'modelSource': resolved['modelSource'],
            'defaultModel': resolved['model']}


@router.put('/settings')
def put_settings(request: Request, body: dict):
    acting = resolve_acting_user_id(request)
    if not can_configure_project(acting):
        return _err(403, 'Permission denied: Admin role required')
    body = body or {}
    model = body.get('model')
    if model is not None and not isinstance(model, str):
        return _err(400, 'model must be a string or null')
    models = None
    if model:
        try:
            models = list_models()
            if models and not any(m['id'] == model for m in models):
                return _err(400, f'Unknown model "{model}"')
        except Exception:
            pass  # connector unreachable: allow setting anyway
    cfg.set_configured_model(model or None)
    try:
        resolved = resolve_connector_model(available_models=models)
    except Exception:
        resolved = cfg.resolve_model()
    return {'model': resolved['model'], 'modelSource': resolved['modelSource'],
            'defaultModel': resolved['model']}


@router.post('/tickets/draft')
def draft(request: Request, body: dict):
    if not cfg.ai_enabled():
        return _err(503, 'AI features are disabled')
    body = body or {}
    text, project_id = body.get('text'), body.get('projectId')
    if not text or not isinstance(text, str) or not text.strip():
        return _err(400, 'text is required')
    if not project_id:
        return _err(400, 'projectId is required')
    max_tickets = min(max(int(body.get('maxTickets') or 5), 1), 10)
    try:
        return draft_tickets(text, project_id, max_tickets,
                             request_model=body.get('model'),
                             user_id=resolve_acting_user_id(request))
    except LookupError as err:
        return _err(404, str(err))
    except ConnectorError as err:
        return _err(502, str(err), code=err.code)
    except Exception as err:
        return _err(500, str(err))


@router.post('/tickets/create', status_code=201)
def create(request: Request, body: dict):
    acting = resolve_acting_user_id(request)
    body = body or {}
    project_id, tickets = body.get('projectId'), body.get('tickets')
    if not project_id:
        return _err(400, 'projectId is required')
    if not isinstance(tickets, list) or not tickets or len(tickets) > 20:
        return _err(400, 'tickets must be an array of 1-20 items')
    if not can_edit_issue(acting):
        return _err(403, 'Permission denied: cannot create issues')

    warnings = []

    def _work():
        out = []
        for raw in tickets:
            t = normalize_ticket(raw)
            if not t:
                warnings.append('Skipped ticket with empty summary')
                continue
            issue = create_issue({
                'projectId': project_id,
                'type': t['type'],
                'summary': t['summary'],
                'description': t['description'],
                'priority': t['priority'],
                'storyPoints': t['storyPoints'],
                'assigneeId': raw.get('assigneeId') or None,
                'sprintId': raw.get('sprintId') or None,
            }, acting, source='ai')
            if isinstance(raw.get('relatesTo'), list):
                for key in raw['relatesTo']:
                    target = db.q1('SELECT id FROM issues WHERE key = ?', key)
                    if not target:
                        warnings.append(f'Unknown issue key {key}')
                        continue
                    try:
                        db.run(
                            'INSERT INTO issue_links (id, source_id, target_id, link_type) VALUES (?, ?, ?, ?)',
                            new_id('link'), issue['id'], target['id'], 'relates_to')
                    except Exception as e:
                        warnings.append(f'Could not link {key}: {e}')
            record_ticket_link(issue['id'], 'created', 'draft', t['summary'], None)
            out.append(issue)
        return out

    try:
        created = db.with_transaction(_work)
        return {'created': created, 'warnings': warnings}
    except Exception as err:
        return _err(400, str(err))


@router.post('/intake')
def intake(request: Request, body: dict):
    if not cfg.ai_enabled():
        return _err(503, 'AI features are disabled')
    expected = cfg.ai_intake_token()
    if expected and not _token_ok(request.headers.get('x-intake-token'), expected):
        return _err(401, 'Invalid or missing intake token')
    acting = resolve_acting_user_id(request)
    if not can_edit_issue(acting):
        return _err(403, 'Permission denied: cannot create issues')
    body = body or {}
    text = body.get('text')
    if not body.get('projectId') and not body.get('projectKey'):
        return _err(400, 'projectId or projectKey is required')
    if not text or not isinstance(text, str) or not text.strip():
        return _err(400, 'text is required')
    thr = body.get('threshold')
    if thr is None:
        thr = 0.75
    else:
        try:
            thr = max(0.0, min(1.0, float(thr)))
        except (TypeError, ValueError):
            thr = 0.75
    source = body.get('source')
    source = source[:50] if isinstance(source, str) and source.strip() else 'webhook'
    try:
        return intake_report(
            text, acting,
            project_id=body.get('projectId'), project_key=body.get('projectKey'),
            source=source, dry_run=bool(body.get('dryRun')), threshold=thr,
            sprint_id=body.get('sprintId') or None, request_model=body.get('model'),
        )
    except LookupError as err:
        return _err(404, str(err))
    except Exception as err:
        return _err(500, str(err))


@router.post('/recommend')
def recommend(request: Request, body: dict):
    body = body or {}
    query = body.get('query')
    if not query or not isinstance(query, str) or not query.strip():
        return _err(400, 'query is required')
    lim = min(max(int(body.get('limit') or 5), 1), 20)
    try:
        return recommend_tickets(
            query, project_id=body.get('projectId') or None, limit=lim,
            include_done=bool(body.get('includeDone')), use_ai=body.get('useAi') is not False,
            request_model=body.get('model'), user_id=resolve_acting_user_id(request))
    except Exception as err:
        return _err(500, str(err))


@router.post('/assistant')
def assistant(request: Request, body: dict):
    if not cfg.ai_enabled():
        return _err(503, 'AI features are disabled')
    acting = resolve_acting_user_id(request)
    body = body or {}
    messages, project_id = body.get('messages'), body.get('projectId')
    if not isinstance(messages, list) or not messages:
        return _err(400, 'messages is required')
    trimmed = messages[-20:]
    last = trimmed[-1]
    if not isinstance(last, dict) or last.get('role') != 'user' \
            or not isinstance(last.get('content'), str) or not last['content'].strip():
        return _err(400, 'The last message must be a user message')
    for m in trimmed:
        if not isinstance(m, dict) or m.get('role') not in ('user', 'assistant') \
                or not isinstance(m.get('content'), str):
            return _err(400, 'messages must contain only user/assistant roles with string content')
        if len(m['content']) > 8000:
            return _err(400, 'Message content exceeds 8000 characters')

    user = db.q1('SELECT * FROM users WHERE id = ?', acting) or {}
    project = db.q1('SELECT * FROM projects WHERE id = ? OR key = ?', project_id, project_id) \
        if project_id else db.q1('SELECT * FROM projects ORDER BY created_at ASC LIMIT 1')

    system = ASSISTANT_SYSTEM \
        .replace('{userName}', user.get('name') or 'Unknown') \
        .replace('{userId}', acting) \
        .replace('{role}', user.get('role') or get_user_role(acting)) \
        .replace('{projectKey}', (project or {}).get('key') or 'none') \
        .replace('{projectName}', (project or {}).get('name') or 'none') \
        .replace('{nowIso}', now_iso())

    try:
        resolved_model = resolve_connector_model(body.get('model'))['model']
    except Exception:
        resolved_model = cfg.resolve_model(body.get('model'))['model']
    can_mutate = can_edit_issue(acting)
    tool_specs = openai_tool_specs(can_mutate)

    convo = [{'role': 'system', 'content': system}, *trimmed]
    steps = []
    calls = 0
    total_latency = 0
    usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    max_steps = cfg.ai_assistant_max_steps()
    reply = None

    def exec_tool(name, args, parse_err, request_id):
        tool = TOOL_BY_NAME.get(name) if name else None
        ok = True
        error = parse_err
        if not tool:
            ok = False
            error = f'Unknown tool {name}'
            result = {'error': error}
        elif tool['mutates'] and not can_mutate:
            ok = False
            error = 'Permission denied'
            result = {'error': error}
        elif parse_err:
            ok = False
            result = {'error': parse_err}
        else:
            try:
                result = tool['handler'](args, {
                    'userId': acting,
                    'projectId': (project or {}).get('id'),
                    'via': 'assistant',
                    'aiRequestId': request_id,
                })
            except Exception as e:
                ok = False
                error = str(e)
                result = {'error': error}
        return {'result': result, 'ok': ok, 'error': error}

    allowed_names = [s['function']['name'] for s in tool_specs]

    try:
        for step in range(max_steps + 1):
            is_last_chance = step == max_steps
            res = chat_completion(
                resolved_model, convo, tools=tool_specs,
                tool_choice='none' if is_last_chance else 'auto',
                feature='assistant', user_id=acting,
                project_id=(project or {}).get('id'))
            calls += 1
            total_latency += res.get('latencyMs') or 0
            if res.get('usage'):
                for k in usage:
                    usage[k] += res['usage'].get(k) or 0

            msg = res.get('message') or {}
            tool_calls = msg.get('tool_calls')
            if isinstance(tool_calls, list) and tool_calls and not is_last_chance:
                convo.append(msg)
                for tc in tool_calls:
                    name = (tc.get('function') or {}).get('name')
                    args = {}
                    parse_err = None
                    try:
                        args = json.loads(tc['function']['arguments']) if (tc.get('function') or {}).get('arguments') else {}
                    except Exception as e:
                        parse_err = f'Invalid tool arguments: {e}'
                    r = exec_tool(name, args, parse_err, res.get('requestId'))
                    result_str = json.dumps(r['result'] if r['result'] is not None else {})[:12000]
                    convo.append({'role': 'tool', 'tool_call_id': tc.get('id'), 'content': result_str})
                    step_rec = {'tool': name, 'arguments': args, 'ok': r['ok'],
                                'resultPreview': result_str[:500], 'mode': 'native'}
                    if r['error']:
                        step_rec['error'] = r['error']
                    steps.append(step_rec)
                continue

            content = msg.get('content') if isinstance(msg.get('content'), str) else ''
            text_calls = parse_text_tool_calls(content, allowed_names)
            if text_calls and not is_last_chance:
                convo.append({'role': 'assistant', 'content': content})
                lines = []
                for c in text_calls:
                    r = exec_tool(c['name'], c['args'], None, res.get('requestId'))
                    result_str = json.dumps(r['result'] if r['result'] is not None else {})[:6000]
                    lines.append(f"{c['name']} {json.dumps(c['args'])} -> {result_str}")
                    step_rec = {'tool': c['name'], 'arguments': c['args'], 'ok': r['ok'],
                                'resultPreview': result_str[:500], 'mode': 'text'}
                    if r['error']:
                        step_rec['error'] = r['error']
                    steps.append(step_rec)
                convo.append({
                    'role': 'user',
                    'content': 'Tool results (executed by the Jira server):\n' + '\n'.join(lines)
                    + '\n\nUsing these results, answer the original question. Call another tool only if necessary.',
                })
                continue
            if is_last_chance and text_calls:
                reply = ("I couldn't finish this request with the current model. "
                         "Please try again, or pick a model with native tool support in AI Settings.")
            else:
                reply = content
            break
    except ConnectorError as err:
        return _err(502, str(err), code=err.code)
    except Exception as err:
        return _err(500, str(err))

    return {'reply': reply or '', 'steps': steps,
            'ai': {'model': resolved_model, 'calls': calls, 'latencyMs': total_latency, 'usage': usage}}


@router.get('/tools')
def list_tools():
    return [{'type': 'function',
             'function': {'name': t['name'], 'description': t['description'],
                          'parameters': t['parameters']},
             'mutates': t['mutates']} for t in TOOLS]


@router.post('/tools/{name}')
def call_tool(name: str, request: Request, body: dict | None = None):
    expected = cfg.ai_tools_token()
    if expected:
        provided = request.headers.get('x-tools-token') or request.query_params.get('token')
        if not _token_ok(provided, expected):
            return _err(401, 'Invalid or missing tools token')
    tool = TOOL_BY_NAME.get(name)
    if not tool:
        return _err(404, f'Unknown tool {name}')
    acting = resolve_acting_user_id(request)
    if tool['mutates'] and not can_edit_issue(acting):
        return _err(403, 'Permission denied')
    try:
        result = tool['handler'](body or {}, {'userId': acting, 'projectId': None, 'via': 'http'})
        if isinstance(result, dict) and 'error' in result:
            rest = {k: v for k, v in result.items() if k != 'error'}
            return {'ok': False, 'error': result['error'], **rest}
        return result
    except Exception as err:
        return {'ok': False, 'error': str(err)}


@router.post('/connector/register-tools')
def register_tools(request: Request):
    acting = resolve_acting_user_id(request)
    if not can_configure_project(acting):
        return _err(403, 'Permission denied: Admin role required')
    try:
        return register_tools_with_connector()
    except ConnectorError as err:
        return _err(502, str(err), code=err.code)
    except Exception as err:
        return _err(500, str(err))


@router.get('/requests')
def list_requests(limit: int = 50):
    limit = min(max(int(limit or 50), 1), 200)
    return db.q('SELECT * FROM ai_requests ORDER BY created_at DESC, rowid DESC LIMIT ?', limit)


@router.post('/generate-story', status_code=201)
def generate_story_route(request: Request, body: dict):
    acting = resolve_acting_user_id(request)
    if not can_edit_issue(acting):
        return _err(403, 'Permission denied')

    project_id = body.get('projectId') or 'proj_cp'
    story_type = (body.get('storyType') or body.get('story_type') or 'coding').lower()
    prompt = (body.get('prompt') or '').strip()
    if not prompt:
        return _err(400, 'Prompt is required')
    difficulty = body.get('difficulty') or 'Medium'
    parent_id = body.get('parentId') or body.get('featureId')

    if story_type == 'coding':
        sys_prompt = (
            "You are an expert algorithms and competitive programming coach. "
            "Generate a coding problem story in JSON format with keys: "
            "'summary' (short problem title), 'description' (markdown problem statement including Input Format, Output Format, and Constraints), "
            "'sample_input_output' (list of objects each with 'input' and 'output' string properties), "
            "'hints' (list of 3-5 progressive algorithmic thinking steps), 'difficulty' ('Easy', 'Medium', or 'Hard'), "
            "'tags' (list of topic strings e.g. ['Array', 'DP']), 'story_points' (number between 1 and 8)."
        )
    elif story_type == 'learning':
        sys_prompt = (
            "You are an expert technical instructor in computer science and algorithms. "
            "Generate an in-depth learning story in JSON format with keys: "
            "'summary' (concept title), 'description' (comprehensive markdown tutorial with intuitive explanation, key concepts, algorithm walkthrough, and code examples), "
            "'hints' (list of 3-5 key takeaways / self-check questions), 'difficulty' ('Easy', 'Medium', or 'Hard'), "
            "'tags' (list of topic strings), 'story_points' (number between 1 and 5)."
        )
    else:
        story_type = 'non-coding'
        sys_prompt = (
            "You are a principal software architect and engineering leader. "
            "Generate a non-coding technical design or engineering task story in JSON format with keys: "
            "'summary' (concise task title), 'description' (markdown description with Background Context, Architecture / Functional Requirements, and Deliverables), "
            "'hints' (list of 3-5 key evaluation criteria / edge cases), 'difficulty' ('Easy', 'Medium', or 'Hard'), "
            "'tags' (list of topic strings), 'story_points' (number between 1 and 8)."
        )

    user_msg = f"Task Prompt: {prompt}\nTarget Difficulty: {difficulty}\nStory Type: {story_type}"
    parsed = None
    try:
        res = chat_completion([
            {'role': 'system', 'content': sys_prompt},
            {'role': 'user', 'content': user_msg},
        ])
        content = res.get('content') or ''
        clean = content.strip()
        if '```' in clean:
            parts = clean.split('```')
            for part in parts[1:]:
                txt = part.lstrip('json').strip()
                if txt.startswith('{') and txt.endswith('}'):
                    clean = txt
                    break
        clean = clean[clean.find('{'):clean.rfind('}')+1]
        parsed = json.loads(clean)
    except Exception:
        parsed = None

    if not parsed or not isinstance(parsed, dict) or not parsed.get('summary'):
        parsed = {
            'summary': f"{prompt[:60].capitalize()}",
            'description': (
                f"### Problem Overview\n{prompt}\n\n"
                f"### Requirements\nAnalyze and implement the solution adhering to optimal time and space complexity.\n\n"
                f"### Constraints\n- Standard input size up to 10^5\n- Time limit: 2.0s\n- Memory limit: 256MB"
            ) if story_type == 'coding' else (
                f"### Learning Guide: {prompt}\nComprehensive study notes and conceptual walkthrough for {prompt}.\n\n"
                f"### Objectives\n- Understand core mechanisms\n- Analyze time/space complexity tradeoffs\n- Review practical applications"
            ) if story_type == 'learning' else (
                f"### Architecture Task: {prompt}\nSystem design and requirements specification for {prompt}.\n\n"
                f"### Deliverables\n1. High-level architecture diagram and component responsibilities\n2. Data model and schema\n3. Scalability, caching, and resiliency analysis"
            ),
            'sample_input_output': [{'input': '5\n1 2 3 4 5', 'output': '15'}] if story_type == 'coding' else [],
            'hints': [
                f'Consider breaking down {prompt} into subproblems.',
                'Identify base cases and optimal data structures.',
                'Analyze the edge cases such as empty input or boundaries.',
            ],
            'difficulty': difficulty,
            'tags': [prompt.split()[0].capitalize() if prompt else 'Algorithms'],
            'story_points': 3 if difficulty == 'Easy' else 5 if difficulty == 'Medium' else 8,
        }

    summary = parsed.get('summary') or prompt
    description = parsed.get('description') or ''
    sample_io = parsed.get('sample_input_output') or []
    hints = parsed.get('hints') or []
    tags = parsed.get('tags') or []
    pts = parsed.get('story_points') or (3 if difficulty == 'Easy' else 5 if difficulty == 'Medium' else 8)

    created = create_issue({
        'projectId': project_id,
        'type': 'Story',
        'storyType': story_type,
        'summary': summary,
        'description': description,
        'difficulty': difficulty,
        'parentId': parent_id or None,
        'storyPoints': pts,
        'sampleIo': sample_io,
        'hints': hints,
        'tags': tags,
        'submissionStatus': 'Unsolved',
    }, acting)

    return created

