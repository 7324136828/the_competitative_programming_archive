import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_unified_app
from backend.jira.db import db


class NotificationClearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.app = create_unified_app({
            'TESTING': True,
            'AUTO_SEED': False,
            'DATABASE_PATH': str(root / 'unified.sqlite'),
            'WORKSPACE_STORAGE_DIR': str(root / 'workspace'),
        })
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.app.state.archive_app.extensions['submission_jobs'].shutdown()
        cls.app.state.archive_app.extensions['audio_store'].shutdown()
        db.reopen(':memory:')
        cls.temporary.cleanup()

    def test_clear_all_removes_only_the_current_users_notifications(self):
        other = self.client.post('/api/users', json={
            'name': 'Notification Test User',
            'email': 'notification-test@example.com',
            'role': 'Member',
        })
        self.assertEqual(other.status_code, 201, other.text)
        other_id = other.json()['id']
        db.run("INSERT INTO notifications (id, user_id, title, message, is_read) VALUES (?, ?, ?, ?, ?)",
               'notif_unread', 'u_admin', 'Unread', 'A new event', 0)
        db.run("INSERT INTO notifications (id, user_id, title, message, is_read) VALUES (?, ?, ?, ?, ?)",
               'notif_read', 'u_admin', 'Read', 'An earlier event', 1)
        db.run("INSERT INTO notifications (id, user_id, title, message, is_read) VALUES (?, ?, ?, ?, ?)",
               'notif_other', other_id, 'Other user', 'Keep this', 0)

        cleared = self.client.delete('/api/notifications', headers={'x-user-id': 'u_admin'})
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json(), {'success': True, 'cleared': 2})
        self.assertEqual(self.client.get('/api/notifications', headers={'x-user-id': 'u_admin'}).json(), [])
        remaining = self.client.get('/api/notifications', headers={'x-user-id': other_id}).json()
        self.assertEqual([notification['id'] for notification in remaining], ['notif_other'])

        again = self.client.delete('/api/notifications', headers={'x-user-id': 'u_admin'})
        self.assertEqual(again.json()['cleared'], 0)


if __name__ == '__main__':
    unittest.main()
