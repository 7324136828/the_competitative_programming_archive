import json
from datetime import datetime, timedelta, timezone

from .db import db
from .util import now_iso
from .services.projects import create_project_with_default_workflow
from .util import generate_avatar

BOOTSTRAP_PROJECT_FLAG = 'bootstrap.default_project_created'
BOOTSTRAP_ADMIN_ID = 'u_admin'


def ensure_bootstrap_data():
    # Every workspace has one stable identity for the default local login,
    # even when imported or demo data already contains other administrators.
    local_admin = db.q1('SELECT id, role FROM users WHERE id = ?', BOOTSTRAP_ADMIN_ID)
    if local_admin:
        if local_admin['role'] != 'Admin':
            db.run('UPDATE users SET role = ? WHERE id = ?', 'Admin', BOOTSTRAP_ADMIN_ID)
    else:
        db.run(
            'INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)',
            BOOTSTRAP_ADMIN_ID, 'Admin', 'admin@localhost', generate_avatar('Admin'), 'Admin',
        )

    project_count = db.q1('SELECT COUNT(*) as c FROM projects')['c']
    flag = db.q1('SELECT value FROM app_settings WHERE key = ?', BOOTSTRAP_PROJECT_FLAG)
    if project_count == 0 and not flag:
        create_project_with_default_workflow(
            key='PROJ',
            name='My Project',
            description='Default project created on first start',
            lead_id=BOOTSTRAP_ADMIN_ID,
        )
        db.run(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, " + "strftime('%Y-%m-%dT%H:%M:%fZ','now')" + ")",
            BOOTSTRAP_PROJECT_FLAG, now_iso(),
        )


