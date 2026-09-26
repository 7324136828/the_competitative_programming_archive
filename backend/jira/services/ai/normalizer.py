import re

_TYPE_MAP = {
    'story': 'Story', 'bug': 'Bug', 'task': 'Task', 'epic': 'Epic',
    'feature': 'Story', 'defect': 'Bug', 'incident': 'Bug',
}

_PRIORITY_MAP = {
    'critical': 'Highest', 'urgent': 'Highest', 'blocker': 'Highest', 'highest': 'Highest',
    'major': 'High', 'high': 'High',
    'medium': 'Medium',
    'minor': 'Low', 'low': 'Low',
    'trivial': 'Lowest', 'lowest': 'Lowest',
}


def normalize_ticket(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    summary = re.sub(r'\s+', ' ', str(raw.get('summary') or '')).strip()
    summary = re.sub(r'^[A-Z][A-Z0-9]{1,9}-\d+:\s*', '', summary)
    if len(summary) > 120:
        summary = summary[:117].rstrip() + '...'
    if not summary:
        return None

    ticket_type = _TYPE_MAP.get(str(raw.get('type') or '').lower(), 'Task')
    priority = _PRIORITY_MAP.get(str(raw.get('priority') or '').lower(), 'Medium')

    description = raw.get('description') if isinstance(raw.get('description'), str) else ''
    if len(description) > 20000:
        description = description[:20000]

    story_points = None
    sp = raw.get('storyPoints')
    try:
        spf = float(sp)
        if sp is not None and 0 <= spf <= 100:
            story_points = spf
    except (TypeError, ValueError):
        pass

    return {
        'type': ticket_type,
        'summary': summary,
        'description': description,
        'priority': priority,
        'storyPoints': story_points,
    }


def heuristic_draft(text: str) -> dict:
    first_line = next((l.strip() for l in text.split('\n') if l.strip()), 'Untitled report')
    summary = re.sub(r'\s+', ' ', first_line)
    if len(summary) > 120:
        cut = summary[:120]
        last_space = cut.rfind(' ')
        summary = (cut[:last_space] if last_space > 60 else cut).rstrip() + '...'

    ticket_type = 'Bug' if re.search(r'\b(error|exception|traceback|fail(ed|ure)?|crash|bug|panic|fatal|5\d\d)\b', text, re.IGNORECASE) else 'Task'
    priority = 'Medium'
    if re.search(r'\b(outage|down|data loss|security|sev ?1|p0|critical)\b', text, re.IGNORECASE):
        priority = 'Highest'
    elif re.search(r'\b(sev ?2|p1|urgent|high)\b', text, re.IGNORECASE):
        priority = 'High'

    return {
        'type': ticket_type,
        'summary': summary,
        'description': text[:20000],
        'priority': priority,
        'storyPoints': None,
    }
