"""Narration queue, cache and Connector speech/MP3 boundary regressions."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import httpx

from backend.audio import AudioError, AudioQueueFull, AudioStore, MAX_TEXT_CHARS, narration_text, wav_to_mp3


PROBLEM = {"id": 1, "title": "Add two numbers", "problem_statements": "Read **a** and **b**. Print their sum.", "language": "en"}
FAKE_MP3 = b"\xff\xfb\x90\x00mock-encoded-audio"


def example_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(b"\x10\x00" * 2400)
    return output.getvalue()


class AudioStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="narration_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio = AudioStore(self.root, max_pending=1)
        self.addCleanup(self.audio.shutdown)

    def test_generation_is_async_deduplicated_and_persisted_across_restart(self):
        entered, release = threading.Event(), threading.Event()

        def slow_service(payload):
            entered.set()
            self.assertTrue(release.wait(5))
            self.assertEqual(list(payload), ["content"])
            self.assertIn("Add two numbers", payload["content"])
            return example_wav()

        self.addCleanup(release.set)
        with patch.object(self.audio, "_wav", side_effect=slow_service) as service, patch("backend.audio.wav_to_mp3", return_value=FAKE_MP3):
            self.assertEqual(self.audio.get(PROBLEM)["status"], "missing")
            queued = self.audio.start(PROBLEM)
            self.assertFalse(queued["done"])
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.audio.start(PROBLEM)["key"], queued["key"])
            self.assertEqual(self.audio.get(PROBLEM)["status"], "generating")
            self.assertIsNone(self.audio.path_for(queued["key"]))
            with self.assertRaises(AudioQueueFull):
                self.audio.start({**PROBLEM, "title": "Different problem"})
            release.set()
            self.audio.shutdown()
        service.assert_called_once()
        complete = self.audio.get(PROBLEM)
        self.assertEqual(complete["status"], "ready")
        self.assertTrue(complete["cached"])
        self.assertEqual(self.audio.path_for(complete["key"]).read_bytes(), FAKE_MP3)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        restarted = AudioStore(self.root)
        self.addCleanup(restarted.shutdown)
        with patch.object(restarted, "_wav") as service:
            self.assertEqual(restarted.start(PROBLEM), complete)
        service.assert_not_called()

    def test_content_endpoint_and_source_language_changes_invalidate_cache(self):
        original = self.audio.get(PROBLEM)["key"]
        for field, value in (("title", "Another title"), ("problem_statements", "Print the product.")):
            self.assertNotEqual(self.audio.get({**PROBLEM, field: value})["key"], original)
        self.assertNotEqual(self.audio.get({**PROBLEM, "language": "fr"})["key"], original)
        configured = AudioStore(self.root, base_url="http://127.0.0.1:8401/v1")
        self.addCleanup(configured.shutdown)
        self.assertNotEqual(configured.get(PROBLEM)["key"], original)

    def test_response_narration_persists_and_can_be_polled_by_key(self):
        response = '## Explanation\nThe bound is $4 \\le N \\le 1000$.\n```json\n{"answer": 42}\n```'
        entered, release = threading.Event(), threading.Event()

        def service(payload):
            self.assertIn("less than or equal to", payload["content"])
            self.assertIn('"answer": 42', payload["content"])
            self.assertNotIn("```", payload["content"])
            entered.set()
            self.assertTrue(release.wait(5))
            return example_wav()

        self.addCleanup(release.set)
        with patch.object(self.audio, "_wav", side_effect=service) as speech, patch("backend.audio.wav_to_mp3", return_value=FAKE_MP3):
            self.assertEqual(self.audio.get_text(response)["status"], "missing")
            queued = self.audio.start_text(response)
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.audio.start_text(response)["key"], queued["key"])
            self.assertEqual(self.audio.get_by_key(queued["key"])["status"], "generating")
            release.set()
            self.audio.shutdown()
        speech.assert_called_once()
        self.assertEqual(self.audio.get_text(response)["status"], "ready")
        restarted = AudioStore(self.root)
        self.addCleanup(restarted.shutdown)
        with patch.object(restarted, "_wav") as speech:
            self.assertEqual(restarted.start_text(response)["status"], "ready")
        speech.assert_not_called()
        self.assertEqual(restarted.get_by_key(queued["key"])["status"], "ready")

    def test_response_text_language_and_poll_key_are_validated(self):
        for value in (None, 4, {}, [], "", "  ", "a" * (MAX_TEXT_CHARS + 1)):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                self.audio.start_text(value)
        for language in (None, {}, "", "x" * 31):
            with self.subTest(language=language), self.assertRaises(ValueError):
                self.audio.get_text("Hello", language)
        for key in (None, "../outside", "a" * 63, "A" * 64):
            with self.assertRaises(ValueError):
                self.audio.get_by_key(key)
        self.assertEqual(self.audio.get_by_key("0" * 64)["status"], "missing")
        self.assertNotEqual(self.audio.get_text("Hello", "en")["key"], self.audio.get_text("Hello", "en-gb")["key"])

    def test_math_speech_conversion_preserves_fenced_and_inline_code(self):
        text = narration_text({"description": (
            r"The ratio is $\frac{a}{b}$ and \(x^2 \to y^3\). "
            r"The limit is \[N \le 1000\]. Keep `value = '$x^2$'`."
            '\n```json\n{"price":"$4$","path":"C:\\\\temp"}\n```'
            '\n```cpp\nvector<int> values; // $x^2$\n```'
        )})
        self.assertIn("(a) divided by (b)", text)
        self.assertIn("x squared to y cubed", text)
        self.assertIn("N less than or equal to 1000", text)
        self.assertIn("value = '$x^2$'", text)
        self.assertIn('"price":"$4$"', text)
        self.assertIn('"path":"C:\\\\temp"', text)
        self.assertIn("vector<int> values; // $x^2$", text)
        bare_json = '{"price":"$4$","formula":"$x^2$","path":"C:\\\\temp"}'
        self.assertEqual(narration_text({"description": bare_json}), bare_json)

    def test_clear_cache_counts_owned_files_and_preserves_other_workspace_files(self):
        first, second = self.root / ("a" * 64 + ".mp3"), self.root / ("b" * 64 + ".mp3")
        first.write_bytes(FAKE_MP3)
        second.write_bytes(b"partial")
        unrelated = [self.root / "notes.mp3", self.root / "draft.cpp", self.root / ("c" * 64 + ".tmp")]
        for path in unrelated:
            path.write_text("preserve")
        nested = self.root / ("d" * 64 + ".mp3")
        nested.mkdir()
        (nested / "nested.mp3").write_text("preserve")
        expected_bytes = len(FAKE_MP3) + len(b"partial")
        self.assertEqual(self.audio.cache_info(), {"files": 2, "bytes": expected_bytes})
        self.assertEqual(self.audio.clear_cache(), {"removedFiles": 2, "removedBytes": expected_bytes, "files": 0, "bytes": 0})
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        for path in unrelated:
            self.assertEqual(path.read_text(), "preserve")
        self.assertEqual((nested / "nested.mp3").read_text(), "preserve")
        self.assertEqual(self.audio.clear_cache()["removedFiles"], 0)

    def test_cache_never_follows_or_removes_symlinks(self):
        original = self.root / "keep.mp3"
        original.write_bytes(FAKE_MP3)
        symlink = self.root / ("a" * 64 + ".mp3")
        try:
            symlink.symlink_to(original)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this system")
        self.assertIsNone(self.audio.path_for("a" * 64))
        self.assertEqual(self.audio.cache_info(), {"files": 0, "bytes": 0})
        self.audio.clear_cache()
        self.assertTrue(symlink.is_symlink())
        self.assertEqual(original.read_bytes(), FAKE_MP3)

    def test_clear_during_generation_prevents_audio_from_reappearing(self):
        entered, release = threading.Event(), threading.Event()

        def slow_service(payload):
            entered.set()
            self.assertTrue(release.wait(5))
            return example_wav()

        self.addCleanup(release.set)
        with patch.object(self.audio, "_wav", side_effect=slow_service), patch("backend.audio.wav_to_mp3", return_value=FAKE_MP3):
            queued = self.audio.start_text("A response being spoken.")
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.audio.clear_cache()["files"], 0)
            self.assertEqual(self.audio.get_by_key(queued["key"])["status"], "missing")
            release.set()
            self.audio.shutdown()
        self.assertIsNone(self.audio.path_for(queued["key"]))
        self.assertEqual(self.audio.cache_info(), {"files": 0, "bytes": 0})

    def test_clear_cancels_queued_jobs_and_old_failure_does_not_replace_new_request(self):
        audio = AudioStore(self.root, max_pending=2)
        self.addCleanup(audio.shutdown)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []

        def slow_service(payload):
            calls.append(payload["content"])
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(5))
                raise AudioError("Old generation failed after clearing")
            return example_wav()

        with patch.object(audio, "_wav", side_effect=slow_service), patch("backend.audio.wav_to_mp3", return_value=FAKE_MP3):
            first = audio.start_text("Regenerate this response.")
            self.assertTrue(entered.wait(5))
            canceled = audio.start_text("Cancel this queued response.")
            audio.clear_cache()
            new = audio.start_text("Regenerate this response.")
            self.assertEqual(first["key"], new["key"])
            self.assertEqual(audio.get_by_key(new["key"])["status"], "queued")
            release.set()
            audio.shutdown()
        self.assertEqual(len(calls), 2)
        self.assertEqual(audio.get_by_key(new["key"])["status"], "ready")
        self.assertEqual(audio.get_by_key(canceled["key"])["status"], "missing")
        self.assertEqual(audio.cache_info()["files"], 1)

    def test_cleanup_and_inventory_filesystem_errors_are_reported(self):
        owned = self.root / ("a" * 64 + ".mp3")
        owned.write_bytes(FAKE_MP3)
        with patch.object(Path, "unlink", side_effect=PermissionError("busy file")):
            with self.assertRaisesRegex(AudioError, "Unable to clear"):
                self.audio.clear_cache()
        self.assertTrue(owned.exists())
        with patch.object(Path, "iterdir", side_effect=PermissionError("folder unavailable")):
            with self.assertRaisesRegex(AudioError, "Unable to inspect"):
                self.audio.cache_info()

    def test_failed_generation_is_visible_and_can_be_retried(self):
        with patch.object(self.audio, "_wav", side_effect=AudioError("Speech service unavailable")), self.assertLogs("backend.audio", level="ERROR"):
            result = self.audio.start(PROBLEM)
            self.audio.shutdown()
        failed = self.audio.get(PROBLEM)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["done"])
        self.assertIn("unavailable", failed["error"])
        self.assertIsNone(self.audio.path_for(result["key"]))
        restarted = AudioStore(self.root)
        self.addCleanup(restarted.shutdown)
        with patch.object(restarted, "_wav", return_value=example_wav()), patch("backend.audio.wav_to_mp3", return_value=FAKE_MP3):
            restarted.start(PROBLEM)
            restarted.shutdown()
        self.assertEqual(restarted.get(PROBLEM)["status"], "ready")

    def test_invalid_file_keys_cannot_escape_audio_directory(self):
        for key in ("../secrets", "a" * 64 + "/../secret", "A" * 64, "a" * 63, None):
            self.assertIsNone(self.audio.path_for(key))

    def test_connector_owns_language_and_voice_configuration(self):
        _, generated = self.audio._request({**PROBLEM, "language": "zh-CN"})
        self.assertEqual(list(generated), ["content"])
        self.assertIn("Add two numbers", generated["content"])

    def test_http_contract_requests_wav_and_encodes_only_valid_payloads(self):
        actual_client = httpx.Client
        observed = []

        def service(request):
            observed.append(request)
            return httpx.Response(200, content=example_wav(), headers={"Content-Type": "audio/wav"})

        with patch("backend.audio.httpx.Client", side_effect=lambda **kwargs: actual_client(transport=httpx.MockTransport(service), **kwargs)):
            _, payload = self.audio._request(PROBLEM)
            self.assertEqual(self.audio._wav(payload), example_wav())
        self.assertEqual(str(observed[0].url), "http://127.0.0.1:8301/api/speech")
        self.assertEqual(json.loads(observed[0].content), {"content": narration_text(PROBLEM)})

    def test_service_http_error_is_bounded_and_actionable(self):
        actual_client = httpx.Client
        transport = httpx.MockTransport(lambda _: httpx.Response(500, content=b"private traceback" * 1000))
        with patch("backend.audio.httpx.Client", side_effect=lambda **kwargs: actual_client(transport=transport, **kwargs)):
            with self.assertRaisesRegex(AudioError, "Connector speech endpoint returned HTTP 500") as error:
                self.audio._wav({})
        self.assertNotIn("private traceback", str(error.exception))

        rejected = httpx.MockTransport(lambda _: httpx.Response(422, content=b"private validation detail"))
        with patch("backend.audio.httpx.Client", side_effect=lambda **kwargs: actual_client(transport=rejected, **kwargs)):
            with self.assertRaisesRegex(AudioError, "non-empty plain text") as error:
                self.audio._wav({"content": ""})
        self.assertNotIn("private validation detail", str(error.exception))

    def test_invalid_or_empty_audio_is_rejected(self):
        for invalid in (b"not audio", b"RIFF", b"<html>error</html>"):
            with self.assertRaises(AudioError):
                wav_to_mp3(invalid)
        with self.assertRaises(ValueError):
            self.audio.start({**PROBLEM, "problem_statements": ""})

    def test_prose_retains_constraints_and_drops_formatting(self):
        text = narration_text({"title": "Test", "problem_statements": "# Task\n<p>Given a < b and n &lt; 10.</p>\nRead **a** and [b](https://example.com).\n```cpp\nx = 1;\n```"})
        self.assertIn("a < b", text)
        self.assertIn("n < 10", text)
        self.assertIn("Read a and b.", text)
        self.assertIn("x = 1;", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("```", text)

    def test_html_cleanup_preserves_cpp_types_and_compact_comparisons(self):
        text = narration_text({"problem_statements": (
            '<p class="statement" data-kind="description">Use <strong title="container">vector<int></strong> '
            'when a<b and b>c; require 0<p and p>0.</p>'
            '<div id=limits>Check <span style="color: red">n&lt;10</span>.</div>'
        )})
        self.assertIn("vector<int>", text)
        self.assertIn("a<b and b>c", text)
        self.assertIn("0<p and p>0", text)
        self.assertIn("n<10", text)
        self.assertNotIn("<strong", text)
        self.assertNotIn("<p class", text)
        self.assertNotIn("<div", text)
        self.assertNotIn("<span", text)

    @unittest.skipUnless(importlib.util.find_spec("lameenc"), "lameenc is not installed")
    def test_real_encoder_produces_mp3_bytes_from_service_wav(self):
        mp3 = wav_to_mp3(example_wav())
        self.assertGreater(len(mp3), 200)
        self.assertNotEqual(mp3[:4], b"RIFF")
        self.assertTrue(mp3.startswith(b"ID3") or mp3[0] == 0xFF and mp3[1] & 0xE0 == 0xE0)


if __name__ == "__main__":
    unittest.main()
