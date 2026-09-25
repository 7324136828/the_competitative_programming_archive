"""Launcher setup checks; no package installation is required."""

import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import setup


class SetupOrchestrationTests(unittest.TestCase):
    def test_default_sets_up_application_once(self):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(setup, "load_env_file") as load_env,
            patch.object(setup, "seed_environment_file") as seed_env,
            patch.object(setup, "setup_application") as application,
        ):
            self.assertEqual(setup.main([]), 0)
        load_env.assert_called_once_with()
        seed_env.assert_called_once_with()
        application.assert_called_once_with()


class ApplicationSetupTests(unittest.TestCase):
    def test_each_node_project_is_installed_once(self):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(setup.shutil, "which", return_value="npm"),
            patch.object(setup, "select_python", return_value=Path("app-python")),
            patch.object(setup, "run") as run,
        ):
            setup.setup_application()
        node_installs = [call for call in run.call_args_list if call.args[0] == ["npm", "install"]]
        self.assertEqual([call.kwargs["cwd"] for call in node_installs], [setup.FRONTEND, setup.E2E])
        self.assertEqual(run.call_args_list[0].args[0][0], Path("app-python"))


if __name__ == "__main__":
    unittest.main()
