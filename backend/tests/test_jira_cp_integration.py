"""Tests for Jira and Competitive Programming Archive integration:
- Every problem is a story (with story_type: coding, learning, non-coding)
- Problem sets are attributed to features
- Set of problem sets are epics (user-created)
- Coding story status depends completely on submission status and test results
- Story import from JSON
- AI generation of coding and non-coding stories
"""

import unittest
import tempfile
from pathlib import Path
from backend.app import create_unified_app
from fastapi.testclient import TestClient
from backend.jira.db import db
from backend.jira.seed import seed_demo_data


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

        # 3. Stories: every problem is a story (with coding, learning, or non-coding types)
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

    def test_ai_story_generation(self):
        # 1. AI Coding Story
        coding_res = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'storyType': 'coding',
            'prompt': 'Write a problem to find the maximum sub-array sum with Kadane algorithm',
            'difficulty': 'Medium',
        })
        self.assertEqual(coding_res.status_code, 201)
        coding_story = coding_res.json()
        self.assertEqual(coding_story['type'], 'Story')
        self.assertEqual(coding_story['story_type'], 'coding')
        self.assertTrue(coding_story['summary'])
        self.assertTrue(coding_story['description'])

        # 2. AI Non-Coding Story
        non_coding_res = self.client.post('/api/ai/generate-story', headers={'x-user-id': 'u_alex'}, json={
            'projectId': 'proj_cp',
            'storyType': 'non-coding',
            'prompt': 'Design an API rate limiter using leaky bucket and token bucket algorithms',
            'difficulty': 'Hard',
        })
        self.assertEqual(non_coding_res.status_code, 201)
        non_coding_story = non_coding_res.json()
        self.assertEqual(non_coding_story['type'], 'Story')
        self.assertEqual(non_coding_story['story_type'], 'non-coding')
        self.assertTrue(non_coding_story['summary'])


if __name__ == '__main__':
    unittest.main()
