"""Exercise the public draft, archive, and audio routes with isolated storage."""

from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave
import zipfile

from backend.app import create_app
from backend.audio import AudioQueueFull


class WorkspaceAPITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="workspace_api_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {
            "TESTING": True, "AUTO_SEED": False,
            "DATABASE_PATH": str(self.root / "test.sqlite"),
            "WORKSPACE_STORAGE_DIR": str(self.root / "files"),
        }
        self.app = self.make_app()
        self.client = self.app.test_client()
        self.database = self.app.extensions["database"]
        self.problem = self.database.create_problem({
            "title": "Add integers", "problem_statements": "Read two integers and print their sum.",
            "language": "en", "sample_input_output": [{"input": "2 3", "output": "5"}],
        })
        self.base = f'/api/problems/{self.problem["id"]}'

    def make_app(self):
        app = create_app(self.config)
        self.addCleanup(app.extensions["submission_jobs"].shutdown)
        self.addCleanup(app.extensions["audio_store"].shutdown)
        return app

    def test_drafts_survive_restart_and_empty_drafts_are_not_defaults(self):
        endpoint = self.base + "/drafts/python"
        missing = self.client.get(endpoint).get_json()["draft"]
        self.assertIsNone(missing["code"])
        saved = self.client.put(endpoint, json={"code": "", "revision": 0})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["draft"]["code"], "")
        restarted = self.make_app().test_client()
        draft = restarted.get(endpoint).get_json()["draft"]
        self.assertTrue(draft["saved"])
        self.assertEqual(draft["code"], "")
        self.assertEqual(draft["revision"], 1)
        with self.database.connect() as connection:
            reference = connection.execute("SELECT file_path FROM editor_drafts").fetchone()[0]
        self.assertTrue((self.root / "files" / "drafts" / reference).is_file())
        conflict = self.client.put(endpoint, json={"code": "stale", "revision": 0})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.get_json()["draft"]["code"], "")

    def test_bad_draft_requests_and_deleted_problem(self):
        endpoint = self.base + "/drafts/python"
        self.assertEqual(self.client.put(endpoint, json={"code": "x"}).status_code, 400)
        self.assertEqual(self.client.get(self.base + "/drafts/unknown").status_code, 400)
        self.assertEqual(self.client.get("/api/problems/999999/drafts/python").status_code, 404)
        self.client.put(endpoint, json={"code": "draft", "revision": 0})
        self.client.delete("/api/database")
        self.assertEqual(self.client.get(endpoint).status_code, 404)

    def test_history_detail_and_export_cover_all_pages(self):
        for number in range(23):
            last = self.database.save_submission({
                "problem_id": self.problem["id"], "language": "python", "code": f"print({number})",
                "status": "Wrong Answer", "test_results": [],
            })
        page = self.client.get("/api/submissions?page=2&limit=20").get_json()
        self.assertEqual(page["total"], 23)
        self.assertEqual(len(page["submissions"]), 3)
        detail = self.client.get(f'/api/submission-records/{last["id"]}').get_json()["submission"]
        self.assertEqual(detail["code"], "print(22)")
        self.assertEqual(detail["problem_title"], "Add integers")
        self.assertEqual(self.client.get("/api/submission-records/999999").status_code, 404)
        exported = self.client.get("/api/submissions/export.zip")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        with zipfile.ZipFile(BytesIO(exported.data)) as archive:
            source_files = [name for name in archive.namelist() if name.endswith("/source.py")]
            self.assertEqual(len(source_files), 23)
            self.assertIn(b"print(22)", [archive.read(name) for name in source_files])

    def test_audio_job_encodes_mp3_and_reuses_disk_cache_after_restart(self):
        wav = BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\x00\x00" * 2400)
        store = self.app.extensions["audio_store"]
        self.assertEqual(self.client.get(self.base + "/audio").get_json()["audio"]["status"], "missing")
        with patch.object(store, "_wav", return_value=wav.getvalue()) as speech:
            response = self.client.post(self.base + "/audio")
            self.assertIn(response.status_code, (200, 202))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                audio = self.client.get(self.base + "/audio").get_json()["audio"]
                if audio["done"]:
                    break
                time.sleep(0.01)
            self.assertEqual(audio["status"], "ready", audio)
            speech.assert_called_once()
        with self.client.get(audio["url"]) as mp3:
            self.assertEqual(mp3.mimetype, "audio/mpeg")
            self.assertGreater(len(mp3.data), 100)
            self.assertFalse(mp3.data.startswith(b"RIFF"))
        with self.client.get(audio["url"], headers={"Range": "bytes=0-15"}) as partial:
            self.assertEqual(partial.status_code, 206)
            self.assertEqual(len(partial.data), 16)
        restarted = self.make_app()
        with patch.object(restarted.extensions["audio_store"], "_wav", side_effect=AssertionError("cache miss")):
            cached = restarted.test_client().post(self.base + "/audio")
            self.assertEqual(cached.status_code, 200)
            self.assertEqual(cached.get_json()["audio"]["url"], audio["url"])
        self.assertEqual(self.client.get("/api/audio/invalid.mp3").status_code, 404)

    def test_full_audio_queue_reports_retryable_error(self):
        with patch.object(self.app.extensions["audio_store"], "start", side_effect=AudioQueueFull("Busy")):
            response = self.client.post(self.base + "/audio")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "2")

    def test_response_audio_persists_and_settings_cleanup_preserves_drafts(self):
        wav = BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\x00\x00" * 2400)
        store = self.app.extensions["audio_store"]
        payload = {"text": "### Checksum\nAdd positions using $N + 1$.", "language": "en"}
        self.client.put(self.base + "/drafts/python", json={"code": "print(5)", "revision": 0})
        with patch.object(store, "_wav", return_value=wav.getvalue()) as speech:
            response = self.client.post("/api/audio/responses", json=payload)
            self.assertIn(response.status_code, (200, 202))
            key = response.get_json()["audio"]["key"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                audio = self.client.get(f"/api/audio/responses/{key}").get_json()["audio"]
                if audio["done"]:
                    break
                time.sleep(0.01)
            self.assertEqual(audio["status"], "ready", audio)
            speech.assert_called_once()
            self.assertIn("Checksum", speech.call_args.args[0]["input"])
        restarted = self.make_app().test_client()
        self.assertEqual(restarted.post("/api/audio/responses", json=payload).status_code, 200)
        with patch("backend.app.send_file", side_effect=FileNotFoundError("concurrent cleanup")):
            self.assertEqual(restarted.get(audio["url"]).status_code, 404)
        with restarted.get(audio["url"]) as mp3:
            self.assertEqual(mp3.mimetype, "audio/mpeg")
            self.assertIn("max-age=0", mp3.headers["Cache-Control"])
        stats = restarted.get("/api/audio/cache").get_json()["cache"]
        self.assertEqual(stats["files"], 1)
        self.assertGreater(stats["bytes"], 100)
        removed = restarted.delete("/api/audio/cache").get_json()["cache"]
        self.assertEqual(removed["removedFiles"], 1)
        self.assertEqual(removed["removedBytes"], stats["bytes"])
        self.assertEqual(removed["files"], 0)
        self.assertEqual(restarted.get(audio["url"]).status_code, 404)
        self.assertEqual(restarted.get(f"/api/audio/responses/{key}").get_json()["audio"]["status"], "missing")
        self.assertEqual(restarted.get(self.base + "/drafts/python").get_json()["draft"]["code"], "print(5)")
        self.assertEqual(restarted.get(self.base).status_code, 200)

    def test_response_audio_validation_and_busy_status(self):
        for payload in (None, {}, {"text": " "}, {"text": {}}, {"text": "Read", "language": []},
                        {"text": "Read", "language": "xx"}, {"text": "x" * 40_001}):
            with self.subTest(payload_type=type(payload).__name__):
                self.assertEqual(self.client.post("/api/audio/responses", json=payload).status_code, 400)
        with patch.object(self.app.extensions["audio_store"], "start_text", side_effect=AudioQueueFull("Busy")):
            response = self.client.post("/api/audio/responses", json={"text": "Read"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "2")


if __name__ == "__main__":
    unittest.main()
