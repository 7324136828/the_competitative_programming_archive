from ..db import db


def get_project_dashboard_metrics(project_id: str):
    status_counts = db.q(
        'SELECT status, COUNT(*) as count FROM issues WHERE project_id = ? GROUP BY status', project_id)
    priority_counts = db.q(
        'SELECT priority, COUNT(*) as count FROM issues WHERE project_id = ? GROUP BY priority', project_id)
    assignee_workload = db.q(
        """SELECT u.id, u.name, u.avatar, COUNT(i.id) as issue_count, SUM(COALESCE(i.story_points, 0)) as total_points
           FROM users u
           LEFT JOIN issues i ON u.id = i.assignee_id AND i.project_id = ?
             AND (SELECT sc.category FROM issue_status_categories sc WHERE sc.issue_id = i.id) != 'DONE'
           GROUP BY u.id, u.name, u.avatar
           HAVING issue_count > 0""",
        project_id,
    )
    type_counts = db.q(
        'SELECT type, COUNT(*) as count FROM issues WHERE project_id = ? GROUP BY type', project_id)
    recent_comments = db.q(
        """SELECT c.id, c.body, c.created_at, u.name as author_name, u.avatar as author_avatar,
                  i.key as issue_key, i.summary as issue_summary
           FROM comments c
           JOIN users u ON c.author_id = u.id
           JOIN issues i ON c.issue_id = i.id
           WHERE i.project_id = ?
           ORDER BY c.created_at DESC LIMIT 5""",
        project_id,
    )
    return {
        'statusCounts': status_counts,
        'priorityCounts': priority_counts,
        'assigneeWorkload': assignee_workload,
        'typeCounts': type_counts,
        'recentComments': recent_comments,
    }
