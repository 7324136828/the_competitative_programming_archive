import json

from ..db import db, SQL_NOW
from ..util import new_id
from .users import get_default_user_id
from .history import record_status_change


def evaluate_condition(issue: dict, cond: dict) -> bool:
    val = str(issue.get(cond.get('field')) or '').lower()
    target = str(cond.get('value') or '').lower()
    op = cond.get('operator')
    if op == 'equals':
        return val == target
    if op == 'not_equals':
        return val != target
    if op == 'contains':
        return target in val
    return False


def run_automation_trigger(event_type: str, issue_id: str, project_id: str, actor_id=None):
    comment_author = actor_id or get_default_user_id()
    rules = db.q(
        """SELECT * FROM automation_rules
           WHERE trigger_event = ? AND (project_id = ? OR project_id IS NULL) AND is_enabled = 1""",
        event_type, project_id,
    )
    if not rules:
        return []
    issue = db.q1('SELECT * FROM issues WHERE id = ?', issue_id)
    if not issue:
        return []

    results = []
    for rule in rules:
        log_id = new_id('log')
        try:
            conditions = json.loads(rule['conditions_json'])
            actions = json.loads(rule['actions_json'])
            all_match = all(evaluate_condition(issue, c) for c in conditions)

            if all_match:
                for act in actions:
                    if act.get('action') == 'assign' and act.get('target'):
                        db.run(f'UPDATE issues SET assignee_id = ?, updated_at = {SQL_NOW} WHERE id = ?',
                               act['target'], issue_id)
                        issue['assignee_id'] = act['target']
                    elif act.get('action') == 'add_comment' and act.get('text'):
                        db.run('INSERT INTO comments (id, issue_id, author_id, body) VALUES (?, ?, ?, ?)',
                               new_id('c_auto'), issue_id, comment_author, act['text'])
                    elif act.get('action') == 'set_status' and act.get('target'):
                        previous = issue['status']
                        db.run(f'UPDATE issues SET status = ?, updated_at = {SQL_NOW} WHERE id = ?',
                               act['target'], issue_id)
                        issue['status'] = act['target']
                        record_status_change(issue_id, project_id, previous, act['target'],
                                             changed_by=actor_id, source='automation')
                details = f"Executed {len(actions)} action(s): {', '.join(a.get('action', '') for a in actions)}"
                db.run('INSERT INTO automation_logs (id, rule_id, issue_id, status, details) VALUES (?, ?, ?, ?, ?)',
                       log_id, rule['id'], issue_id, 'SUCCESS', details)
                results.append({'ruleId': rule['id'], 'status': 'SUCCESS', 'details': details})
            else:
                details = f"Conditions not met for issue {issue['key']}"
                db.run('INSERT INTO automation_logs (id, rule_id, issue_id, status, details) VALUES (?, ?, ?, ?, ?)',
                       log_id, rule['id'], issue_id, 'SKIPPED', details)
                results.append({'ruleId': rule['id'], 'status': 'SKIPPED', 'details': details})
        except Exception as err:
            details = f'Error executing rule: {err}'
            db.run('INSERT INTO automation_logs (id, rule_id, issue_id, status, details) VALUES (?, ?, ?, ?, ?)',
                   log_id, rule['id'], issue_id, 'FAILED', details)
            results.append({'ruleId': rule['id'], 'status': 'FAILED', 'details': details})
    return results


def get_automation_rules(project_id: str | None = None):
    if not project_id:
        return db.q('SELECT * FROM automation_rules ORDER BY created_at DESC')
    return db.q(
        'SELECT * FROM automation_rules WHERE project_id = ? OR project_id IS NULL ORDER BY created_at DESC',
        project_id,
    )


def get_automation_logs(project_id: str | None = None):
    if project_id:
        return db.q(
            """SELECT l.*, r.name as rule_name, i.key as issue_key
               FROM automation_logs l
               JOIN automation_rules r ON l.rule_id = r.id
               LEFT JOIN issues i ON l.issue_id = i.id
               WHERE r.project_id = ?
               ORDER BY l.executed_at DESC LIMIT 100""",
            project_id,
        )
    return db.q(
        """SELECT l.*, r.name as rule_name, i.key as issue_key
           FROM automation_logs l
           JOIN automation_rules r ON l.rule_id = r.id
           LEFT JOIN issues i ON l.issue_id = i.id
           ORDER BY l.executed_at DESC LIMIT 100"""
    )
