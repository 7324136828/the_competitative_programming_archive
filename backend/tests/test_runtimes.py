"""Runtime discovery covers missing, broken, PATH, and non-PATH installations."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend import runtimes


class RuntimeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.which = self.enterContext(patch.object(runtimes.shutil, "which", return_value=None))
        self.enterContext(patch.object(runtimes.sys, "executable", ""))
        self.enterContext(patch.object(runtimes, "STRAWBERRY_CPP", ""))
        self.enterContext(patch.dict(os.environ, {"JAVA_HOME": ""}))
        self.usable = self.enterContext(
            patch.object(runtimes, "_usable", side_effect=lambda path, *args, **kwargs: bool(path) and Path(path).is_file())
        )

    def executable(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return str(path)

    def test_missing_tools_return_no_languages(self):
        self.assertEqual(runtimes.available_languages(), [])

    def test_running_python_is_preferred(self):
        python = self.executable("current-python")
        other = self.executable("other-python")
        self.which.side_effect = lambda name: other if name == "python" else None
        with patch.object(runtimes.sys, "executable", python):
            detected = runtimes.discover_runtimes()
        self.assertEqual(detected["python"].executable, python)
        self.assertEqual(
            self.usable.call_args_list[0].args[1], ["-c", "import sys; sys.exit(sys.version_info.major != 3)"]
        )

    def test_broken_python_falls_back_to_path(self):
        python = self.executable("python3")
        self.which.side_effect = lambda name: python if name == "python3" else None
        with patch.object(runtimes.sys, "executable", "missing-python"):
            self.assertEqual(runtimes.discover_runtimes()["python"].executable, python)

    def test_path_compiler_and_public_language_metadata(self):
        compiler = self.executable("clang++")
        self.which.side_effect = lambda name: compiler if name == "clang++" else None
        self.assertEqual(runtimes.discover_runtimes()["cpp"].compiler, compiler)
        self.assertEqual(runtimes.available_languages(), [{"id": "cpp", "label": "C++", "editorLanguage": "cpp"}])

    @unittest.skipUnless(os.name == "nt", "Windows installation fallback")
    def test_strawberry_is_used_when_missing_from_path(self):
        compiler = self.executable("strawberry/bin/g++.exe")
        with patch.object(runtimes, "STRAWBERRY_CPP", compiler):
            detected = runtimes.discover_runtimes()
        self.assertEqual(detected["cpp"].compiler, compiler)
        self.assertEqual(self.usable.call_args.args[2]["PATH"].split(os.pathsep)[0], str(Path(compiler).parent))

    def test_java_runtime_without_compiler_is_not_available(self):
        java = self.executable("java")
        self.which.side_effect = lambda name: java if name == "java" else None
        self.assertNotIn("java", runtimes.discover_runtimes())

    def test_java_home_supplies_complete_toolchain(self):
        suffix = ".exe" if os.name == "nt" else ""
        java = self.executable("jdk/bin/java" + suffix)
        javac = self.executable("jdk/bin/javac" + suffix)
        with patch.dict(os.environ, {"JAVA_HOME": str(self.root / "jdk")}):
            detected = runtimes.discover_runtimes()
        self.assertEqual(detected["java"], runtimes.Runtime(java, javac))

    def test_java_home_does_not_accept_compiler_only(self):
        suffix = ".exe" if os.name == "nt" else ""
        self.executable("jdk/bin/javac" + suffix)
        with patch.dict(os.environ, {"JAVA_HOME": str(self.root / "jdk")}):
            self.assertNotIn("java", runtimes.discover_runtimes())

    def test_environment_retains_path_without_mutating_parent(self):
        compiler = self.executable("tools/g++")
        with patch.dict(os.environ, {"PATH": "original-path"}):
            environment = runtimes.Runtime(compiler, compiler).environment()
            self.assertEqual(environment["PATH"], str(Path(compiler).parent) + os.pathsep + "original-path")
            self.assertEqual(os.environ["PATH"], "original-path")


class RuntimeProbeTests(unittest.TestCase):
    def test_failed_or_hung_executables_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "tool"
            executable.touch()
            for outcome in (
                subprocess.CompletedProcess([], 1),
                OSError("cannot start"),
                subprocess.TimeoutExpired([], 3),
            ):
                with self.subTest(outcome=outcome):
                    kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                    with patch.object(runtimes.subprocess, "run", **kwargs):
                        self.assertFalse(runtimes._usable(str(executable), ["--version"]))


if __name__ == "__main__":
    unittest.main()

