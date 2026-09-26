import json

from ...db import db
from ...util import new_id
from ...config import ai_max_input_chars, ai_enabled
from .client import chat_completion, ConnectorError, resolve_model
from .json_util import parse_json_object
from .normalizer import normalize_ticket, heuristic_draft
from .extract import extract_links
from .search import rank_tickets
from .prompts import DRAFT_SYSTEM, DRAFT_USER, INTAKE_SYSTEM, INTAKE_USER, RECOMMEND_SYSTEM, RECOMMEND_USER
from .tools import record_ticket_link
from ..issues import create_issue, add_comment, get_issue_by_id
from ..history import get_status_category

SIMILAR_MIN_SCORE = 20


class AiUnavailable(Exception):
    def __init__(self):
        super().__init__('AI features are disabled')


def _fill(template: str, **vars) -> str:
    for k, v in vars.items():
        template = template.replace('{' + k + '}', v)
    return template


def call_json_feature(feature: str, system: str, user: str, model: str,
                      user_id=None, project_id=None, validate=None) -> dict:
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]
    retried = False
    for attempt in range(2):
        res = chat_completion(model, messages, feature=feature, user_id=user_id, project_id=project_id)
        content = res['message'].get('content') or ''
        try:
            parsed = parse_json_object(content)
            if validate:
                problem = validate(parsed)
                if problem:
                    raise ValueError(problem)
            return {'parsed': parsed, 'result': res, 'retried': retried}
        except Exception:
            if attempt == 0:
                retried = True
                messages.append(res['message'])
                messages.append({'role': 'user', 'content': 'Your previous reply was not valid JSON matching the required shape. Reply again with ONLY the JSON object.'})
                continue
            raise ValueError('AI returned invalid JSON')
    raise ValueError('AI returned invalid JSON')


def _project_or_404(project_id: str) -> dict:
    p = db.q1('SELECT * FROM projects WHERE id = ? OR key = ?', project_id, project_id)
    if not p:
        raise LookupError('Project not found')
    return p


def _append_references(description: str, text: str) -> str:
    extracted = extract_links(text)
    missing = []
    desc_lower = description.lower()
    for u in extracted['urls']:
        if u.lower() not in desc_lower:
            missing.append(u)
    for k in extracted['issueKeys']:
        if k not in description:
            missing.append(k)
    if not missing:
        return description
    sep = '' if description.endswith('\n') else '\n'
    return description + sep + '\nReferences:\n' + '\n'.join(f'- {m}' for m in missing)


def draft_tickets(text: str, project_id: str, max_tickets: int, request_model=None, user_id=None) -> dict:
    project = _project_or_404(project_id)
    resolved = resolve_model(request_model)
    model, model_source = resolved['model'], resolved['modelSource']
    clipped = text[:ai_max_input_chars()]

    ai = {'used': False, 'model': model, 'modelSource': model_source, 'latencyMs': None, 'error': None}
    drafts = []

    if ai_enabled():
        try:
            system = _fill(DRAFT_SYSTEM, maxTickets=str(max_tickets))
            user = _fill(DRAFT_USER, projectKey=project['key'], projectName=project['name'], text=clipped)
            out = call_json_feature(
                'draft', system, user, model, user_id=user_id, project_id=project['id'],
                validate=lambda p: None if any(
                    normalize_ticket(t) for t in (p.get('tickets') if isinstance(p, dict) else []) or []
                ) else 'expected at least one normalizable ticket',
            )
            ai['used'] = True
            ai['latencyMs'] = out['result']['latencyMs']
            raw = out['parsed'].get('tickets') if isinstance(out['parsed'], dict) else []
            drafts = [t for t in (normalize_ticket(t) for t in (raw or [])) if t][:max_tickets]
            if not drafts:
                raise ValueError('AI returned no usable tickets')
        except Exception as err:
            ai['error'] = str(err)
            ai['used'] = False
            drafts = [heuristic_draft(text)]
    else:
        ai['error'] = 'AI disabled'
        drafts = [heuristic_draft(text)]

    for d in drafts:
        d['description'] = _append_references(d['description'], text)
        d['similar'] = [r for r in rank_tickets(
            f"{d['summary']}\n{d['description']}", 'similar',
            project_id=project['id'], limit=3, include_done=True,
        )['results'] if r['score'] >= SIMILAR_MIN_SCORE]

    return {'drafts': drafts, 'extracted': extract_links(text), 'ai': ai}