def seed_demo_data():
    if db.q1("SELECT id FROM projects WHERE id = 'proj_cp'"):
        return  # Demo data already seeded

    users = [
        ('u_alex', 'Alex Chen', 'alex@company.com', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces', 'Admin'),
        ('u_sarah', 'Sarah Connor', 'sarah@company.com', 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop&crop=faces', 'Member'),
        ('u_marcus', 'Marcus Vance', 'marcus@company.com', 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop&crop=faces', 'Member'),
        ('u_triage', 'Triage Lead', 'triage@company.com', 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100&h=100&fit=crop&crop=faces', 'Member'),
        ('u_guest', 'Guest Stakeholder', 'guest@company.com', 'https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=100&h=100&fit=crop&crop=faces', 'Viewer'),
    ]
    for u in users:
        db.run('INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)', *u)

    projects = [
        ('proj_cp', 'CP', 'Cloud Platform Core', 'Core backend infrastructure, authentication, microservices and APIs', 'u_alex'),
        ('proj_mob', 'MOB', 'Mobile App NextGen', 'iOS and Android client applications for next generation platform', 'u_sarah'),
    ]
    for p in projects:
        db.run('INSERT INTO projects (id, key, name, description, lead_id) VALUES (?, ?, ?, ?, ?)', *p)

    for wf_id, proj_id, name in (
        ('wf_cp', 'proj_cp', 'Cloud Core Software Workflow'),
        ('wf_mob', 'proj_mob', 'Mobile Agile Workflow'),
    ):
        db.run('INSERT INTO workflows (id, project_id, name, is_default) VALUES (?, ?, ?, ?)', wf_id, proj_id, name, 1)

    statuses = [
        ('To Do', 'TODO', 0), ('In Progress', 'IN_PROGRESS', 1),
        ('In Review', 'IN_PROGRESS', 2), ('Done', 'DONE', 3),
    ]
    for wf in ('wf_cp', 'wf_mob'):
        for name, cat, pos in statuses:
            db.run(
                'INSERT INTO workflow_statuses (id, workflow_id, name, category, position) VALUES (?, ?, ?, ?, ?)',
                f'{wf}_{name.replace(" ", "_").lower()}', wf, name, cat, pos,
            )

    transitions = [
        ('To Do', 'In Progress', 'Start Work'),
        ('In Progress', 'In Review', 'Submit for Review'),
        ('In Review', 'Done', 'Approve & Close'),
        ('In Review', 'In Progress', 'Request Changes'),
        ('In Progress', 'To Do', 'Stop Work'),
        ('Done', 'To Do', 'Reopen'),
    ]
    tr_id = 1
    for wf in ('wf_cp', 'wf_mob'):
        for fr, to, name in transitions:
            db.run(
                'INSERT INTO workflow_transitions (id, workflow_id, from_status, to_status, name) VALUES (?, ?, ?, ?, ?)',
                f'tr_{tr_id}', wf, fr, to, name,
            )
            tr_id += 1

    today = datetime.now(timezone.utc)
    start_7_ago = (today - timedelta(days=7)).date().isoformat()
    end_7_ahead = (today + timedelta(days=7)).date().isoformat()
    future_start = (today + timedelta(days=8)).date().isoformat()
    future_end = (today + timedelta(days=22)).date().isoformat()
    today_str = today.date().isoformat()

    sprints = [
        ('sprint_cp_1', 'proj_cp', 'Sprint 14 - Observability & Auth', 'Complete distributed tracing and OAuth integration', start_7_ago, end_7_ahead, 'active'),
        ('sprint_cp_2', 'proj_cp', 'Sprint 15 - Performance Optimization', 'P99 latency reduction below 50ms', future_start, future_end, 'planned'),
        ('sprint_mob_1', 'proj_mob', 'Sprint M1 - Core Shell', 'Deliver initial native navigation shell', start_7_ago, end_7_ahead, 'active'),
    ]
    for s in sprints:
        db.run('INSERT INTO sprints (id, project_id, name, goal, start_date, end_date, state) VALUES (?, ?, ?, ?, ?, ?, ?)', *s)

    versions = [
        ('ver_cp_1', 'proj_cp', 'v1.2.0 - Core Gateway', 'OAuth2, WebSocket enhancements, and metric aggregations', end_7_ahead, 'unreleased'),
        ('ver_cp_0', 'proj_cp', 'v1.1.0 - Multi-region support', 'Initial multi-cloud region routing', start_7_ago, 'released'),
        ('ver_mob_1', 'proj_mob', 'v1.0.0-beta', 'Initial beta release for internal testing', end_7_ahead, 'unreleased'),
    ]
    for v in versions:
        db.run('INSERT INTO versions (id, project_id, name, description, release_date, status) VALUES (?, ?, ?, ?, ?, ?)', *v)

    custom_fields = [
        ('cf_impact', 'proj_cp', 'Customer Impact', 'select', json.dumps(['Critical Enterprise', 'High', 'Standard SLA', 'Internal Only'])),
        ('cf_env', 'proj_cp', 'Target Environment', 'select', json.dumps(['Production', 'Staging', 'Dev'])),
        ('cf_device', 'proj_mob', 'Target Platform', 'select', json.dumps(['iOS', 'Android', 'Both'])),
    ]
    for cf in custom_fields:
        db.run('INSERT INTO custom_fields (id, project_id, name, field_type, options_json) VALUES (?, ?, ?, ?, ?)', *cf)

    db.run(
        """INSERT INTO automation_rules (id, project_id, name, trigger_event, conditions_json, actions_json, is_enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        'rule_high_bug_triage', 'proj_cp',
        'Auto-assign High Priority Bugs to Triage Lead',
        'ISSUE_CREATED',
        json.dumps([
            {'field': 'type', 'operator': 'equals', 'value': 'Bug'},
            {'field': 'priority', 'operator': 'equals', 'value': 'High'},
        ]),
        json.dumps([
            {'action': 'assign', 'target': 'u_triage'},
            {'action': 'add_comment', 'text': 'Automated triage: This high priority bug has been assigned to the triage lead.'},
        ]),
        1,
    )

    issues = [
        # id, key, project, type, summary, description, status, priority, assignee, reporter, parent, sprint, version, rank, pts, start, due, orig_est, remaining
        ('issue_cp_1', 'CP-1', 'proj_cp', 'Story', 'Implement OAuth2 OpenID Connect Integration', 'Build standard OpenID Connect discovery endpoints and JWT validation for third-party microservices.', 'In Review', 'High', 'u_alex', 'u_sarah', None, 'sprint_cp_1', 'ver_cp_1', 1.0, 8, start_7_ago, end_7_ahead, 480, 120),
        ('issue_cp_2', 'CP-2', 'proj_cp', 'Task', 'Configure Redis Cluster caching layer', 'Deploy Redis Sentinel / Cluster nodes with automatic failover and client pooling.', 'In Progress', 'Medium', 'u_marcus', 'u_alex', None, 'sprint_cp_1', 'ver_cp_1', 2.0, 5, start_7_ago, end_7_ahead, 300, 180),
        ('issue_cp_3', 'CP-3', 'proj_cp', 'Task', 'Expose Mobile Gateway GraphQL endpoints', 'Set up federation schema for mobile app clients and optimize N+1 queries.', 'In Progress', 'High', 'u_sarah', 'u_alex', None, 'sprint_cp_1', 'ver_cp_1', 3.0, 5, start_7_ago, end_7_ahead, 300, 120),
        ('issue_cp_4', 'CP-4', 'proj_cp', 'Bug', 'Memory spike under high throughput WebSocket streams', 'Node process leaks memory buffers when handling >10k concurrent SSE connections.', 'In Progress', 'High', 'u_triage', 'u_marcus', None, 'sprint_cp_1', 'ver_cp_1', 4.0, 3, start_7_ago, end_7_ahead, 240, 120),
        ('issue_cp_5', 'CP-5', 'proj_cp', 'Story', 'Add OpenTelemetry tracing exporters', 'Export distributed trace headers across gRPC and HTTP gateway handlers.', 'Done', 'Medium', 'u_alex', 'u_marcus', None, 'sprint_cp_1', 'ver_cp_1', 5.0, 5, start_7_ago, today_str, 300, 0),
        ('issue_cp_7', 'CP-7', 'proj_cp', 'Subtask', 'Add JWT validator middleware', 'Validate signature, expiration, and required scopes on incoming API requests.', 'Done', 'High', 'u_alex', 'u_alex', 'issue_cp_1', 'sprint_cp_1', None, 1.1, 3, start_7_ago, start_7_ago, 180, 0),
        ('issue_cp_8', 'CP-8', 'proj_cp', 'Subtask', 'Implement refresh token rotation', 'Store hashed refresh tokens in Redis with single-use invalidation.', 'In Review', 'High', 'u_alex', 'u_alex', 'issue_cp_1', 'sprint_cp_1', None, 1.2, 5, start_7_ago, end_7_ahead, 300, 60),
        ('issue_cp_9', 'CP-9', 'proj_cp', 'Story', 'Implement rate limiting middleware with sliding window', 'Protect public endpoints from abuse using Redis sliding log algorithm.', 'To Do', 'Medium', 'u_marcus', 'u_alex', None, None, None, 6.0, 5, future_start, future_end, 300, 300),
        ('issue_cp_10', 'CP-10', 'proj_cp', 'Bug', 'Session timeout banner does not dismiss on touch devices', 'UI backdrop captures tap event before close button receives click.', 'To Do', 'Low', None, 'u_guest', None, None, None, 7.0, 2, None, None, 120, 120),
        ('issue_cp_11', 'CP-11', 'proj_cp', 'Task', 'Upgrade Postgres read-replicas to v16', 'Perform zero-downtime rolling failover upgrade on analytics database replica.', 'To Do', 'High', 'u_marcus', 'u_alex', None, 'sprint_cp_2', None, 8.0, 8, future_start, future_end, 480, 480),
        ('issue_mob_1', 'MOB-1', 'proj_mob', 'Story', 'Consume Mobile Gateway GraphQL API', 'Integrate Apollo Client on iOS and Android to query user profile and task list.', 'In Progress', 'High', 'u_sarah', 'u_sarah', None, 'sprint_mob_1', 'ver_mob_1', 1.0, 5, start_7_ago, end_7_ahead, 300, 150),
        ('issue_mob_2', 'MOB-2', 'proj_mob', 'Bug', 'Push notification registration fails on iOS 18', 'APNs device token serialization format changed in iOS 18 developer beta.', 'To Do', 'High', 'u_sarah', 'u_guest', None, 'sprint_mob_1', 'ver_mob_1', 2.0, 3, start_7_ago, end_7_ahead, 180, 180),
    ]
    for i in issues:
        db.run(
            """INSERT INTO issues (id, key, project_id, type, summary, description, status, priority,
                 assignee_id, reporter_id, parent_id, sprint_id, version_id, rank, story_points,
                 start_date, due_date, original_estimate_minutes, remaining_estimate_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            *i,
        )

    # Competitive programming archive integration:
    # Epics (sets of problem sets created by user)
    # Features (problem sets)
    # Stories (coding, learning, non-coding)
    cp_entities = [
        # Epic: set of problem sets
        ('issue_epic_cp', 'CP-EPIC-1', 'proj_cp', 'Epic', None, 'Competitive Programming & Problem Solving Track',
         'User-defined epic encompassing core algorithmic problem sets, patterns, and interactive practice.',
         'In Progress', 'High', 'Medium', 'u_alex', 'u_alex', None, None, 'ver_cp_1', 0.05, 40,
         start_7_ago, end_7_ahead, '[]', '[]', '["Algorithms","Competitive Programming"]', None, 'In Progress'),

        # Features: Problem sets
        ('issue_feat_array', 'CP-FEAT-1', 'proj_cp', 'Feature', None, 'Problem Set: Arrays & Hashing',
         'Attributed problem set for array operations, prefix sums, and hash table mappings.',
         'In Progress', 'High', 'Medium', 'u_alex', 'u_alex', 'issue_epic_cp', None, 'ver_cp_1', 0.1, 16,
         start_7_ago, end_7_ahead, '[]', '[]', '["Array","Hash Table"]', None, 'In Progress'),

        ('issue_feat_pointers', 'CP-FEAT-2', 'proj_cp', 'Feature', None, 'Problem Set: Two Pointers & Sliding Window',
         'Attributed problem set for two-pointer traversals and dynamic sliding windows.',
         'To Do', 'Medium', 'Medium', 'u_sarah', 'u_alex', 'issue_epic_cp', None, 'ver_cp_1', 0.2, 13,
         future_start, future_end, '[]', '[]', '["Two Pointers","Sliding Window"]', None, 'Unsolved'),

        # Stories under Features:
        # Coding stories (every problem is a story)
        ('issue_cp_two_sum', 'CP-12', 'proj_cp', 'Story', 'coding', 'Two Sum',
         'Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\n### Input Format\n- First line: space-separated integers representing `nums`.\n- Second line: a single integer `target`.\n\n### Output Format\n- Space-separated 0-based indices of the two numbers.\n\n### Constraints\n- `2 <= nums.length <= 10^4`\n- `-10^9 <= nums[i] <= 10^9`\n- `-10^9 <= target <= 10^9`',
         'To Do', 'Medium', 'Easy', 'u_alex', 'u_alex', 'issue_feat_array', 'sprint_cp_1', 'ver_cp_1', 0.11, 3,
         start_7_ago, end_7_ahead,
         '[{"input":"2 7 11 15\\n9","output":"0 1"},{"input":"3 2 4\\n6","output":"1 2"},{"input":"3 3\\n6","output":"0 1"}]',
         '["A brute force approach checks all pairs in O(n^2).","Can you use a hash map to look up target - nums[i] in O(1)?","Iterate through the array and check if the complement exists in the map."]',
         '["Array","Hash Table"]', 1, 'Unsolved'),

        ('issue_cp_palindrome', 'CP-13', 'proj_cp', 'Story', 'coding', 'Palindrome Number',
         'Given an integer `x`, return `true` if `x` is a palindrome, and `false` otherwise.\n\nAn integer is a palindrome when it reads the same forward and backward.\n\n### Constraints\n- `-2^31 <= x <= 2^31 - 1`',
         'To Do', 'Medium', 'Easy', 'u_marcus', 'u_alex', 'issue_feat_pointers', 'sprint_cp_1', 'ver_cp_1', 0.21, 2,
         start_7_ago, end_7_ahead,
         '[{"input":"121","output":"true"},{"input":"-121","output":"false"},{"input":"10","output":"false"}]',
         '["Negative numbers cannot be palindromes.","Can you reverse half of the integer mathematically?"]',
         '["Math","Two Pointers"]', 2, 'Unsolved'),

        ('issue_cp_longest_sub', 'CP-14', 'proj_cp', 'Story', 'coding', 'Longest Substring Without Repeating Characters',
         'Given a string `s`, find the length of the longest substring without duplicate characters.\n\n### Constraints\n- `0 <= s.length <= 5 * 10^4`',
         'To Do', 'High', 'Medium', 'u_sarah', 'u_alex', 'issue_feat_pointers', 'sprint_cp_1', 'ver_cp_1', 0.22, 5,
         start_7_ago, end_7_ahead,
         '[{"input":"abcabcbb","output":"3"},{"input":"bbbbb","output":"1"},{"input":"pwwkew","output":"3"}]',
         '["Use a sliding window with two pointers left and right.","Maintain a set or lookup table of characters in the current window."] ',
         '["Sliding Window","Hash Table"]', 3, 'Unsolved'),

        # Learning story
        ('issue_cp_learn_pointers', 'CP-15', 'proj_cp', 'Story', 'learning', 'Mastering Two-Pointer & Sliding Window Paradigms',
         '### Overview\nThe two-pointer and sliding window techniques are essential patterns for reducing quadratic time complexity to linear time.\n\n### Key Concepts\n- Opposite Direction Pointers (Binary search, Palindromes, Two Sum II)\n- Equi-directional Pointers (Remove duplicates, Fast & Slow cycle detection)\n- Dynamic Sliding Window (Minimum window substring, longest substring with k distinct elements)\n\n### Self-Check Questions\n1. When does a sorted array guarantee a monotonic pointer move?\n2. What is the invariant condition for shrinking the left window boundary?',
         'To Do', 'Medium', 'Easy', 'u_alex', 'u_alex', 'issue_feat_pointers', 'sprint_cp_1', 'ver_cp_1', 0.23, 2,
         start_7_ago, end_7_ahead, '[]',
         '["Review the sliding window template code","Identify which condition causes left to increment"]',
         '["Learning","Tutorial"]', None, 'Unsolved'),

        # Non-coding story
        ('issue_cp_design_judge', 'CP-16', 'proj_cp', 'Story', 'non-coding', 'System Architecture: Real-Time Code Execution Engine',
         '### Requirements\nDesign a multi-language sandbox architecture for executing untrusted user code with deterministic time and memory enforcement.\n\n### Deliverables\n1. Isolation mechanism (Linux namespaces / cgroups vs Windows Job Objects)\n2. Security guardrails (seccomp, network isolation, filesystem chroot)\n3. Asynchronous compilation and evaluation worker queue architecture',
         'To Do', 'High', 'Hard', 'u_alex', 'u_alex', 'issue_feat_array', 'sprint_cp_1', 'ver_cp_1', 0.12, 8,
         start_7_ago, end_7_ahead, '[]',
         '["Evaluate tradeoffs between containerized execution and lightweight process wrappers","Consider how fast worker pools can be pre-warmed"]',
         '["Architecture","System Design"]', None, 'Unsolved'),
    ]
    for cp in cp_entities:
        db.run(
            """INSERT INTO issues (id, key, project_id, type, story_type, summary, description, status,
                 priority, difficulty, assignee_id, reporter_id, parent_id, sprint_id, version_id,
                 rank, story_points, start_date, due_date, sample_io_json, hints_json, tags_json,
                 problem_id, submission_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            *cp,
        )


    for link in (
        ('link_1', 'issue_cp_1', 'issue_cp_2', 'blocks'),
        ('link_2', 'issue_cp_3', 'issue_mob_1', 'blocks'),
    ):
        db.run('INSERT INTO issue_links (id, source_id, target_id, link_type) VALUES (?, ?, ?, ?)', *link)

    comments = [
        ('c_1', 'issue_cp_1', 'u_sarah', 'Checked the provider specs, looks solid. Are we supporting PKCE with SHA-256 for mobile clients?'),
        ('c_2', 'issue_cp_1', 'u_alex', 'Yes, PKCE with code_challenge_method=S256 is fully supported and mandatory for all native mobile apps.'),
        ('c_3', 'issue_cp_4', 'u_triage', 'Investigated the heap dump: Buffer.allocUnsafe was not being freed on client disconnection. Fix in review.'),
    ]
    for c in comments:
        db.run('INSERT INTO comments (id, issue_id, author_id, body) VALUES (?, ?, ?, ?)', *c)

    worklogs = [
        ('wl_1', 'issue_cp_1', 'u_alex', 180, 'Drafted discovery document endpoint and initial JWT validation logic', start_7_ago),
        ('wl_2', 'issue_cp_1', 'u_alex', 180, 'Configured JWKS public key rotation cache', today_str),
        ('wl_3', 'issue_cp_2', 'u_marcus', 120, 'Benchmarked Redis memory footprint and connection pooling', start_7_ago),
    ]
    for w in worklogs:
        db.run('INSERT INTO worklogs (id, issue_id, author_id, time_spent_minutes, description, started_at) VALUES (?, ?, ?, ?, ?, ?)', *w)

    for w in (('issue_cp_1', 'u_sarah'), ('issue_cp_1', 'u_guest'), ('issue_cp_4', 'u_alex')):
        db.run('INSERT INTO watchers (issue_id, user_id) VALUES (?, ?)', *w)

    for cv in (
        ('issue_cp_1', 'cf_impact', 'Critical Enterprise'),
        ('issue_cp_1', 'cf_env', 'Production'),
        ('issue_cp_4', 'cf_impact', 'High'),
        ('issue_cp_4', 'cf_env', 'Production'),
        ('issue_mob_1', 'cf_device', 'Both'),
    ):
        db.run('INSERT INTO custom_field_values (issue_id, field_id, value) VALUES (?, ?, ?)', *cv)

    prs = [
        ('pr_1', 'issue_cp_1', 'github.com/company/auth-service', 104, 'feat(auth): openid connect provider configuration', 'feat/oauth2-oidc', 'OPEN', 'https://github.com/company/auth-service/pull/104'),
        ('pr_2', 'issue_cp_5', 'github.com/company/core-gateway', 98, 'feat(telemetry): otel tracing integration', 'feat/tracing', 'MERGED', 'https://github.com/company/core-gateway/pull/98'),
    ]
    for p in prs:
        db.run('INSERT INTO pull_requests (id, issue_id, repo, pr_number, title, branch, status, url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', *p)

    filters = [
        ('filter_my_open', 'u_alex', 'My Open Issues', json.dumps({'assignee_id': 'u_alex', 'status_not': 'Done'})),
        ('filter_high_pri', 'u_alex', 'High Priority Bugs', json.dumps({'type': 'Bug', 'priority': 'High'})),
    ]
    for f in filters:
        db.run('INSERT INTO saved_filters (id, user_id, name, query_json) VALUES (?, ?, ?, ?)', *f)

    points = [
        (0, 26, 26), (1, 26, 24.1), (2, 26, 22.2), (3, 21, 20.3),
        (4, 21, 18.5), (5, 16, 16.6), (6, 13, 14.7), (7, 13, 12.8),
    ]
    for day, remaining, ideal in points:
        d = (datetime.fromisoformat(start_7_ago) + timedelta(days=day)).date().isoformat()
        db.run(
            'INSERT INTO sprint_snapshots (id, sprint_id, date, remaining_points, ideal_points) VALUES (?, ?, ?, ?, ?)',
            f'snap_{day}', 'sprint_cp_1', d, remaining, ideal,
        )
