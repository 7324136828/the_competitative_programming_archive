import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_unified_app
from backend.db import Database
from backend.jira.db import db
from backend.jira.seed import ensure_bootstrap_data


class ProjectCreationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        legacy_path = root / 'legacy.sqlite'
        legacy = Database(legacy_path)
        legacy.initialize()
        legacy.create_problem({'title': 'Legacy', 'problem_statements': 'Do not import by default'})
        with (
            patch.dict(os.environ, {
                'AUTO_SEED': '',
                'MIGRATE_LEGACY_DATABASES': '',
                'SEED_DEMO': '',
                'NODE_ENV': '',
                'JIRA_ENV': '',
            }),
            patch('backend.app.legacy_archive_database_path', return_value=legacy_path),
        ):
            self.app = create_unified_app({
                'TESTING': True,
                'DATABASE_PATH': str(root / 'unified.sqlite'),
                'WORKSPACE_STORAGE_DIR': str(root / 'workspace'),
            })
        archive_app = self.app.state.archive_app
        self.addCleanup(archive_app.extensions['submission_jobs'].shutdown)
        self.addCleanup(archive_app.extensions['audio_store'].shutdown)
        self.client = TestClient(self.app)

    def tearDown(self):
        db.reopen(':memory:')
        ensure_bootstrap_data()

    def test_default_admin_can_create_and_lead_a_project(self):
        response = self.client.post('/api/projects', json={
            'key': 'OWN',
            'name': 'My Own Project',
            'description': 'A user-created project.',
        })

        self.assertEqual(response.status_code, 201, response.text)
        project = response.json()
        self.assertEqual(project['id'], 'proj_own')
        self.assertEqual(project['key'], 'OWN')
        self.assertEqual(project['lead_id'], 'u_admin')
        self.assertEqual(project['lead_name'], 'Admin')
        self.assertIsNotNone(db.q1(
            'SELECT id FROM workflows WHERE project_id = ? AND is_default = 1',
            project['id'],
        ))

    def test_new_database_contains_the_canonical_admin(self):
        self.assertEqual(
            db.q1('SELECT id, name, email, role FROM users WHERE id = ?', 'u_admin'),
            {
                'id': 'u_admin',
                'name': 'Admin',
                'email': 'admin@localhost',
                'role': 'Admin',
            },
        )

    def test_new_database_starts_without_problems_or_stories(self):
        self.assertEqual(self.app.state.archive_database.count(), 0)
        self.assertEqual(db.q1(
            "SELECT COUNT(*) AS c FROM issues WHERE type = 'Story'"
        )['c'], 0)

    def test_bootstrap_adds_canonical_admin_when_another_admin_exists(self):
        db.run("UPDATE projects SET lead_id = NULL WHERE lead_id = 'u_admin'")
        db.run("DELETE FROM users WHERE id = 'u_admin'")
        db.run(
            'INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)',
            'u_other_admin', 'Other Admin', 'other-admin@localhost', '', 'Admin',
        )

        ensure_bootstrap_data()

        self.assertEqual(db.q1(
            "SELECT role FROM users WHERE id = 'u_admin'"
        )['role'], 'Admin')
        self.assertEqual(db.q1(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'Admin'"
        )['c'], 2)

    def test_bootstrap_repairs_a_workspace_without_an_admin(self):
        db.run("UPDATE users SET role = 'Member' WHERE id = 'u_admin'")
        self.assertIsNone(db.q1("SELECT id FROM users WHERE role = 'Admin'"))

        ensure_bootstrap_data()

        self.assertEqual(db.q1("SELECT role FROM users WHERE id = 'u_admin'")['role'], 'Admin')

    def test_non_admin_cannot_create_a_project(self):
        db.run(
            'INSERT INTO users (id, name, email, avatar, role) VALUES (?, ?, ?, ?, ?)',
            'u_member', 'Member', 'member@localhost', '', 'Member',
        )
        response = self.client.post(
            '/api/projects',
            headers={'x-user-id': 'u_member'},
            json={'key': 'NOPE', 'name': 'Not Allowed'},
        )

        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