def _find_description(issue_id: str) -> str:
    row = db.q1('SELECT description FROM issues WHERE id = ?', issue_id)
    return (row or {}).get('description') or ''


def recommend_tickets(query: str, project_id=None, limit=5, include_done=False,
                      use_ai=True, request_model=None, user_id=None) -> dict:
    ranked = rank_tickets(query, 'fix', project_id=project_id,
                          limit=max(limit, 10), include_done=include_done)
    resolved = resolve_model(request_model)
    model, model_source = resolved['model'], resolved['modelSource']
    ai = {'used': False, 'model': model, 'modelSource': model_source,
          'suggestion': None, 'latencyMs': None, 'error': None}
    results = ranked['results']

    if use_ai and ai_enabled() and results:
        candidates = results[:10]
        candidate_lines = '\n'.join(json.dumps({
            'key': c['key'], 'summary': c['summary'], 'type': c['type'], 'status': c['status'],
            'priority': c['priority'], 'score': c['score'], 'reasons': c['reasons'],
            'description': str(_find_description(c['id']))[:400],
        }) for c in candidates)
        try:
            out = call_json_feature(
                'recommend', RECOMMEND_SYSTEM,
                _fill(RECOMMEND_USER, query=query[:ai_max_input_chars()], candidates=candidate_lines),
                model, user_id=user_id, project_id=project_id,
                validate=lambda p: None if isinstance(p, dict) and isinstance(p.get('ranking'), list)
                else 'expected a ranking array',
            )
            ai['used'] = True
            ai['latencyMs'] = out['result']['latencyMs']
            parsed = out['parsed']
            ai['suggestion'] = parsed.get('suggestion') if isinstance(parsed.get('suggestion'), str) else None

            by_key = {r['key']: r for r in results}
            merged = []
            seen = set()
            for r in parsed.get('ranking', []):
                item = by_key.get(r.get('key') if isinstance(r, dict) else None)
                if item and item['key'] not in seen:
                    seen.add(item['key'])
                    conf = r.get('confidence')
                    merged.append({
                        **item,
                        'aiRationale': r.get('rationale') if isinstance(r.get('rationale'), str) else None,
                        'aiConfidence': max(0, min(1, conf)) if isinstance(conf, (int, float)) else None,
                    })
            for item in results:
                if item['key'] not in seen:
                    merged.append(item)
            results = merged
        except Exception as err:
            ai['error'] = str(err)
            ai['used'] = False

    return {'extracted': ranked['extracted'], 'results': results[:limit], 'ai': ai}


