"""Verify portable profiles, bundled resources, and transactional publishing."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build


class PortableBuildTests(unittest.TestCase):
    def test_profiles_include_complete_portable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / "server.exe").write_bytes(b"frozen application")
            (stage / "public" / "assets").mkdir(parents=True)
            (stage / "public" / "index.html").write_text("<html>Study</html>")
            (stage / "public" / "assets" / "client.js").write_text("console.log('Study')")
            packages = build.prepare_artifacts(stage)
            for profile, host in build.PROFILES.items():
                package = packages / profile
                build.validate_artifacts(package, host=host)
                self.assertEqual((package / "server.exe").read_bytes(), b"frozen application")
                self.assertTrue((package / "public" / "assets" / "client.js").is_file())
                self.assertEqual(json.loads((package / "runtime.json").read_text()), {"host": host})
                self.assertEqual((package / "port_mapping.json").read_bytes(), build.PORT_MAPPING.read_bytes())
                launcher = (package / "run.bat").read_text()
                self.assertIn('"%~dp0server.exe" --prepare-settings --ports-file "%APP_PORTS_FILE%"', launcher)
                self.assertIn('"%~dp0server.exe" --frontend-port %APP_FRONTEND_PORT% --backend-port %APP_BACKEND_PORT% %*', launcher)
                self.assertIn('echo {}', launcher)
                self.assertIn('settings.json', launcher)
                self.assertIn('Fill missing ports from port_mapping.json beside server.exe', launcher)
                self.assertNotIn('frontend_port=5100', launcher)
                self.assertNotIn("python", launcher)
                self.assertNotIn("npm", launcher)

    def test_custom_port_mapping_is_copied_byte_for_byte_into_both_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            defaults = stage / "custom-ports.json"
            content = b'\xef\xbb\xbf{\r\n  "frontend_port": 4201,\r\n  "backend_port": 9201,\r\n  "description": "custom defaults"\r\n}\r\n'
            defaults.write_bytes(content)
            (stage / "server.exe").write_bytes(b"application")
            (stage / "public").mkdir()
            (stage / "public" / "index.html").write_text("frontend")
            packages = build.prepare_artifacts(stage, defaults_path=defaults)
            for profile, host in build.PROFILES.items():
                package = packages / profile
                self.assertEqual((package / "port_mapping.json").read_bytes(), content)
                build.validate_artifacts(package, host=host)

    def test_invalid_or_missing_port_mapping_is_a_build_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ports.json"
            with self.assertRaises(build.BuildError):
                build.validate_port_defaults(path)
            for payload in ('{broken', '[]', '{}', '{"frontend_port": true, "backend_port": 8011}',
                            '{"frontend_port": "5100", "backend_port": 8011}',
                            '{"frontend_port": 0, "backend_port": 8011}',
                            '{"frontend_port": 5100, "backend_port": 65536}'):
                with self.subTest(payload=payload):
                    path.write_text(payload)
                    with self.assertRaises(build.BuildError):
                        build.validate_port_defaults(path)

    @unittest.skipUnless(os.name == "nt", "Windows build preflight")
    def test_missing_or_invalid_mapping_fails_before_build_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            mapping = Path(directory) / "port_mapping.json"
            for payload in (None, '{"frontend_port": -1, "backend_port": 8011}'):
                with self.subTest(payload=payload):
                    if payload is not None:
                        mapping.write_text(payload)
                    with patch.object(build, "PORT_MAPPING", mapping), patch.object(
                        build, "select_python"
                    ) as select_python, patch.object(build, "run") as run, patch.object(Path, "mkdir") as mkdir:
                        with self.assertRaises(build.BuildError):
                            build.main([])
                    select_python.assert_not_called()
                    run.assert_not_called()
                    mkdir.assert_not_called()

    def test_prepare_rejects_bad_mapping_before_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            with self.assertRaises(build.BuildError):
                build.prepare_artifacts(stage, defaults_path=stage / "missing.json")
            self.assertFalse((stage / "packages").exists())

    def test_freezer_bundles_runtime_resources_and_dynamic_uvicorn_modules(self):
        command = [str(item) for item in build.pyinstaller_command(Path("python.exe"), Path("stage"))]
        self.assertIn("--onefile", command)
        self.assertIn("uvicorn.protocols.http.h11_impl", command)
        self.assertIn("lameenc", command)
        self.assertTrue(any("schema.sql" in item and "backend/jira" in item for item in command))
        self.assertTrue(any("problem.json" in item for item in command))

    def test_checked_paths_reject_outside_targets_and_parent_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in (root, root.parent / "unrelated"):
                with self.assertRaises(build.BuildError):
                    build.checked_path(target, root)
            self.assertEqual(build.checked_path(root / "safe", root), (root / "safe").resolve())

    def prepare_publish(self, root):
        stage = root / "build" / "stage"
        for profile in build.PROFILES:
            package = stage / profile
            previous = root / "dist" / profile
            package.mkdir(parents=True)
            previous.mkdir(parents=True)
            for name in build.ARTIFACTS:
                if name == "public":
                    (package / name).mkdir()
                    (previous / name).mkdir()
                    (package / name / "index.html").write_text("new frontend")
                    (previous / name / "index.html").write_text("old frontend")
                elif name == "port_mapping.json":
                    (package / name).write_text('{"frontend_port": 5100, "backend_port": 8011}')
                    (previous / name).write_text('{"frontend_port": 4100, "backend_port": 7011}')
                else:
                    (package / name).write_text("new " + name)
                    (previous / name).write_text("old " + name)
            (previous / "settings.json").write_text("user settings")
            (previous / "data").mkdir()
            (previous / "data" / "user.db").write_text("user data")
        return stage

    def test_publish_preserves_user_files_in_both_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = self.prepare_publish(root)
            build.publish_artifacts(stage, repository=root)
            for profile in build.PROFILES:
                output = root / "dist" / profile
                self.assertEqual((output / "server.exe").read_text(), "new server.exe")
                self.assertEqual((output / "public" / "index.html").read_text(), "new frontend")
                self.assertEqual(json.loads((output / "port_mapping.json").read_text()), {
                    "frontend_port": 5100, "backend_port": 8011,
                })
                self.assertEqual((output / "settings.json").read_text(), "user settings")
                self.assertEqual((output / "data" / "user.db").read_text(), "user data")

    def test_locked_release_artifact_rolls_back_debug_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = self.prepare_publish(root)
            rename = Path.rename

            def locked_rename(source, target):
                if source == root / "dist" / "Release" / "public":
                    raise PermissionError("Running app locked an artifact")
                return rename(source, target)

            with patch.object(Path, "rename", locked_rename):
                with self.assertRaisesRegex(build.BuildError, "close the running application"):
                    build.publish_artifacts(stage, repository=root)
            for profile in build.PROFILES:
                output = root / "dist" / profile
                self.assertEqual((output / "server.exe").read_text(), "old server.exe")
                self.assertEqual((output / "public" / "index.html").read_text(), "old frontend")
                self.assertEqual((stage / profile / "server.exe").read_text(), "new server.exe")
                self.assertEqual(json.loads((output / "port_mapping.json").read_text()), {
                    "frontend_port": 4100, "backend_port": 7011,
                })

    def test_locked_port_mapping_rolls_back_all_managed_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = self.prepare_publish(root)
            rename = Path.rename

            def locked_rename(source, target):
                if source == root / "dist" / "Release" / "port_mapping.json":
                    raise PermissionError("Port defaults are locked")
                return rename(source, target)

            with patch.object(Path, "rename", locked_rename):
                with self.assertRaises(build.BuildError):
                    build.publish_artifacts(stage, repository=root)
            for profile in build.PROFILES:
                output = root / "dist" / profile
                self.assertEqual((output / "server.exe").read_text(), "old server.exe")
                self.assertEqual((output / "public" / "index.html").read_text(), "old frontend")
                self.assertEqual((output / "settings.json").read_text(), "user settings")
                self.assertEqual((output / "data" / "user.db").read_text(), "user data")
                self.assertEqual(json.loads((output / "port_mapping.json").read_text()), {
                    "frontend_port": 4100, "backend_port": 7011,
                })


if __name__ == "__main__":
    unittest.main()
