-- Jira Clone SQLite Database Schema

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  avatar TEXT,
  role TEXT NOT NULL DEFAULT 'Member' -- 'Admin', 'Member', 'Viewer'
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  lead_id TEXT REFERENCES users(id),
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sprints (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  goal TEXT,
  start_date TEXT,
  end_date TEXT,
  state TEXT NOT NULL DEFAULT 'planned', -- 'planned', 'active', 'closed'
  started_at TEXT,
  completed_at TEXT,
  committed_points REAL,
  committed_issue_count INTEGER,
  completed_points REAL,
  completed_issue_count INTEGER,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS versions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  description TEXT,
  release_date TEXT,
  status TEXT NOT NULL DEFAULT 'unreleased' -- 'unreleased', 'released', 'archived'
);

CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  is_default INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS workflow_statuses (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  name TEXT NOT NULL,
  category TEXT NOT NULL, -- 'TODO', 'IN_PROGRESS', 'DONE'
  position INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workflow_transitions (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
  id TEXT PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  project_id TEXT NOT NULL REFERENCES projects(id),
  type TEXT NOT NULL DEFAULT 'Story', -- 'Epic', 'Feature', 'Story', 'Bug', 'Task', 'Subtask'
  story_type TEXT DEFAULT 'coding', -- 'coding', 'learning', 'non-coding'
  summary TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'To Do',
  priority TEXT NOT NULL DEFAULT 'Medium', -- 'Lowest', 'Low', 'Medium', 'High', 'Highest'
  difficulty TEXT DEFAULT 'Medium', -- 'Easy', 'Medium', 'Hard'
  assignee_id TEXT REFERENCES users(id),
  reporter_id TEXT REFERENCES users(id),
  parent_id TEXT REFERENCES issues(id),
  sprint_id TEXT REFERENCES sprints(id),
  version_id TEXT REFERENCES versions(id),
  rank REAL NOT NULL DEFAULT 0,
  story_points REAL,
  start_date TEXT,
  due_date TEXT,
  original_estimate_minutes INTEGER DEFAULT 0,
  remaining_estimate_minutes INTEGER DEFAULT 0,
  problem_id INTEGER,
  sample_io_json TEXT DEFAULT '[]',
  hints_json TEXT DEFAULT '[]',
  tags_json TEXT DEFAULT '[]',
  submission_status TEXT DEFAULT 'Unsolved',
  study_set_id TEXT,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);


CREATE TABLE IF NOT EXISTS issue_status_history (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status TEXT NOT NULL,
  from_category TEXT,
  to_category TEXT NOT NULL,
  changed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  source TEXT NOT NULL DEFAULT 'user', -- 'user', 'ai', 'automation', 'system'
  changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_issue_status_history_issue ON issue_status_history(issue_id, changed_at);

CREATE TABLE IF NOT EXISTS sprint_issue_events (
  id TEXT PRIMARY KEY,
  sprint_id TEXT NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  event TEXT NOT NULL, -- 'committed', 'added', 'removed', 'completed', 'carried_over'
  story_points REAL,
  status TEXT,
  changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sprint_issue_events_sprint ON sprint_issue_events(sprint_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_sprint_issue_events_issue ON sprint_issue_events(issue_id);

CREATE TABLE IF NOT EXISTS issue_links (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  target_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  link_type TEXT NOT NULL, -- 'blocks', 'relates_to', 'duplicates'
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  original_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  uploaded_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS worklogs (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES users(id),
  time_spent_minutes INTEGER NOT NULL,
  description TEXT,
  started_at TEXT NOT NULL,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS watchers (
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (issue_id, user_id)
);

CREATE TABLE IF NOT EXISTS custom_fields (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  field_type TEXT NOT NULL, -- 'text', 'select', 'number', 'date', 'checkbox'
  options_json TEXT,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS custom_field_values (
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  field_id TEXT NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
  value TEXT,
  PRIMARY KEY (issue_id, field_id)
);

CREATE TABLE IF NOT EXISTS automation_rules (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  name TEXT NOT NULL,
  trigger_event TEXT NOT NULL, -- 'ISSUE_CREATED', 'STATUS_CHANGED', 'ASSIGNED'
  conditions_json TEXT NOT NULL,
  actions_json TEXT NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS automation_logs (
  id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
  issue_id TEXT REFERENCES issues(id) ON DELETE SET NULL,
  status TEXT NOT NULL, -- 'SUCCESS', 'FAILED', 'SKIPPED'
  details TEXT,
  executed_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS pull_requests (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  repo TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  branch TEXT NOT NULL,
  status TEXT NOT NULL, -- 'OPEN', 'MERGED', 'CLOSED'
  url TEXT NOT NULL,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS saved_filters (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  query_json TEXT NOT NULL,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  issue_id TEXT REFERENCES issues(id) ON DELETE SET NULL,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sprint_snapshots (
  id TEXT PRIMARY KEY,
  sprint_id TEXT NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  remaining_points REAL NOT NULL,
  ideal_points REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_requests (
  id TEXT PRIMARY KEY,
  feature TEXT NOT NULL,
  model TEXT,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  status TEXT NOT NULL,
  latency_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_tokens INTEGER,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_ticket_links (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  ai_request_id TEXT REFERENCES ai_requests(id) ON DELETE SET NULL,
  action TEXT NOT NULL, -- 'created', 'commented'
  source TEXT, -- 'draft', 'intake', 'assistant', 'tool'
  input_excerpt TEXT,
  created_at TEXT NOT NULL
);

-- User activity audit trail; optionally mirrored to The Connector activity session
CREATE TABLE IF NOT EXISTS activity_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  user_name TEXT,
  user_role TEXT,
  method TEXT NOT NULL, -- HTTP verb, or 'UI' for client-side beacons
  path TEXT NOT NULL,
  status_code INTEGER,
  duration_ms INTEGER,
  summary TEXT,
  detail TEXT, -- small JSON excerpt (query/body/beacon payload)
  forwarded INTEGER NOT NULL DEFAULT 0, -- 0 not forwarded, 1 sent to connector, -1 forward failed
  forward_error TEXT,
  created_at TEXT NOT NULL
);

-- Indexes on hot foreign-key columns
CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_sprint ON issues(sprint_id);
CREATE INDEX IF NOT EXISTS idx_issues_assignee ON issues(assignee_id);
CREATE INDEX IF NOT EXISTS idx_issues_parent ON issues(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_issue ON comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_worklogs_issue ON worklogs(issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_links_source ON issue_links(source_id);
CREATE INDEX IF NOT EXISTS idx_issue_links_target ON issue_links(target_id);
CREATE INDEX IF NOT EXISTS idx_pull_requests_issue ON pull_requests(issue_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at);

-- Full-text search over issues + comments
CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
  issue_id UNINDEXED,
  key,
  summary,
  description,
  comments,
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS issues_fts_insert AFTER INSERT ON issues BEGIN
  INSERT INTO issues_fts (issue_id, key, summary, description, comments)
  VALUES (new.id, new.key, new.summary, COALESCE(new.description, ''), '');
END;

CREATE TRIGGER IF NOT EXISTS issues_fts_update AFTER UPDATE OF key, summary, description ON issues BEGIN
  UPDATE issues_fts SET key = new.key, summary = new.summary, description = COALESCE(new.description, '')
  WHERE issue_id = new.id;
END;

CREATE TRIGGER IF NOT EXISTS issues_fts_delete AFTER DELETE ON issues BEGIN
  DELETE FROM issues_fts WHERE issue_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS issues_fts_comment_insert AFTER INSERT ON comments BEGIN
  UPDATE issues_fts SET comments = (
    SELECT COALESCE(group_concat(body, ' '), '') FROM comments WHERE issue_id = new.issue_id
  ) WHERE issue_id = new.issue_id;
END;

CREATE TRIGGER IF NOT EXISTS issues_fts_comment_delete AFTER DELETE ON comments BEGIN
  UPDATE issues_fts SET comments = (
    SELECT COALESCE(group_concat(body, ' '), '') FROM comments WHERE issue_id = old.issue_id
  ) WHERE issue_id = old.issue_id;
END;

CREATE VIEW IF NOT EXISTS issue_status_categories AS
SELECT i.id AS issue_id,
       COALESCE(
         (SELECT ws.category
          FROM workflow_statuses ws
          JOIN workflows w ON ws.workflow_id = w.id
          WHERE w.project_id = i.project_id AND ws.name = i.status
          ORDER BY w.is_default DESC
          LIMIT 1),
         CASE i.status
           WHEN 'Done' THEN 'DONE'
           WHEN 'To Do' THEN 'TODO'
           ELSE 'IN_PROGRESS'
         END
       ) AS category
FROM issues i;
