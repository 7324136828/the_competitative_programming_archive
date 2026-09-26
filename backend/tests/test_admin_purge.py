import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_unified_app
from backend.jira.db import db
from backend.jira.seed import ensure_bootstrap_data, seed_demo_data
from backend.jira.services.users import get_default_user_id


class AdminPurgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = create_unified_app({
            'TESTING': True,
            'AUTO_SEED': False,
            'DATABASE_PATH': str(Path(self.temporary.name) / 'archive.sqlite'),
            'WORKSPACE_STORAGE_DIR': str(Path(self.temporary.name) / 'workspace'),
        })
        archive_app = self.app.state.archive_app
        seed_demo_data()
        self.addCleanup(archive_app.extensions['submission_jobs'].shutdown)
        self.addCleanup(archive_app.extensions['audio_store'].shutdown)
        self.client = TestClient(self.app)

    def tearDown(self):
        # Leave the process-global Jira connection in the demo state expected by
        # the integration tests that share this test process.
        db.reopen(':memory:')
        seed_demo_data()
        ensure_bootstrap_data()

    def test_requires_explicit_admin_identity_and_confirmation(self):
        no_identity = self.client.post('/api/admin/purge', json={'confirmation': 'PURGE'})
        self.assertEqual(no_identity.status_code, 403)

        member = self.client.post(
            '/api/admin/purge',
            headers={'x-user-id': 'u_sarah'},
            json={'confirmation': 'PURGE'},
        )
        self.assertEqual(member.status_code, 403)

        unconfirmed = self.client.post(
            '/api/admin/purge',
            headers={'x-user-id': 'u_alex'},
            json={'confirmation': 'purge'},
        )
        self.assertEqual(unconfirmed.status_code, 400)
        self.assertGreater(db.q1('SELECT COUNT(*) AS c FROM issues')['c'], 0)

    def test_admin_purge_clears_both_stores_and_rebootstraps_workspace(self):
        archive = self.app.state.archive_database
        self.assertEqual(Path(archive.path).resolve(), Path(db.path).resolve())
        problem = archive.create_problem({
            'title': 'Disposable problem',
            'problem_statements': 'This should be purged.',
        })
        archive.save_submission({
            'problem_id': problem['id'],
            'language': 'python',
            'code': 'print(1)',
            'status': 'Wrong Answer',
            'test_results': [],
        })

        response = self.client.post(
            '/api/admin/purge',
            headers={'x-user-id': 'u_alex'},
            json={'confirmation': 'PURGE'},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertGreater(body['deleted']['issues'], 0)
        self.assertEqual(body['deleted']['problems'], 1)
        self.assertEqual(body['deleted']['submissions'], 1)
        self.assertEqual(archive.count(), 0)
        self.assertEqual(db.q1('SELECT COUNT(*) AS c FROM issues')['c'], 0)
        self.assertEqual(db.q1(
            "SELECT role FROM users WHERE id = 'u_admin'"
        )['role'], 'Admin')
        self.assertEqual(get_default_user_id(), 'u_admin')
        self.assertEqual(db.q1('SELECT COUNT(*) AS c FROM projects')['c'], 1)


if __name__ == '__main__':
    unittest.main()
