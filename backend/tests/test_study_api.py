"""Comprehensive tests for Study Set integration in the competitive programming archive:
- Workspace listing and loading
- Zip upload, validation, and content store extraction
- Jira story creation and bidirectional association for study sets
- Searching issues by study set
- QA sessions lifecycle and download
- Delete study set
"""

import io
import json
import zipfile
import unittest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app import create_unified_app
from backend.jira.db import db
from backend.jira.seed import seed_demo_data


class StudySetApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temporary.name)
        app = create_unified_app({
            'TESTING': True,
            'AUTO_SEED': True,
            'BACKFILL_PROBLEM_STORIES': False,
            'DATABASE_PATH': str(cls.temp_path / 'unified.sqlite'),
            'WORKSPACE_STORAGE_DIR': str(cls.temp_path / 'workspace'),
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

    def _create_mock_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            manifest = {
                "title": "Algorithms Deep Dive",
                "workspace": [
                    {"name": "Trees & Graphs (Chapter 1)", "path": "./chapter_output/ch_1/output"},
                    {"name": "Trees & Graphs (Chapter 2)", "path": "./chapter_output/ch_2/output"},
                ]
            }
            z.writestr("workspace.json", json.dumps(manifest))
            fc_data = {
                "title": "Tree Concepts",
                "cards": [
                    {"front": "BFS", "back": "Queue based level order traversal"},
                    {"front": "DFS", "back": "Stack or recursive depth traversal"}
                ]
            }
            z.writestr("chapter_output/ch_1/output/flashcards/trees.json", json.dumps(fc_data))
            quiz_data = {
                "title": "Tree Quiz",
                "questions": [
                    {
                        "question": "What is the time complexity of BFS on a tree with N nodes?",
                        "options": ["O(N)", "O(log N)", "O(N^2)"],
                        "answer": 0
                    }
                ]
            }
            z.writestr("chapter_output/ch_1/output/quizzes/quiz.json", json.dumps(quiz_data))
            z.writestr(
                "chapter_output/ch_2/output/quizzes/quiz.json",
                json.dumps({
                    "title": "Graph Quiz",
                    "questions": [{
                        "question": "Which traversal uses a queue?",
                        "options": ["BFS", "DFS"],
                        "answer": 0,
                    }],
                }),
            )
        return buf.getvalue()

    def test_01_workspace_status_initial(self):
        res = self.client.get('/api/workspace')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('currentWorkspace', data)
        self.assertIn('workspaces', data)
        self.assertIsInstance(data['workspaces'], list)

    def test_02_upload_and_extract_study_set(self):
        zip_bytes = self._create_mock_zip()
        res = self.client.post(
            '/api/workspace/upload',
            content=zip_bytes,
            headers={'Content-Type': 'application/zip'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('uploadId', data)
        self.assertIn('workspaces', data)
        self.assertEqual(len(data['workspaces']), 2)
        self.assertEqual(
            [workspace['name'] for workspace in data['workspaces']],
            ['Trees & Graphs (Chapter 1)', 'Trees & Graphs (Chapter 2)'],
        )
        ws = data['workspaces'][0]
        self.assertEqual(ws['name'], 'Trees & Graphs (Chapter 1)')
        self.assertEqual(data['activeWorkspace'], ws['id'])
        self.assertTrue(data['exists'])
        StudySetApiTests.created_workspace_id = ws['id']

        # The content viewer uses the manifest beneath /api/content so that it
        # shares a URL namespace with the individual documents.
        manifest_res = self.client.get('/api/content/manifest')
        self.assertEqual(manifest_res.status_code, 200)
        manifest = manifest_res.json()
        self.assertEqual(manifest['kinds']['quizzes'][0]['file'], 'quiz.json')
        self.assertEqual(manifest['kinds']['flashcards'][0]['file'], 'trees.json')

        content_res = self.client.get('/api/content/quizzes/quiz.json')
        self.assertEqual(content_res.status_code, 200)
        self.assertEqual(content_res.json()['title'], 'Tree Quiz')

        chapter_two = data['workspaces'][1]
        activate_res = self.client.post(
            '/api/workspace/activate',
            json={'workspace': chapter_two['id']},
        )
        self.assertEqual(activate_res.status_code, 200)
        chapter_two_manifest = self.client.get('/api/content/manifest').json()
        self.assertEqual(chapter_two_manifest['kinds']['quizzes'][0]['title'], 'Graph Quiz')
        self.assertEqual(chapter_two_manifest['kinds']['flashcards'], [])

        # Leave chapter one active for the association lifecycle tests below.
        self.client.post('/api/workspace/activate', json={'workspace': ws['id']})

    def test_03_create_story_for_study_set(self):
        ws_id = getattr(self, 'created_workspace_id', None)
        self.assertIsNotNone(ws_id)

        res = self.client.post(
            '/api/workspace/create-story',
            headers={'x-user-id': 'u_alex'},
            json={
                'workspaceId': ws_id,
                'summary': 'Master Trees & Graphs Chapter 1 Study Set',
                'projectId': 'proj_cp',
            }
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['success'])
        issue = body['issue']
        self.assertEqual(issue['story_type'], 'study')
        self.assertEqual(issue['study_set_id'], ws_id)
        StudySetApiTests.created_issue_id = issue['id']

        workspace_res = self.client.get('/api/workspace')
        linked_workspace = next(
            workspace for workspace in workspace_res.json()['workspaces']
            if workspace['id'] == ws_id
        )
        self.assertEqual(linked_workspace['story']['id'], issue['id'])
        self.assertEqual(linked_workspace['story']['key'], issue['key'])

        uploads_res = self.client.get('/api/workspace/uploads')
        linked_set = uploads_res.json()['uploads'][0]['studySets'][0]
        self.assertEqual(linked_set['story']['id'], issue['id'])

        # Verify issue is searchable by study set
        lookup_res = self.client.get(f'/api/issues/by-study-set/{ws_id}')
        self.assertEqual(lookup_res.status_code, 200)
        self.assertEqual(lookup_res.json()['id'], issue['id'])

    def test_04_unlink_and_reassociate_study_set(self):
        ws_id = getattr(self, 'created_workspace_id', None)
        issue_id = getattr(self, 'created_issue_id', None)
        self.assertIsNotNone(ws_id)
        self.assertIsNotNone(issue_id)

        # Unlink
        res_unlink = self.client.post(
            '/api/workspace/unlink-story',
            json={'workspaceId': ws_id}
        )
        self.assertEqual(res_unlink.status_code, 200)
        self.assertTrue(res_unlink.json()['success'])

        # Verify unlinked
        lookup_res = self.client.get(f'/api/issues/by-study-set/{ws_id}')
        self.assertEqual(lookup_res.status_code, 404)

        # Re-associate
        res_assoc = self.client.post(
            '/api/workspace/associate-story',
            json={'workspaceId': ws_id, 'issueId': issue_id}
        )
        self.assertEqual(res_assoc.status_code, 200)
        self.assertTrue(res_assoc.json()['success'])

        lookup_res2 = self.client.get(f'/api/issues/by-study-set/{ws_id}')
        self.assertEqual(lookup_res2.status_code, 200)
        self.assertEqual(lookup_res2.json()['id'], issue_id)

    def test_05_qa_sessions_lifecycle(self):
        create_res = self.client.post(
            '/api/qa/sessions',
            json={
                'qaFile': 'trees/output/qanda/trees.json',
                'title': 'Tree Traversal Q&A',
                'questions': [
                    {'id': 'q1', 'question': 'Explain preorder traversal.'},
                    {'id': 'q2', 'question': 'When is BFS preferred over DFS?'}
                ]
            }
        )
        self.assertEqual(create_res.status_code, 200)
        session = create_res.json()
        session_id = session['id']
        self.assertEqual(session['status'], 'in_progress')

        # Get session
        get_res = self.client.get(f'/api/qa/sessions/{session_id}')
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()['id'], session_id)

        # Update session
        put_res = self.client.put(
            f'/api/qa/sessions/{session_id}',
            json={
                'answers': ['Root, Left, Right', 'When finding the shortest path in unweighted graphs'],
                'currentQuestion': 1,
                'completed': True
            }
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()['status'], 'completed')

        # Download session
        dl_res = self.client.get(f'/api/qa/sessions/{session_id}/download')
        self.assertEqual(dl_res.status_code, 200)
        data = dl_res.json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(len(data['answers']), 2)

    def test_06_delete_study_set(self):
        ws_id = getattr(self, 'created_workspace_id', None)
        self.assertIsNotNone(ws_id)

        del_res = self.client.delete(f'/api/workspace/study-sets/{ws_id}')
        self.assertEqual(del_res.status_code, 200)
        body = del_res.json()
        self.assertIn('deleted', body)
        self.assertEqual(body['deleted']['id'], ws_id)
