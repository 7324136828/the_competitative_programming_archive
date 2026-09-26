import re

from ...db import db
from ..history import get_status_category
from .extract import extract_links, extract_keywords

PRIORITY_RANK = {'Highest': 0, 'High': 1, 'Medium': 2, 'Low': 3, 'Lowest': 4}
PRIORITY_BOOST = {'Highest': 15, 'High': 10, 'Medium': 5, 'Low': 2, 'Lowest': 0}


def _escape_like(s: str) -> str:
    return re.sub(r'[\\%_]', lambda m: '\\' + m.group(0), s)


def rank_tickets(query: str, mode: str, project_id=None, limit=10, include_done=False):
    limit = min(max(limit or 10, 1), 50)
    extracted = extract_links(query)
    terms = extract_keywords(query)

    scores: dict[str, dict] = {}

    def entry(iid):
        return scores.setdefault(iid, {'keyword': 0.0, 'link': 0.0, 'reasons': [], 'matchedLinks': []})

    # 1) FTS keyword search (restricted to project when given)
    if terms:
        match = ' OR '.join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in terms)
        sql = """
            SELECT f.issue_id, bm25(issues_fts, 0.0, 3.0, 10.0, 4.0, 1.5) as rank
            FROM issues_fts f
            JOIN issues i ON i.id = f.issue_id
            WHERE issues_fts MATCH ?
        """
        params = [match]
        if project_id:
            sql += ' AND i.project_id = ?'
            params.append(project_id)
        sql += ' ORDER BY rank ASC LIMIT 50'
        try:
            rows = db.q(sql, *params)
            mx = max((-r['rank'] for r in rows), default=0)
            for r in rows:
                entry(r['issue_id'])['keyword'] = (-r['rank'] / mx) if mx > 0 else 0
        except Exception:
            pass

    # 2) Link-based scoring
    mentioned = {}
    for key in extracted['issueKeys']:
        issue = db.q1('SELECT id, key FROM issues WHERE key = ?', key)
        if issue:
            mentioned[issue['id']] = key
            e = entry(issue['id'])
            e['link'] += 100
            e['reasons'].append(f'Mentioned directly ({key})')
            e['matchedLinks'].append({'kind': 'issue', 'value': key})

    for iid, key in mentioned.items():
        if project_id:
            linked = db.q(
                """SELECT DISTINCT issue_id FROM (
                     SELECT l.source_id as issue_id FROM issue_links l JOIN issues i ON i.id = l.source_id
                     WHERE l.target_id = ? AND i.project_id = ?
                     UNION
                     SELECT l.target_id FROM issue_links l JOIN issues i ON i.id = l.target_id
                     WHERE l.source_id = ? AND i.project_id = ?
                   )""",
                iid, project_id, iid, project_id,
            )
        else:
            linked = db.q(
                """SELECT DISTINCT issue_id FROM (
                     SELECT l.source_id as issue_id FROM issue_links l WHERE l.target_id = ?
                     UNION
                     SELECT l.target_id FROM issue_links l WHERE l.source_id = ?
                   )""",
                iid, iid,
            )
        for l in linked:
            if l['issue_id'] == iid:
                continue
            e = entry(l['issue_id'])
            if not any(m['kind'] == 'issue' and m['value'] == key for m in e['matchedLinks']):
                e['link'] += 20
                e['reasons'].append(f'Linked to {key}')
                e['matchedLinks'].append({'kind': 'issue', 'value': key})

    for pr in extracted['pullRequests'][:10]:
        owner_repo = '/'.join(pr['repo'].split('/')[-2:]).lower()
        sql = """
            SELECT p.issue_id, p.repo, p.pr_number FROM pull_requests p
            JOIN issues i ON i.id = p.issue_id
            WHERE (lower(p.url) = ? OR (p.pr_number = ? AND lower(p.repo) LIKE ?))
        """
        params = [pr['url'].lower(), pr['number'], f'%{_escape_like(owner_repo)}']
        if project_id:
            sql += ' AND i.project_id = ?'
            params.append(project_id)
        for row in db.q(sql, *params):
            e = entry(row['issue_id'])
            e['link'] += 80
            e['reasons'].append(f"Linked pull request {row['repo']}#{row['pr_number']}")
            e['matchedLinks'].append({'kind': 'pr', 'value': f"{row['repo']}#{row['pr_number']}"})

    for branch in extracted['branches'][:10]:
        sql = """SELECT p.issue_id FROM pull_requests p JOIN issues i ON i.id = p.issue_id
                 WHERE p.branch = ?"""
        params = [branch]
        if project_id:
            sql += ' AND i.project_id = ?'
            params.append(project_id)
        for row in db.q(sql, *params):
            e = entry(row['issue_id'])
            e['link'] += 60
            e['reasons'].append(f'Linked branch {branch}')
            e['matchedLinks'].append({'kind': 'branch', 'value': branch})

    for u in extracted['urls'][:10]:
        stripped = re.sub(r'^https?://', '', u)
        if len(stripped) < 6:
            continue
        like = f'%{_escape_like(stripped)}%'
        sql = """
            SELECT DISTINCT i.id FROM issues i
            WHERE (i.description LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\'
              OR EXISTS (SELECT 1 FROM comments c WHERE c.issue_id = i.id AND c.body LIKE ? ESCAPE '\\'))
        """
        params = [like, like, like]
        if project_id:
            sql += ' AND i.project_id = ?'
            params.append(project_id)
        for row in db.q(sql, *params):
            e = entry(row['id'])
            e['link'] += 50
            e['reasons'].append('URL referenced in ticket')
            e['matchedLinks'].append({'kind': 'url', 'value': u})

    for f in extracted['filePaths'][:10]:
        basename = re.sub(r':\d+$', '', f).split('/')[-1].split('\\')[-1]
        if len(basename) < 4:
            continue
        like = f'%{_escape_like(basename)}%'
        sql = """
            SELECT DISTINCT i.id FROM issues i
            WHERE (i.description LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\'
              OR EXISTS (SELECT 1 FROM comments c WHERE c.issue_id = i.id AND c.body LIKE ? ESCAPE '\\')
              OR EXISTS (SELECT 1 FROM attachments a WHERE a.issue_id = i.id AND a.original_name LIKE ? ESCAPE '\\'))
        """
        params = [like, like, like, like]
        if project_id:
            sql += ' AND i.project_id = ?'
            params.append(project_id)
        for row in db.q(sql, *params):
            e = entry(row['id'])
            e['link'] += 25
            e['reasons'].append(f'File referenced: {basename}')
            e['matchedLinks'].append({'kind': 'file', 'value': basename})

    for sig in extracted['errorSignatures'][:10]:
        like = f'%{_escape_like(sig)}%'
        sql = """SELECT id FROM issues
                 WHERE (summary LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"""
        params = [like, like]
        if project_id:
            sql += ' AND project_id = ?'
            params.append(project_id)
        for row in db.q(sql, *params):
            e = entry(row['id'])
            e['link'] += 15
            e['reasons'].append(f'Same error signature {sig}')
            e['matchedLinks'].append({'kind': 'error', 'value': sig})

    # 3) Combine
    scored_ids = [iid for iid, e in scores.items() if e['keyword'] > 0 or min(e['link'], 100) > 0]
    issue_rows = db.q(
        f"SELECT * FROM issues WHERE id IN ({','.join('?' * len(scored_ids))})", *scored_ids
    ) if scored_ids else []
    issue_by_id = {i['id']: i for i in issue_rows}

    active_sprint_issues = {
        r['id'] for r in db.q(
            "SELECT i.id FROM issues i JOIN sprints s ON i.sprint_id = s.id WHERE s.state = 'active'")
    }

    def open_blocked(source_id: str) -> int:
        rows = db.q(
            """SELECT t.id, t.status, t.project_id FROM issue_links l
               JOIN issues t ON l.target_id = t.id
               WHERE l.source_id = ? AND l.link_type = 'blocks'""",
            source_id,
        )
        return sum(1 for r in rows if get_status_category(r['project_id'], r['status']) != 'DONE')

    results = []
    for iid, e in scores.items():
        issue = issue_by_id.get(iid)
        if not issue:
            continue
        comments = db.q1(
            "SELECT COALESCE(group_concat(body, ' '), '') as b FROM comments WHERE issue_id = ?", iid)
        haystack = f"{issue['summary']} {issue.get('description') or ''} {comments['b'] if comments else ''}".lower()
        matched_terms = [t for t in terms if t in haystack]

        link_score = min(e['link'], 100)
        coverage = min(1, len(matched_terms) / min(len(terms), 6)) if terms else 0
        keyword_score = 60 * e['keyword'] * coverage
        score = keyword_score + link_score
        if score <= 0:
            continue

        category = get_status_category(issue['project_id'], issue['status'])
        reasons = list(e['reasons'])

        if mode == 'fix':
            if category == 'DONE':
                if not include_done:
                    continue
                score *= 0.5
                reasons.append('Already done - possible regression')
            pb = PRIORITY_BOOST.get(issue['priority'], 0)
            if pb > 0:
                score += pb
                reasons.append(f"{issue['priority']} priority")
            if issue['type'] == 'Bug':
                score += 8
                reasons.append('Bug')
            if iid in active_sprint_issues:
                score += 5
                reasons.append('In active sprint')
            n_blocked = open_blocked(iid)
            if n_blocked > 0:
                score += min(n_blocked * 4, 12)
                reasons.append(f"Blocks {n_blocked} open ticket{'s' if n_blocked != 1 else ''}")

        if matched_terms:
            reasons.insert(0, f"Keyword match: {', '.join(matched_terms)}")

        assignee = db.q1('SELECT name FROM users WHERE id = ?', issue['assignee_id'])['name'] \
            if issue['assignee_id'] else None
        sprint_name = db.q1('SELECT name FROM sprints WHERE id = ?', issue['sprint_id'])['name'] \
            if issue['sprint_id'] else None

        results.append({
            'id': issue['id'],
            'key': issue['key'],
            'summary': issue['summary'],
            'type': issue['type'],
            'status': issue['status'],
            'statusCategory': category,
            'priority': issue['priority'],
            'assigneeName': assignee,
            'sprintName': sprint_name,
            'score': round(score * 10) / 10,
            'matchedTerms': matched_terms,
            'matchedLinks': e['matchedLinks'],
            'reasons': reasons,
            '_rank': issue['rank'],
            '_projectId': issue['project_id'],
        })

    results.sort(key=lambda r: (
        -r['score'],
        PRIORITY_RANK.get(r['priority'], 9),
        r['_rank'],
    ))

    limited = [{k: v for k, v in r.items() if not k.startswith('_')} for r in results[:limit]]
    return {'extracted': extracted, 'results': limited}
