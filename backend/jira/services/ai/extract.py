import re

from ...db import db

_STOPWORDS = set((
    'a an and are as at be been but by can could did do does for from had has have he her his how i if in into is it its '
    'me my no not of on or our she so that the their them then there these they this to was we were what when where which '
    'who will with you your it its am are was were been being have has had having do does did doing would should could '
    'ought shall will can may might must about above after again against all any because before below between both each '
    'few further here how just more most other over own same some such than too under until very once only out down off up '
    'now during while http https www com'
).split(' '))


def extract_links(text: str) -> dict:
    result = {
        'issueKeys': [], 'urls': [], 'pullRequests': [],
        'branches': [], 'filePaths': [], 'errorSignatures': [],
    }
    if not text:
        return result

    project_keys = {r['key'] for r in db.q('SELECT key FROM projects')}

    seen = set()
    for m in re.finditer(r'\b([A-Z][A-Z0-9]{1,9})-(\d+)\b', text):
        key = f'{m.group(1)}-{m.group(2)}'
        if m.group(1) in project_keys and key not in seen:
            seen.add(key)
            result['issueKeys'].append(key)

    for m in re.finditer(r'https?://[^\s<>"\'\)\]]+', text):
        u = re.sub(r'[.,;:!?]+$', '', m.group(0))
        if u not in result['urls']:
            result['urls'].append(u)
        pm = re.search(r'github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)', u, re.IGNORECASE)
        if pm:
            result['pullRequests'].append({'repo': f'github.com/{pm.group(1)}', 'number': int(pm.group(2)), 'url': u})
            continue
        pm = re.search(r'gitlab\.[^/]*/([\w.-]+/[\w.-]+)/merge_requests/(\d+)', u, re.IGNORECASE)
        if pm:
            result['pullRequests'].append({'repo': f'gitlab.com/{pm.group(1)}', 'number': int(pm.group(2)), 'url': u})
            continue
        pm = re.search(r'bitbucket\.[^/]*/([\w.-]+/[\w.-]+)/pull-requests/(\d+)', u, re.IGNORECASE)
        if pm:
            result['pullRequests'].append({'repo': f'bitbucket.org/{pm.group(1)}', 'number': int(pm.group(2)), 'url': u})

    for m in re.finditer(r'\b(?:feature|feat|fix|bugfix|hotfix|release|chore)/[\w.\-/]+', text):
        b = re.sub(r'[.,;:!?]+$', '', m.group(0))
        if b not in result['branches']:
            result['branches'].append(b)

    file_matches = []
    seen_f = set()
    for m in re.finditer(r'(?:[A-Za-z]:\\[\w.\-\\ ]+|[\w.\-/]+/[\w.\-/]+|\b[\w-]+\.[A-Za-z]{1,10}:\d+)\b', text):
        f = m.group(0)
        if re.match(r'^\d', f) and not re.search(r':\d+$', f):
            continue
        if not re.search(r'\.[A-Za-z]{1,10}(:\d+)?$', f):
            continue
        if f not in seen_f:
            seen_f.add(f)
            file_matches.append(f)
    result['filePaths'] = file_matches

    for m in re.finditer(r'\b[A-Z][A-Za-z0-9]*(?:Exception|Error)\b', text):
        if m.group(0) not in result['errorSignatures']:
            result['errorSignatures'].append(m.group(0))

    return result


def extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    out = []
    seen = set()

    def push(tok: str):
        t = tok.lower()
        if len(t) < 2:
            return
        if re.match(r'^\d+$', t) and len(t) < 3:
            return
        if t in _STOPWORDS or t in seen:
            return
        seen.add(t)
        out.append(t)

    for raw in re.split(r'[^\w]+|_', text, flags=re.UNICODE):
        if not raw:
            continue
        push(raw)
        parts = re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+', raw)
        if len(parts) > 1:
            for p in parts:
                push(p)
        if len(out) >= 24:
            break
    return out[:24]
