"""Launcher setup checks; no package installation or GPU is required."""

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import setup


class KokoroSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        (self.root / "requirements.txt").write_text("kokoro==0.9.4\n")
        (self.root / "requirements-cuda.txt").write_text("torch==2.11.0+cu128\n")
        for name, value in (("KOKORO_DIR", self.root), ("KOKORO_PYTHON", self.python)):
            self.enterContext(patch.object(setup, name, value))
        self.probe = self.enterContext(patch.object(setup, "is_python312", return_value=True))
        self.run = self.enterContext(patch.object(setup, "run"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def commands(self):
        return [call.args[0] for call in self.run.call_args_list]

    def test_cuda_installs_pinned_requirements_only_into_dedicated_environment(self):
        setup.setup_kokoro("cuda")
        commands = self.commands()
        self.assertTrue(all(command[0] == self.python for command in commands))
        self.assertEqual(commands[0][-2:], ["-r", self.root / "requirements-cuda.txt"])
        self.assertEqual(commands[1][-2:], ["-r", self.root / "requirements.txt"])
        self.assertIn("torch.ones(1, device='cuda').add_(1).item()", commands[-1][-1])

    def test_cpu_install_never_probes_or_executes_cuda(self):
        setup.setup_kokoro("cpu")
        commands = self.commands()
        self.assertIn("https://download.pytorch.org/whl/cpu", commands[0])
        self.assertFalse(any("torch.cuda" in str(command) for command in commands))
        self.assertFalse(any(self.root / "requirements-cuda.txt" in command for command in commands))

    def test_wrong_python_version_stops_before_installing_anything(self):
        self.probe.return_value = False
        with self.assertRaisesRegex(setup.SetupError, "must be Python 3.12"):
            setup.setup_kokoro("cuda")
        self.run.assert_not_called()
        self.assertTrue(self.python.exists())

    def test_cuda_compute_failure_fails_without_cpu_fallback(self):
        def fail_cuda(command):
            if "torch.ones(" in str(command):
                raise setup.SetupError("GPU kernel failed")

        self.run.side_effect = fail_cuda
        with self.assertRaisesRegex(setup.SetupError, "CUDA verification failed"):
            setup.setup_kokoro("cuda")
        self.assertFalse(any("whl/cpu" in str(command) for command in self.commands()))

    def test_new_environment_uses_python312_and_explicit_system_packages_flag(self):
        self.python.unlink()

        def create_environment(command):
            if "venv" in command:
                self.python.touch()

        self.run.side_effect = create_environment
        with patch.object(setup, "find_python312", return_value=["py", "-3.12"]):
            setup.setup_kokoro("cuda", reuse_system_packages=True)
        self.assertEqual(
            self.commands()[0],
            ["py", "-3.12", "-m", "venv", "--system-site-packages", str(self.root / ".venv")],
        )
        self.probe.assert_called_once_with([self.python])

    def test_missing_python312_does_not_install_into_application_environment(self):
        self.python.unlink()
        with patch.object(setup, "find_python312", side_effect=setup.SetupError("Install Python 3.12")):
            with self.assertRaisesRegex(setup.SetupError, "Install Python 3.12"):
                setup.setup_kokoro("cuda")
        self.run.assert_not_called()


class SetupOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.load_env = self.enterContext(patch.object(setup, "load_env_file"))
        self.seed_env = self.enterContext(patch.object(setup, "seed_environment_file"))
        self.application = self.enterContext(patch.object(setup, "setup_application"))
        self.kokoro = self.enterContext(patch.object(setup, "setup_kokoro"))

    def test_default_sets_up_application_and_cuda(self):
        self.assertEqual(setup.main([]), 0)
        self.application.assert_called_once_with()
        self.kokoro.assert_called_once_with("cuda", reuse_system_packages=False)

    def test_kokoro_only_does_not_require_node_or_application_dependencies(self):
        self.assertEqual(setup.main(["--kokoro-only", "--kokoro-device", "cpu"]), 0)
        self.application.assert_not_called()
        self.kokoro.assert_called_once_with("cpu", reuse_system_packages=False)

    def test_skip_kokoro_does_not_validate_or_install_kokoro(self):
        os.environ["KOKORO_DEVICE"] = "invalid"
        self.assertEqual(setup.main(["--skip-kokoro"]), 0)
        self.application.assert_called_once_with()
        self.kokoro.assert_not_called()

    def test_environment_is_loaded_before_selecting_device(self):
        self.load_env.side_effect = lambda: os.environ.setdefault("KOKORO_DEVICE", "cpu")
        setup.main(["--kokoro-only"])
        self.kokoro.assert_called_once_with("cpu", reuse_system_packages=False)

    def test_explicit_device_overrides_environment(self):
        os.environ["KOKORO_DEVICE"] = "cpu"
        setup.main(["--kokoro-only", "--kokoro-device", "cuda"])
        self.kokoro.assert_called_once_with("cuda", reuse_system_packages=False)

    def test_auto_runtime_installs_cuda_capable_build(self):
        os.environ["KOKORO_DEVICE"] = "auto"
        setup.main(["--kokoro-only"])
        self.kokoro.assert_called_once_with("cuda", reuse_system_packages=False)

    def test_invalid_device_fails_before_installations(self):
        os.environ["KOKORO_DEVICE"] = "typo"
        with self.assertRaisesRegex(setup.SetupError, "KOKORO_DEVICE"):
            setup.main([])
        self.kokoro.assert_not_called()
        self.application.assert_not_called()


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