def intake_report(text: str, user_id: str, project_id=None, project_key=None,
                  source: str = 'webhook', dry_run=False, threshold=0.75,
                  sprint_id=None, request_model=None) -> dict:
    project = _project_or_404(project_id or project_key or '')
    resolved = resolve_model(request_model)
    model, model_source = resolved['model'], resolved['modelSource']
    clipped = text[:ai_max_input_chars()]

    candidates = rank_tickets(text, 'similar', project_id=project['id'], limit=5, include_done=True)['results']
    candidate_keys = {c['key'] for c in candidates}

    ai = {'used': False, 'model': model, 'modelSource': model_source, 'latencyMs': None, 'error': None}
    ticket = None
    duplicate_of = None
    ai_request_id = None

    if ai_enabled():
        candidate_lines = '\n'.join(json.dumps({
            'key': c['key'], 'summary': c['summary'], 'status': c['status'],
            'type': c['type'], 'priority': c['priority'],
            'description': str(_find_description(c['id']))[:300],
        }) for c in candidates) if candidates else '(none)'
        try:
            out = call_json_feature(
                'intake', INTAKE_SYSTEM,
                _fill(INTAKE_USER, projectKey=project['key'], projectName=project['name'],
                      source=source, text=clipped, candidates=candidate_lines),
                model, user_id=user_id, project_id=project['id'],
                validate=lambda p: None if isinstance(p, dict) and normalize_ticket(p.get('ticket'))
                else 'expected a normalizable ticket',
            )
            ai_request_id = out['result']['requestId']
            ai['used'] = True
            ai['latencyMs'] = out['result']['latencyMs']
            parsed = out['parsed']
            ticket = normalize_ticket(parsed.get('ticket')) or heuristic_draft(text)
            dup_key = parsed.get('duplicateOf') if isinstance(parsed.get('duplicateOf'), str) else None
            if dup_key not in candidate_keys:
                dup_key = None
            try:
                conf = float(parsed.get('duplicateConfidence'))
                if conf != conf:
                    conf = 0.0
            except (TypeError, ValueError):
                conf = 0.0
            conf = max(0.0, min(1.0, conf))
            if not dup_key:
                conf = 0.0
            duplicate_of = {'key': dup_key, 'confidence': conf,
                            'reason': parsed.get('duplicateReason') if isinstance(parsed.get('duplicateReason'), str) else None} \
                if dup_key else None
        except Exception as err:
            ai['error'] = str(err)
            ai['used'] = False
            ticket = heuristic_draft(text)
            duplicate_of = None
    else:
        ai['error'] = 'AI disabled'
        ticket = heuristic_draft(text)

    extracted = extract_links(text)
    dup_issue = db.q1('SELECT * FROM issues WHERE key = ?', duplicate_of['key']) if duplicate_of else None
    dup_is_done = bool(dup_issue) and get_status_category(dup_issue['project_id'], dup_issue['status']) == 'DONE'

    is_dup = bool(duplicate_of) and duplicate_of['confidence'] >= threshold and dup_issue
    if is_dup and not dup_is_done:
        action = 'would_comment' if dry_run else 'commented'
    elif is_dup and dup_is_done:
        action = 'would_create_regression' if dry_run else 'created_regression'
    else:
        action = 'would_create' if dry_run else 'created'

    issue = None
    if not dry_run:
        if action == 'commented':
            pct = round(duplicate_of['confidence'] * 100)
            reason_para = f"\n\n{duplicate_of['reason']}" if duplicate_of['reason'] else ''
            body = (f"[AI intake from {source}] New occurrence reported (duplicate confidence {pct}%)."
                    f"{reason_para}\n\n---\n{text[:4000]}")
            add_comment(dup_issue['id'], user_id, body)
            record_ticket_link(dup_issue['id'], 'commented', 'intake', text[:2000], ai_request_id)
            issue = get_issue_by_id(dup_issue['id'])
        else:
            description = ticket['description'] + (
                f"\n\nPossible regression of {duplicate_of['key']}." if action == 'created_regression' else '')

            def _work():
                new_issue = create_issue({
                    'projectId': project['id'],
                    'type': ticket['type'],
                    'summary': ticket['summary'],
                    'description': description,
                    'priority': ticket['priority'],
                    'storyPoints': ticket['storyPoints'],
                    'sprintId': sprint_id,
                }, user_id, source='ai')
                link_keys = set(extracted['issueKeys'])
                if duplicate_of:
                    link_keys.add(duplicate_of['key'])
                for key in link_keys:
                    target = db.q1('SELECT id FROM issues WHERE key = ?', key)
                    if not target or target['id'] == new_issue['id']:
                        continue
                    try:
                        db.run(
                            'INSERT INTO issue_links (id, source_id, target_id, link_type) VALUES (?, ?, ?, ?)',
                            new_id('link'), new_issue['id'], target['id'], 'relates_to',
                        )
                    except Exception:
                        pass
                record_ticket_link(new_issue['id'], 'created', 'intake', text[:2000], ai_request_id)
                return new_issue

            created = db.with_transaction(_work)
            issue = get_issue_by_id(created['id'])

    return {
        'action': action,
        'issue': issue,
        'duplicateOf': duplicate_of,
        'draft': ticket,
        'candidates': [{'key': c['key'], 'summary': c['summary'], 'status': c['status'], 'score': c['score']}
                       for c in candidates],
        'ai': ai,
    }
