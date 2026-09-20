"""Database location and restart behavior without touching application data."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app import create_app
from backend import paths, seed


class DatabasePathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="judge_paths_test_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for mock in (
            patch("backend.paths.tempfile.gettempdir", return_value=str(self.root)),
            patch.dict(os.environ, {"DATABASE_PATH": ""}),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def test_default_is_stable_in_system_temp_and_shared_with_seed(self):
        first = paths.default_database_path()
        self.assertEqual(first, paths.default_database_path())
        self.assertEqual(first, seed.default_database_path())
        self.assertTrue(first.is_relative_to(self.root / "codejudge"))
        self.assertEqual(first.name, "leetcode.db")

    def test_project_copies_have_separate_databases(self):
        with patch.object(paths, "ROOT", self.root / "first-project"):
            first = paths.default_database_path()
        with patch.object(paths, "ROOT", self.root / "second-project"):
            second = paths.default_database_path()
        self.assertNotEqual(first, second)

    def test_default_retains_empty_database_on_restart(self):
        database_path = paths.default_database_path()
        app = create_app({"TESTING": True, "AUTO_SEED": False})
        self.assertEqual(app.extensions["database"].path, database_path)
        self.assertTrue(database_path.is_file())
        restarted = create_app({"TESTING": True, "AUTO_SEED": True})
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
        self.assertEqual(app.extensions["database"].path, environment_path)
        self.assertEqual(configured.extensions["database"].path, configured_path)
        self.assertFalse(paths.default_database_path().exists())


if __name__ == "__main__":
    unittest.main()

