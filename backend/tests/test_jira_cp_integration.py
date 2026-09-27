"""Tests for Jira and Competitive Programming Archive integration:
- Coding stories link to archive problems; imported problems may remain unlinked
- Problem sets are attributed to features
- Set of problem sets are epics (user-created)
- Coding story status depends completely on submission status and test results
- Story import from JSON
- AI generation of coding and non-coding stories
"""

import json
import unittest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch
from backend.app import create_unified_app
from fastapi.testclient import TestClient
from backend.jira.db import db
from backend.jira.seed import seed_demo_data
from backend.jira.services.automation import run_automation_trigger


class JiraCompetitiveProgrammingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        app = create_unified_app({
            'TESTING': True,
            'AUTO_SEED': True,
            'BACKFILL_PROBLEM_STORIES': False,
            'DATABASE_PATH': str(Path(cls.temporary.name) / 'unified.sqlite'),
            'WORKSPACE_STORAGE_DIR': str(Path(cls.temporary.name) / 'workspace'),
        })
        seed_demo_data()
        cls.app = app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        archive_app = cls.app.state.archive_app
        archive_app.extensions['submission_jobs'].shutdown()
        archive_app.extensions['audio_store'].shutdown()
        db.reopen(':memory:')
        cls.temporary.cleanup()

    def test_story_start_and_finish_dates_follow_status_transitions(self):
        today = date.today().isoformat()
        headers = {'x-user-id': 'u_alex'}
        story_res = self.client.post('/api/issues', headers=headers, json={
            'projectId': 'proj_cp', 'type': 'Story', 'storyType': 'coding',
            'summary': 'PROJ-10 date transition test',
        })
        self.assertEqual(story_res.status_code, 201)
        story = story_res.json()
        story_id = story['id']
        self.assertIsNone(story['start_date'])
        self.assertIsNone(story['due_date'])

        started = self.client.post(f'/api/issues/{story_id}/start', headers=headers)
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()['status'], 'In Progress')
        self.assertEqual(started.json()['start_date'], today)
        self.assertIsNone(started.json()['due_date'])

        dated = self.client.post(f'/api/issues/{story_id}/dates', headers=headers,
                                 json={'startDate': today, 'dueDate': today})
        self.assertEqual(dated.status_code, 200)
        self.assertEqual(dated.json()['start_date'], today)
        self.assertEqual(dated.json()['due_date'], today)

        submitted = self.client.post(f'/api/issues/{story_id}/submission', headers=headers,
                                     json={'verdict': 'Accepted'})
        self.assertEqual(submitted.status_code, 200)
        finished = self.client.get(f'/api/issues/{story_id}').json()
        self.assertEqual(finished['status'], 'Done')
        self.assertEqual(finished['start_date'], today)
        self.assertEqual(finished['due_date'], today)

        reopened = self.client.post(f'/api/issues/{story_id}/status', headers=headers,
                                    json={'status': 'To Do'})
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()['start_date'], today)
        self.assertIsNone(reopened.json()['due_date'])

    def test_study_story_can_start_from_to_do(self):
        headers = {'x-user-id': 'u_alex'}
        story = self.client.post('/api/issues', headers=headers, json={
            'projectId': 'proj_cp', 'type': 'Story', 'storyType': 'study',
            'summary': 'PROJ-10 study start test',
        }).json()
        started = self.client.post(f"/api/issues/{story['id']}/start", headers=headers)
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()['status'], 'In Progress')
        self.assertEqual(started.json()['start_date'], date.today().isoformat())
        reviewing = self.client.post(f"/api/issues/{story['id']}/status", headers=headers,
                                     json={'status': 'In Review'})
        self.assertEqual(reviewing.status_code, 200)
        self.assertIsNone(reviewing.json()['due_date'])
        finished = self.client.post(f"/api/issues/{story['id']}/status", headers=headers,
                                    json={'status': 'Done'})
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.json()['due_date'], date.today().isoformat())

    def test_automation_status_change_sets_story_dates(self):
        headers = {'x-user-id': 'u_alex'}
        story = self.client.post('/api/issues', headers=headers, json={
            'projectId': 'proj_cp', 'type': 'Story', 'storyType': 'study',
            'summary': 'PROJ-10 automation date test',
        }).json()
        rule_id = 'rule_proj10_story_dates'
        db.run(
            """INSERT INTO automation_rules
               (id, project_id, name, trigger_event, conditions_json, actions_json, is_enabled)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            rule_id, 'proj_cp', 'PROJ-10 date test', 'ASSIGNED',
            json.dumps([{'field': 'summary', 'operator': 'equals', 'value': story['summary']}]),
            json.dumps([{'action': 'set_status', 'target': 'Done'}]),
        )
        try:
            result = run_automation_trigger('ASSIGNED', story['id'], 'proj_cp', 'u_alex')
            self.assertEqual(result[0]['status'], 'SUCCESS')
            finished = self.client.get(f"/api/issues/{story['id']}").json()
            self.assertEqual(finished['status'], 'Done')
            self.assertEqual(finished['start_date'], date.today().isoformat())
            self.assertEqual(finished['due_date'], date.today().isoformat())
        finally:
            db.run('DELETE FROM automation_rules WHERE id = ?', rule_id)

    def test_epics_features_and_stories_hierarchy(self):
        # 1. Epics: set of problem sets created by user
        epic_res = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Epic',
            'summary': 'Dynamic Programming Mastery Track',
            'description': 'User-created epic containing DP problem sets',
        })
        self.assertEqual(epic_res.status_code, 201)
        epic = epic_res.json()
        self.assertEqual(epic['type'], 'Epic')
        epic_id = epic['id']

        # 2. Features: problem sets attributed to features under an epic
        feat_res = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Feature',
            'summary': '1D Dynamic Programming Problem Set',
            'description': 'Problem set for 1D memoization and tabulation',
            'parentId': epic_id,
        })
        self.assertEqual(feat_res.status_code, 201)
        feature = feat_res.json()
        self.assertEqual(feature['type'], 'Feature')
        self.assertEqual(feature['parent_id'], epic_id)
        feat_id = feature['id']

        # 3. Stories support coding, learning, and non-coding activity types.
        # 3a. Coding story
        coding_story = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Story',
            'storyType': 'coding',
            'summary': 'House Robber',
            'description': 'Determine the maximum money you can rob without alerting police.',
            'difficulty': 'Medium',
            'parentId': feat_id,
            'storyPoints': 5,
            'sampleIo': [{'input': '1 2 3 1', 'output': '4'}],
            'hints': ['Identify recurrence: dp[i] = max(dp[i-1], dp[i-2] + nums[i])'],
            'tags': ['Dynamic Programming'],
        }).json()
        self.assertEqual(coding_story['type'], 'Story')
        self.assertEqual(coding_story['story_type'], 'coding')
        self.assertEqual(coding_story['difficulty'], 'Medium')
        self.assertEqual(coding_story['parent_id'], feat_id)
        self.assertEqual(coding_story['submission_status'], 'Unsolved')
        self.assertIsInstance(coding_story['problem_id'], int)
        archived = self.app.state.archive_database.get_problem(coding_story['problem_id'])
        self.assertEqual(archived['story_id'], coding_story['id'])
        self.assertEqual(archived['story_key'], coding_story['key'])

        # 3b. Learning story
        learning_story = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Story',
            'storyType': 'learning',
            'summary': 'Introduction to Bellman Equation in DP',
            'description': 'Comprehensive study notes on state transitions and subproblems.',
            'parentId': feat_id,
            'storyPoints': 3,
        }).json()
        self.assertEqual(learning_story['type'], 'Story')
        self.assertEqual(learning_story['story_type'], 'learning')
        self.assertIsNone(learning_story['problem_id'])

        # 3c. Non-coding story
        non_coding_story = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Story',
            'storyType': 'non-coding',
            'summary': 'Design Real-Time Leaderboard System',
            'description': 'System design task for sub-second ranking updates under high concurrency.',
            'parentId': feat_id,
            'storyPoints': 8,
        }).json()
        self.assertEqual(non_coding_story['type'], 'Story')
        self.assertEqual(non_coding_story['story_type'], 'non-coding')

    def test_coding_story_status_depends_on_submission_and_test_results(self):
        # Create a new coding story
        story = self.client.post('/api/issues', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'type': 'Story',
            'storyType': 'coding',
            'summary': 'Climbing Stairs',
            'description': 'Distinct ways to climb n stairs taking 1 or 2 steps.',
            'difficulty': 'Easy',
            'storyPoints': 2,
        }).json()
        story_id = story['id']
        self.assertEqual(story['status'], 'To Do')

        # Rule check: Manual transition to 'Done' must be rejected because submission is not Accepted
        rejected = self.client.post(f'/api/issues/{story_id}/status', headers={'x-user-id': 'u_alex'}, json={
            'status': 'Done'
        })
        self.assertEqual(rejected.status_code, 400)
        self.assertIn('depends entirely on submission status', rejected.json()['error'])

        # Attempted test run / failed submission: should move to 'In Progress'
        in_prog_res = self.client.post(f'/api/issues/{story_id}/submission', headers={'x-user-id': 'u_alex'}, json={
            'verdict': 'Wrong Answer',
            'test_results': [{'passed': False, 'status': 'Wrong Answer'}],
        })
        self.assertEqual(in_prog_res.status_code, 200)
        self.assertEqual(in_prog_res.json()['status'], 'In Progress')
        self.assertEqual(in_prog_res.json()['submission_status'], 'Wrong Answer')

        # Accepted submission: status must now become 'Done'!
        accepted_res = self.client.post(f'/api/issues/{story_id}/submission', headers={'x-user-id': 'u_alex'}, json={
            'verdict': 'Accepted',
            'test_results': [{'passed': True, 'status': 'Success'}],
        })
        self.assertEqual(accepted_res.status_code, 200)
        self.assertEqual(accepted_res.json()['status'], 'Done')
        self.assertEqual(accepted_res.json()['submission_status'], 'Accepted')

    def test_problem_import_defers_story_creation_until_requested(self):
        upload = self.client.post('/api/problems/upload', json={
            'problems': [{
                'title': 'Deferred Story Problem',
                'problem_statements': 'Import this problem without creating a story.',
                'difficulty': 'Easy',
            }],
        })
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()['insertedCount'], 1)

        problems = self.client.get('/api/problems?search=Deferred+Story+Problem').json()['problems']
        self.assertEqual(len(problems), 1)
        problem = problems[0]
        self.assertIsNone(problem['story_id'])
        self.assertEqual(self.client.get(f"/api/issues/by-problem/{problem['id']}").status_code, 404)

        created = self.client.post(
            f"/api/issues/from-problem/{problem['id']}",
            headers={'x-user-id': 'u_alex'},
            json={'projectId': 'proj_cp'},
        )
        self.assertEqual(created.status_code, 201, created.text)
        story = created.json()
        self.assertEqual(story['problem_id'], problem['id'])

        linked_problem = self.client.get(f"/api/problems/{problem['id']}").json()['problem']
        self.assertEqual(linked_problem['story_id'], story['id'])
        self.assertEqual(linked_problem['story_key'], story['key'])

    def test_import_stories_creates_features_and_epics(self):
        payload = {
            'projectId': 'proj_cp',
            'epicTitle': 'Batch 2026 Competitive Programming Problems',
            'stories': [
                {
                    'title': 'Binary Search',
                    'problem_statements': 'Given a sorted array, search for target in O(log n).',
                    'tags': ['Binary Search'],
                    'difficulty': 'Easy',
                    'sample_input_output': [{'input': '-1 0 3 5 9 12\n9', 'output': '4'}],
                    'hints': ['Compute mid = (left + right) // 2'],
                    'story_type': 'coding',
                    'story_points': 2,
                },
                {
                    'title': 'Binary Search Range Invariants',
                    'problem_statements': 'Learning guide on inclusive vs half-open intervals.',
                    'tags': ['Binary Search'],
                    'story_type': 'learning',
                    'story_points': 2,
                },
            ]
        }
        res = self.client.post('/api/issues/import-stories', headers={'x-user-id': 'u_alex'}, json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['imported'], 2)
        self.assertGreaterEqual(data['features'], 1)
        self.assertTrue(data['epicId'])

        # Verify created stories have feature parent
        imported = data['stories']
        self.assertEqual(len(imported), 2)
        self.assertEqual(imported[0]['story_type'], 'coding')
        self.assertEqual(imported[1]['story_type'], 'learning')
        self.assertEqual(imported[0]['parent_id'], imported[1]['parent_id'])
        self.assertIsInstance(imported[0]['problem_id'], int)
        self.assertIsNone(imported[1]['problem_id'])

        # Navigation works in both directions through persisted identifiers.
        problem_id = imported[0]['problem_id']
        story_from_problem = self.client.get(f'/api/issues/by-problem/{problem_id}')
        self.assertEqual(story_from_problem.status_code, 200)
        self.assertEqual(story_from_problem.json()['id'], imported[0]['id'])
        problem = self.client.get(f'/api/problems/{problem_id}').json()['problem']
        self.assertEqual(problem['story_id'], imported[0]['id'])
        self.assertEqual(problem['story_key'], imported[0]['key'])

    def test_file_import_uses_multipart_and_returns_compact_results(self):
        payload = [{
            'title': 'Multipart Learning Story',
            'description': 'Imported without loading the dataset into the browser editor.',
            'story_type': 'learning',
        }]

        with self.assertLogs('uvicorn.error', level='INFO') as logs:
            response = self.client.post(
                '/api/issues/import-stories/file',
                headers={'x-user-id': 'u_alex'},
                data={
                    'projectId': 'proj_cp',
                    'epicName': 'Multipart Import Epic',
                    'featureName': 'Multipart Problem Set',
                },
                files={
                    'file': ('stories.json', json.dumps(payload).encode('utf-8'), 'application/json'),
                },
            )

        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        self.assertEqual(data['stories_created'], 1)
        self.assertEqual(data['features_created'], 1)
        self.assertEqual(data['epics_created'], 1)
        self.assertEqual(data['stories'], [])
        imported = db.q1(
            "SELECT story_type, description FROM issues WHERE summary = ?",
            'Multipart Learning Story',
        )
        self.assertEqual(imported['story_type'], 'learning')
        self.assertEqual(imported['description'], payload[0]['description'])
        self.assertTrue(any(
            'processing entry 1/1: Multipart Learning Story' in message
            for message in logs.output
        ))

    def test_backlog_is_paged_and_board_hides_unsprinted_todo_stories(self):
        backlog = self.client.get(
            '/api/issues?projectId=proj_cp&type=Story&sprintId=none&page=1&limit=2&compact=true'
        )
        self.assertEqual(backlog.status_code, 200, backlog.text)
        page = backlog.json()
        self.assertEqual(page['page'], 1)
        self.assertEqual(page['limit'], 2)
        self.assertLessEqual(len(page['issues']), 2)
        self.assertGreaterEqual(page['totalPages'], 1)
        self.assertTrue(all(issue['type'] == 'Story' for issue in page['issues']))
        self.assertTrue(all(issue['description'] == '' for issue in page['issues']))

        board = self.client.get('/api/issues?projectId=proj_cp&board=true&compact=true')
        self.assertEqual(board.status_code, 200, board.text)
        todo_items = [issue for issue in board.json() if issue['status'] == 'To Do']
        self.assertTrue(todo_items)
        self.assertTrue(all(issue['sprint_id'] is not None for issue in todo_items))

    def test_backlog_queries_include_bugs_and_preserve_project_and_sprint_filters(self):
        headers = {'x-user-id': 'u_alex'}
        sprint_res = self.client.post('/api/sprints/projects/proj_cp', json={
            'name': 'PROJ-13 Bug Sprint',
        })
        self.assertEqual(sprint_res.status_code, 201)
        sprint_id = sprint_res.json()['id']

        def make_issue(issue_type, summary, project_id='proj_cp', sprint=None):
            result = self.client.post('/api/issues', headers=headers, json={
                'projectId': project_id, 'type': issue_type, 'summary': summary,
                'sprintId': sprint,
            })
            self.assertEqual(result.status_code, 201, result.text)
            return result.json()

        backlog_bug = make_issue('Bug', 'PROJ-13 backlog bug')
        sprint_bug = make_issue('Bug', 'PROJ-13 sprint bug', sprint=sprint_id)
        backlog_story = make_issue('Story', 'PROJ-13 backlog story')
        other_project_bug = make_issue('Bug', 'PROJ-13 other project bug', project_id='proj_mob')
        task = make_issue('Task', 'PROJ-13 excluded task')

        unsprinted = self.client.get(
            '/api/issues?projectId=proj_cp&types=Story,Bug&sprintId=none&query=PROJ-13&page=1&limit=2&compact=true'
        )
        self.assertEqual(unsprinted.status_code, 200, unsprinted.text)
        page = unsprinted.json()
        self.assertEqual(page['total'], 2)
        self.assertEqual({issue['id'] for issue in page['issues']}, {backlog_bug['id'], backlog_story['id']})
        self.assertNotIn(task['id'], [issue['id'] for issue in page['issues']])
        self.assertNotIn(other_project_bug['id'], [issue['id'] for issue in page['issues']])

        assigned = self.client.get(
            '/api/issues?projectId=proj_cp&types=Story,Bug&sprintAssigned=true&query=PROJ-13&compact=true'
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual([issue['id'] for issue in assigned.json()], [sprint_bug['id']])

    def test_ai_story_generation(self):
        with patch('backend.jira.routers.ai.resolve_connector_model', return_value={'model': 'test-model'}), \
             patch('backend.jira.routers.ai.chat_completion') as completion:
            completion.return_value = {'message': {'content': json.dumps({
                'summary': 'Maximum subarray sum', 'description': 'Find the maximum sum.',
                'sample_input_output': [{'input': '1 2', 'output': '3'}],
                'hints': ['Use a running sum'], 'tags': ['Arrays'], 'story_points': 5,
            })}}
            coding_res = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json={
                'projectId': 'proj_cp', 'storyType': 'coding',
                'prompt': 'Write a problem to find the maximum sub-array sum with Kadane algorithm',
                'difficulty': 'Medium', 'title': 'Kadane practice',
            })
            self.assertEqual(completion.call_args.args[0], 'test-model')
        self.assertEqual(coding_res.status_code, 201)
        coding_story = coding_res.json()['issue']
        self.assertEqual(coding_story['type'], 'Story')
        self.assertEqual(coding_story['story_type'], 'coding')
        self.assertEqual(coding_story['summary'], 'Kadane practice')
        self.assertEqual(coding_story['description'], 'Find the maximum sum.')

        with patch('backend.jira.routers.ai.resolve_connector_model', return_value={'model': 'test-model'}), \
             patch('backend.jira.routers.ai.chat_completion', return_value={
                 'message': {'content': '```json\n{"summary":"Rate limiter","description":"Design the architecture."}\n```'}
             }):
            non_coding_res = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json={
                'projectId': 'proj_cp', 'storyType': 'non-coding',
                'prompt': 'Design an API rate limiter using leaky bucket and token bucket algorithms',
                'difficulty': 'Hard',
            })
        self.assertEqual(non_coding_res.status_code, 201)
        non_coding_story = non_coding_res.json()['issue']
        self.assertEqual(non_coding_story['type'], 'Story')
        self.assertEqual(non_coding_story['story_type'], 'non-coding')
        self.assertTrue(non_coding_story['summary'])

    def test_ai_story_generation_failure_is_clear(self):
        from backend.jira.services.ai.client import ConnectorError

        request = {'projectId': 'proj_cp', 'storyType': 'learning', 'prompt': 'Explain graph traversal'}
        with patch('backend.jira.routers.ai.resolve_connector_model', return_value={'model': 'test-model'}), \
             patch('backend.jira.routers.ai.chat_completion', side_effect=ConnectorError(
                 503, 'connector_unreachable', 'Connector is offline')):
            failed = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json=request)
        self.assertEqual(failed.status_code, 502)
        self.assertIn('Connector is offline', failed.json()['error'])

        with patch('backend.jira.routers.ai.resolve_connector_model', return_value={'model': 'test-model'}), \
             patch('backend.jira.routers.ai.chat_completion', return_value={
                 'message': {'content': 'not JSON'}
             }):
            malformed = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json=request)
        self.assertEqual(malformed.status_code, 502)
        self.assertIn('invalid story', malformed.json()['error'])

    def test_story_title_and_description_edits_persist(self):
        headers = {'x-user-id': 'u_alex'}
        created = self.client.post('/api/issues', headers=headers, json={
            'projectId': 'proj_cp', 'type': 'Story', 'storyType': 'learning',
            'summary': 'PROJ-11 description edit', 'description': 'Original description',
        })
        self.assertEqual(created.status_code, 201)
        issue_id = created.json()['id']
        updated = self.client.patch(f'/api/issues/{issue_id}', headers=headers,
                                    json={'description': 'Revised description\nSecond line'})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['description'], 'Revised description\nSecond line')
        reopened = self.client.get(f'/api/issues/{issue_id}')
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()['description'], 'Revised description\nSecond line')

        renamed = self.client.patch(f'/api/issues/{issue_id}', headers=headers,
                                    json={'summary': 'Revised story title'})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()['summary'], 'Revised story title')
        reopened = self.client.get(f'/api/issues/{issue_id}')
        self.assertEqual(reopened.json()['summary'], 'Revised story title')

        blank = self.client.patch(f'/api/issues/{issue_id}', headers=headers,
                                  json={'summary': '   '})
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(self.client.get(f'/api/issues/{issue_id}').json()['summary'],
                         'Revised story title')


if __name__ == '__main__':
    unittest.main()
