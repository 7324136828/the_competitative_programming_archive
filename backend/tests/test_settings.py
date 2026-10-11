"""Settings persistence, storage selection, and local-only changes."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.app import create_app
from backend import paths, settings


class ApplicationSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=".settings-test-", dir=paths.ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.mapping = self.root / "port_mapping.json"
        self.mapping.write_text('{"frontend_port": 5100, "backend_port": 8011}')
        mapping_lookup = patch.object(settings, "port_mapping_path", return_value=self.mapping)
        mapping_lookup.start()
        self.addCleanup(mapping_lookup.stop)
        environment = patch.dict(os.environ, {
            "APPDATA": str(self.root / "roaming"),
            "TEMP": str(self.root / "temporary"), "TMP": str(self.root / "temporary"),
            "DATABASE_PATH": "", "DB_PATH": "", "JIRA_DB_PATH": "",
            "WORKSPACE_STORAGE_DIR": "", "UPLOAD_DIR": "", "STUDY_PROXY_TOKEN": "",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def application(self, **config):
        app = create_app({
            "TESTING": True, "AUTO_SEED": False,
            "SETTINGS_PATH": str(settings.settings_path()), **config,
        })
        self.addCleanup(app.extensions["submission_jobs"].shutdown)
        self.addCleanup(app.extensions["audio_store"].shutdown)
        return app

    def test_first_start_creates_roaming_settings_and_temp_data(self):
        app = self.application()
        expected = self.root / "temporary" / settings.APP_NAME
        self.assertEqual(settings.settings_path(), self.root / "roaming" / settings.APP_NAME / "settings.json")
        self.assertEqual(json.loads(settings.settings_path().read_text()), {
            "schema_version": 1, "data_dir": "", "frontend_port": 5100, "backend_port": 8011,
        })
        self.assertEqual(app.extensions["database"].path, expected / "jira.db")
        self.assertTrue(app.extensions["draft_store"].directory.is_relative_to(expected))
        self.assertTrue(app.extensions["audio_store"].root.is_relative_to(expected))
        self.assertEqual(Path(app.config["UPLOAD_DIR"]), expected / "uploads")
        body = app.test_client().get("/api/settings").get_json()
        self.assertEqual(body["data_dir"], str(expected))
        self.assertFalse(body["restart_required"])
        self.assertTrue(body["editable"])

    def test_read_defaults_does_not_create_settings_or_data(self):
        self.assertEqual(settings.read_settings(), {
            "schema_version": 1, "data_dir": "", "frontend_port": 5100, "backend_port": 8011,
        })
        self.assertFalse(settings.settings_path().exists())
        self.assertFalse(settings.default_data_dir().exists())

    def test_port_initialization_creates_empty_json_before_populating_ports(self):
        location = settings.settings_path()
        original_write = settings._write_settings
        initial_contents = []

        def observe_write(path, payload):
            initial_contents.append(path.read_text())
            original_write(path, payload)

        with patch("backend.settings._write_settings", side_effect=observe_write):
            payload = settings.initialize_port_settings()
        self.assertEqual(initial_contents, ["{}"])
        self.assertEqual(payload, {"frontend_port": 5100, "backend_port": 8011})
        self.assertEqual(json.loads(location.read_text()), payload)
        self.assertFalse(settings.default_data_dir().exists())

    def test_port_initialization_preserves_existing_keys_and_does_not_validate_data(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        original = {
            "frontend_port": 5200, "schema_version": 7, "data_dir": "relative/data",
            "custom_setting": {"enabled": True},
        }
        location.write_text(json.dumps(original))
        payload = settings.initialize_port_settings()
        self.assertEqual(payload, {**original, "backend_port": 8011})
        self.assertEqual(json.loads(location.read_text()), payload)
        self.assertFalse(settings.default_data_dir().exists())

    def test_existing_complete_port_settings_are_not_rewritten(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        original = '{"frontend_port":5101,"backend_port":8012,"other":true}'
        location.write_text(original)
        self.assertEqual(settings.initialize_port_settings(), {
            "frontend_port": 5101, "backend_port": 8012, "other": True,
        })
        self.assertEqual(location.read_text(), original)

    def test_startup_populates_partial_settings_without_losing_custom_values(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        chosen = self.root / "chosen data"
        original = {"frontend_port": 6000, "data_dir": str(chosen), "other": ["kept"]}
        location.write_text(json.dumps(original))
        self.assertEqual(settings.initialize_settings(), chosen)
        self.assertEqual(json.loads(location.read_text()), {
            **original, "backend_port": 8011, "schema_version": 1,
        })

    def test_invalid_ports_are_reported_without_replacing_settings(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        for key in ("frontend_port", "backend_port"):
            for value in (None, True, False, "5100", 5100.0, 0, -1, 65536, [], {}):
                with self.subTest(key=key, value=value):
                    original = json.dumps({key: value, "other": "kept"})
                    location.write_text(original)
                    for reader in (settings.read_settings, settings.initialize_port_settings, settings.initialize_settings):
                        with self.assertRaisesRegex(ValueError, key):
                            reader()
                        self.assertEqual(location.read_text(), original)
        self.assertFalse(settings.default_data_dir().exists())

    def test_port_limits_are_valid(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        location.write_text('{"frontend_port": 1, "backend_port": 65535}')
        payload = settings.initialize_port_settings()
        self.assertEqual(payload["frontend_port"], 1)
        self.assertEqual(payload["backend_port"], 65535)

    def test_custom_mapping_supplies_defaults_to_read_initialize_and_save(self):
        custom = self.root / "custom_mapping.json"
        custom.write_text('{"frontend_port": 6100, "backend_port": 9011}')
        self.assertEqual(settings.load_port_mapping(custom), {
            "frontend_port": 6100, "backend_port": 9011,
        })
        payload = settings.read_settings(defaults_path=custom)
        self.assertEqual(payload["frontend_port"], 6100)
        self.assertEqual(payload["backend_port"], 9011)
        self.assertFalse(settings.settings_path().exists())
        self.assertEqual(settings.initialize_port_settings(defaults_path=custom), {
            "frontend_port": 6100, "backend_port": 9011,
        })
        settings.settings_path().write_text('{"backend_port": 9012, "other": "kept"}')
        self.assertEqual(settings.initialize_settings(defaults_path=custom), settings.default_data_dir())
        initialized = json.loads(settings.settings_path().read_text())
        self.assertEqual(initialized, {
            "frontend_port": 6100, "backend_port": 9012, "other": "kept", "schema_version": 1, "data_dir": "",
        })
        settings.settings_path().write_text('{"frontend_port": 6101, "other": "kept"}')
        chosen = self.root / "saved data"
        settings.save_data_dir(str(chosen), defaults_path=custom)
        saved = settings.read_settings(defaults_path=custom)
        self.assertEqual(saved, {
            "frontend_port": 6101, "backend_port": 9011, "other": "kept", "schema_version": 1, "data_dir": str(chosen),
        })
        self.assertEqual(settings.configured_data_dir(defaults_path=custom), chosen)

    def test_mapping_change_only_populates_missing_saved_ports(self):
        self.mapping.write_text('{"frontend_port": 6200, "backend_port": 9200}')
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        location.write_text('{"frontend_port": 6201, "other": "kept"}')
        payload = settings.initialize_port_settings()
        self.assertEqual(payload, {"frontend_port": 6201, "backend_port": 9200, "other": "kept"})
        original = location.read_bytes()
        self.mapping.write_text('{"frontend_port": 6300, "backend_port": 9300}')
        self.assertEqual(settings.initialize_port_settings(), payload)
        self.assertEqual(location.read_bytes(), original)

    def test_invalid_or_missing_mapping_does_not_touch_user_settings(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        original = '{"frontend_port": 6000, "backend_port": 9000, "data_dir": "", "other": true}'
        location.write_text(original)
        invalid_contents = (
            None, '{broken', '[]', 'null', '{}', '{"frontend_port": 5100}',
            '{"frontend_port": true, "backend_port": 8011}',
            '{"frontend_port": 5100, "backend_port": "8011"}',
            '{"frontend_port": 5100.0, "backend_port": 8011}',
            '{"frontend_port": 0, "backend_port": 8011}',
            '{"frontend_port": 5100, "backend_port": 65536}',
        )
        readers = (
            settings.read_settings, settings.initialize_port_settings, settings.initialize_settings,
            lambda: settings.save_data_dir(str(self.root / "unused data")),
        )
        for contents in invalid_contents:
            with self.subTest(contents=contents):
                if contents is None:
                    self.mapping.unlink()
                else:
                    self.mapping.write_text(contents)
                for reader in readers:
                    with self.assertRaises((ValueError, OSError)) as error:
                        reader()
                    self.assertIn(str(self.mapping), str(error.exception))
                    self.assertEqual(location.read_text(), original)
                untouched = self.root / "uncreated roaming" / "settings.json"
                with self.assertRaises((ValueError, OSError)):
                    settings.initialize_port_settings(untouched)
                self.assertFalse(untouched.parent.exists())
        self.assertFalse(settings.default_data_dir().exists())
        self.assertFalse((self.root / "unused data").exists())

    def test_mapping_accepts_port_boundaries_and_same_port_without_fallback(self):
        self.mapping.write_text('{"frontend_port": 1, "backend_port": 65535}')
        self.assertEqual(settings.load_port_mapping(), {"frontend_port": 1, "backend_port": 65535})
        self.mapping.write_text('{"frontend_port": 6200, "backend_port": 6200}')
        self.assertEqual(settings.load_port_mapping(), {"frontend_port": 6200, "backend_port": 6200})

    def test_save_requires_restart_and_preserves_existing_data(self):
        app = self.application()
        client = app.test_client()
        database = app.extensions["database"]
        database.create_problem({"title": "Saved problem", "problem_statements": "Keep this"})
        old_root = Path(app.config["ACTIVE_DATA_DIR"])
        new_root = self.root / "selected storage"
        saved = client.put("/api/settings", json={"data_dir": str(new_root)})
        self.assertEqual(saved.status_code, 200, saved.get_json())
        body = saved.get_json()
        self.assertEqual(body["active_data_dir"], str(old_root))
        self.assertEqual(body["data_dir"], str(new_root))
        self.assertTrue(body["restart_required"])
        self.assertEqual(database.count(), 1)
        self.assertFalse((new_root / "jira.db").exists())
        restarted = self.application()
        self.assertEqual(restarted.extensions["database"].path, new_root / "jira.db")
        self.assertEqual(restarted.extensions["database"].count(), 0)
        self.assertFalse(restarted.test_client().get("/api/settings").get_json()["restart_required"])
        reset = restarted.test_client().put("/api/settings", json={"data_dir": ""})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.get_json()["data_dir"], str(old_root))
        self.assertTrue(reset.get_json()["restart_required"])
        self.assertEqual(database.count(), 1)

    def test_invalid_folder_does_not_replace_settings(self):
        app = self.application()
        client = app.test_client()
        original = settings.settings_path().read_bytes()
        file = self.root / "not-a-directory"
        file.write_text("fixture")
        for value in ("relative/folder", 14, None, str(file), "bad\x00path"):
            with self.subTest(value=value):
                response = client.put("/api/settings", json={"data_dir": value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(settings.settings_path().read_bytes(), original)
        response = client.put("/api/settings", json={"data_dir": "", "extra": True})
        self.assertEqual(response.status_code, 400)

    def test_copied_data_folder_retains_drafts_and_audio_after_restart(self):
        app = self.application()
        problem = app.extensions["database"].create_problem({
            "title": "Portable problem", "problem_statements": "Preserve files when relocating storage.",
        })
        saved = app.extensions["draft_store"].save(problem["id"], "python", "print('preserved')", 0)
        old_root = Path(app.config["ACTIVE_DATA_DIR"])
        old_audio = app.extensions["audio_store"]
        old_audio.root.mkdir(parents=True, exist_ok=True)
        audio_key = "a" * 64
        (old_audio.root / f"{audio_key}.mp3").write_bytes(b"fixture narration")
        new_root = self.root / "relocated data"
        shutil.copytree(old_root, new_root)
        settings.save_data_dir(str(new_root))
        restarted = self.application()
        drafts = restarted.extensions["draft_store"]
        self.assertEqual(drafts.get(problem["id"], "python"), saved)
        audio = restarted.extensions["audio_store"]
        self.assertEqual(audio.path_for(audio_key).read_bytes(), b"fixture narration")
        self.assertEqual(
            drafts.directory.relative_to(new_root),
            app.extensions["draft_store"].directory.relative_to(old_root),
        )

    def test_external_database_override_uses_absolute_workspace_identity(self):
        database = self.root / "external.sqlite"
        first_root = self.root / "first data"
        second_root = self.root / "second data"
        first = paths.default_storage_path(database, first_root)
        second = paths.default_storage_path(database, second_root)
        self.assertEqual(first.name, second.name)
        other = paths.default_storage_path(self.root / "other.sqlite", first_root)
        self.assertNotEqual(first.name, other.name)

    def test_unwritable_folder_and_atomic_write_failure_keep_previous_settings(self):
        self.application()
        original = settings.settings_path().read_bytes()
        with patch("backend.settings.tempfile.TemporaryFile", side_effect=PermissionError("no write")):
            with self.assertRaisesRegex(ValueError, "not writable"):
                settings.save_data_dir(str(self.root / "read-only"))
        self.assertEqual(settings.settings_path().read_bytes(), original)
        with patch("backend.settings.os.replace", side_effect=PermissionError("no replace")):
            with self.assertRaises(PermissionError):
                settings.save_data_dir(str(self.root / "writable"))
        self.assertEqual(settings.settings_path().read_bytes(), original)
        self.assertEqual(list(settings.settings_path().parent.glob(".settings-*")), [])

    def test_invalid_json_is_reported_without_overwriting(self):
        location = settings.settings_path()
        location.parent.mkdir(parents=True)
        location.write_text("{broken json")
        with self.assertRaisesRegex(ValueError, "Invalid settings JSON"):
            settings.initialize_settings()
        self.assertEqual(location.read_text(), "{broken json")

    def test_remote_and_untrusted_proxy_clients_cannot_change_settings(self):
        client = self.application().test_client()
        target = str(self.root / "remote folder")
        cases = [
            ({"REMOTE_ADDR": "192.168.1.20"}, {}),
            ({"REMOTE_ADDR": "192.168.1.20"}, {"X-Forwarded-For": "127.0.0.1"}),
            ({"REMOTE_ADDR": "127.0.0.1"}, {"X-Study-Client-IP": "127.0.0.1", "X-Study-Proxy-Token": "fake"}),
            ({"REMOTE_ADDR": "127.0.0.1"}, {"X-Forwarded-For": "127.0.0.1"}),
            ({"REMOTE_ADDR": "127.0.0.1"}, {"Origin": "https://untrusted.example"}),
        ]
        for environ, headers in cases:
            with self.subTest(environ=environ, headers=headers):
                body = client.get("/api/settings", environ_overrides=environ, headers=headers).get_json()
                self.assertFalse(body["editable"])
                response = client.put("/api/settings", json={"data_dir": target}, environ_overrides=environ, headers=headers)
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Path(target).exists())

    def test_authenticated_proxy_uses_actual_client_address(self):
        client = self.application().test_client()
        with patch.dict(os.environ, {"STUDY_PROXY_TOKEN": "test-shared-token"}):
            headers = {"X-Study-Proxy-Token": "test-shared-token", "X-Study-Client-IP": "192.168.1.20"}
            denied = client.put("/api/settings", json={"data_dir": ""}, headers=headers)
            self.assertEqual(denied.status_code, 403)
            headers["X-Study-Client-IP"] = "::ffff:127.0.0.1"
            headers["Origin"] = "http://localhost:5173"
            allowed = client.put("/api/settings", json={"data_dir": ""}, headers=headers)
            self.assertEqual(allowed.status_code, 200, allowed.get_json())

    def test_explicit_storage_overrides_remain_active_and_reported(self):
        database = self.root / "custom database.sqlite"
        workspace = self.root / "custom workspace"
        upload = self.root / "custom uploads"
        with patch.dict(os.environ, {
            "JIRA_DB_PATH": str(database), "WORKSPACE_STORAGE_DIR": str(workspace), "UPLOAD_DIR": str(upload),
        }):
            app = self.application()
            client = app.test_client()
            response = client.put("/api/settings", json={"data_dir": str(self.root / "new root")})
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertEqual(body["overrides"]["JIRA_DB_PATH"], str(database))
            self.assertEqual(body["overrides"]["WORKSPACE_STORAGE_DIR"], str(workspace))
            self.assertEqual(body["overrides"]["UPLOAD_DIR"], str(upload))
            self.assertEqual(app.extensions["database"].path, database)
            self.assertEqual(app.extensions["draft_store"].directory, workspace / "drafts")
            self.assertEqual(Path(app.config["UPLOAD_DIR"]), upload)

    def test_unified_uploads_and_study_storage_keep_startup_root_after_save(self):
        from backend.app import create_unified_app
        from backend.jira.db import db
        from fastapi.testclient import TestClient

        self.addCleanup(db.reopen, ":memory:")
        with patch.dict(os.environ, {"JIRA_ENV": "", "NODE_ENV": ""}), patch("tempfile.gettempdir", return_value=str(self.root)):
            unified = create_unified_app({
                "TESTING": True, "AUTO_SEED": False,
                "SETTINGS_PATH": str(settings.settings_path()),
            })
        from backend.study import state
        archive = unified.state.archive_app
        self.addCleanup(archive.extensions["submission_jobs"].shutdown)
        self.addCleanup(archive.extensions["audio_store"].shutdown)
        previous_store = state._store
        previous_workspace = state._active_workspace_id
        self.addCleanup(setattr, state, "_store", previous_store)
        self.addCleanup(setattr, state, "_active_workspace_id", previous_workspace)
        client = TestClient(unified)
        active = Path(archive.config["ACTIVE_DATA_DIR"])
        store = state.get_content_store()
        self.assertEqual(store.database, active / "jira.db")
        self.assertEqual(store.voice_dir, active / "voices")
        self.assertEqual(Path(unified.state.upload_dir), active / "uploads")
        body = client.get("/api/settings").json()
        self.assertEqual(body["overrides"], {})
        (Path(unified.state.upload_dir) / "fixture.txt").write_text("old attachment")
        settings.save_data_dir(str(self.root / "pending root"))
        self.assertTrue(client.get("/api/settings").json()["restart_required"])
        self.assertEqual(client.get("/uploads/fixture.txt").text, "old attachment")
        self.assertIs(state.get_content_store(), store)

    def test_study_store_reopens_for_a_different_active_database(self):
        from backend.jira.db import db
        from backend.study import state

        self.addCleanup(db.reopen, ":memory:")
        previous_store = state._store
        self.addCleanup(setattr, state, "_store", previous_store)
        db.reopen(str(self.root / "first.sqlite"))
        first = state.get_content_store()
        db.reopen(str(self.root / "second.sqlite"))
        second = state.get_content_store()
        self.assertIsNot(first, second)
        self.assertEqual(second.database, self.root / "second.sqlite")


class PortMappingLookupTests(unittest.TestCase):
    def test_source_mapping_lookup_ignores_cwd_and_extraction_folder(self):
        expected = Path(settings.__file__).resolve().parent.parent / "port_mapping.json"
        with patch.object(settings.sys, "frozen", False, create=True), patch.object(
            settings.sys, "_MEIPASS", str(paths.ROOT / "extracted"), create=True,
        ), patch.object(Path, "cwd", return_value=paths.ROOT / "elsewhere"):
            self.assertEqual(settings.port_mapping_path(), expected)

    def test_frozen_mapping_lookup_uses_executable_directory(self):
        executable = paths.ROOT / "portable" / "study-platform.exe"
        with patch.object(settings.sys, "frozen", True, create=True), patch.object(
            settings.sys, "executable", str(executable),
        ), patch.object(settings.sys, "_MEIPASS", str(paths.ROOT / "extracted"), create=True), patch.object(
            Path, "cwd", return_value=paths.ROOT / "elsewhere",
        ):
            self.assertEqual(settings.port_mapping_path(), executable.parent / "port_mapping.json")


if __name__ == "__main__":
    unittest.main()
