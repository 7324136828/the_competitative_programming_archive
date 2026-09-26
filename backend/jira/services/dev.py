from ..db import db
from ..util import new_id


def get_linked_pull_requests(issue_id: str):
    return db.q('SELECT * FROM pull_requests WHERE issue_id = ? ORDER BY created_at DESC', issue_id)


def link_pull_request(issue_id: str, repo: str, pr_number: int, title: str, branch: str, status: str, url: str):
    pid = new_id('pr')
    db.run(
        """INSERT INTO pull_requests (id, issue_id, repo, pr_number, title, branch, status, url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        pid, issue_id, repo, pr_number, title, branch, status, url,
    )
    return {
        'id': pid, 'issueId': issue_id, 'repo': repo, 'prNumber': pr_number,
        'title': title, 'branch': branch, 'status': status, 'url': url,
    }


def update_pull_request_status(pr_id: str, status: str):
    db.run('UPDATE pull_requests SET status = ? WHERE id = ?', status, pr_id)
