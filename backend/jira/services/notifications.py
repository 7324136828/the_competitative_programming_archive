from ..db import db
from ..util import new_id


def notify_watchers(issue_id: str, title: str, message: str, exclude_user_id: str | None = None):
    watchers = db.q('SELECT user_id FROM watchers WHERE issue_id = ?', issue_id)
    for w in watchers:
        if exclude_user_id and w['user_id'] == exclude_user_id:
            continue
        db.run(
            'INSERT INTO notifications (id, user_id, title, message, issue_id) VALUES (?, ?, ?, ?, ?)',
            new_id('notif'), w['user_id'], title, message, issue_id,
        )


def get_user_notifications(user_id: str):
    return db.q(
        """SELECT n.*, i.key as issue_key
           FROM notifications n
           LEFT JOIN issues i ON n.issue_id = i.id
           WHERE n.user_id = ?
           ORDER BY n.created_at DESC
           LIMIT 50""",
        user_id,
    )


def mark_notification_read(notif_id: str):
    db.run('UPDATE notifications SET is_read = 1 WHERE id = ?', notif_id)
