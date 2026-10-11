"""Database location and restart behavior without touching application data."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.app import create_app
from backend import paths, seed
from backend.settings import APP_NAME


class DatabasePathTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        temporary = tempfile.TemporaryDirectory(prefix=".judge_paths_test_", dir=paths.ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for mock in (
            patch("backend.paths.ROOT", self.root),
            patch("backend.paths.tempfile.gettempdir", return_value=str(self.root)),
            patch.dict(os.environ, {
                "DATABASE_PATH": "", "DB_PATH": "", "JIRA_DB_PATH": "",
                "WORKSPACE_STORAGE_DIR": "", "APPDATA": str(self.root / "roaming"),
                "TEMP": str(self.root / "temporary"), "TMP": str(self.root / "temporary"),
            }),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def test_default_is_stable_and_shared_with_seed(self):
        first = paths.default_database_path()
        self.assertEqual(first, paths.default_database_path())
        self.assertEqual(first, seed.default_database_path())
        self.assertEqual(first.parent, self.root / "temporary" / APP_NAME)
        self.assertEqual(first.name, "jira.db")

    def test_project_copies_share_user_selected_data_root(self):
        with patch.object(paths, "ROOT", self.root / "first-project"):
            first = paths.default_database_path()
        with patch.object(paths, "ROOT", self.root / "second-project"):
            second = paths.default_database_path()
        self.assertEqual(first, second)

    def test_legacy_paths_retain_checkout_specific_locations(self):
        self.assertEqual(paths.legacy_archive_database_path(), paths.project_temp_path() / "leetcode.db")
        self.assertEqual(paths.legacy_unified_database_path(), paths.project_temp_path() / "jira.db")
        self.assertTrue(paths.legacy_storage_path(paths.default_database_path()).is_relative_to(self.root / "data"))

    def test_default_retains_empty_database_on_restart(self):
        database_path = paths.default_database_path()
        app = create_app({"TESTING": True, "AUTO_SEED": False})
        self.addCleanup(app.extensions["submission_jobs"].shutdown)
        self.addCleanup(app.extensions["audio_store"].shutdown)
        self.assertEqual(app.extensions["database"].path, database_path)
        self.assertTrue(database_path.is_file())
        restarted = create_app({"TESTING": True, "AUTO_SEED": True})
        self.addCleanup(restarted.extensions["submission_jobs"].shutdown)
        self.addCleanup(restarted.extensions["audio_store"].shutdown)
        self.assertEqual(restarted.extensions["database"].path, database_path)
        self.assertEqual(restarted.extensions["database"].count(), 0)

    def test_environment_and_explicit_configuration_override_default(self):
        environment_path = self.root / "environment.sqlite"
        configured_path = self.root / "configured.sqlite"
        with patch.dict(os.environ, {"DATABASE_PATH": str(environment_path)}):
            app = create_app({"TESTING": True, "AUTO_SEED": False})
            configured = create_app({
                "TESTING": True,
                "AUTO_SEED": False,
                "DATABASE_PATH": str(configured_path),
            })
        for application in (app, configured):
            self.addCleanup(application.extensions["submission_jobs"].shutdown)
            self.addCleanup(application.extensions["audio_store"].shutdown)
        self.assertEqual(app.extensions["database"].path, environment_path)
        self.assertEqual(configured.extensions["database"].path, configured_path)
        self.assertFalse(paths.default_database_path().exists())


if __name__ == "__main__":
    unittest.main()

