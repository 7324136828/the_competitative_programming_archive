import json
import unittest
from unittest.mock import MagicMock, patch

from backend.study import tts


def client_with_response(status: int, content: bytes) -> tuple[MagicMock, MagicMock]:
    response = MagicMock(status_code=status, content=content, headers={"content-type": "audio/wav"})
    client = MagicMock()
    client.post.return_value = response
    context = MagicMock()
    context.__enter__.return_value = client
    context.__exit__.return_value = False
    return context, client


class StudySpeechTests(unittest.TestCase):
    def test_connector_request_passes_content_and_selected_actor(self):
        context, client = client_with_response(200, b"connector-wav")
        with patch.object(tts.httpx, "Client", return_value=context):
            result = tts.synthesize_wav("Explain the result.", voice="af_heart")

        self.assertEqual(result, b"connector-wav")
        client.post.assert_called_once_with(
            tts.connector_speech_url(),
            json={"content": json.dumps({"text": "Explain the result."}), "actor": "af_heart"},
        )

    def test_json_like_study_text_is_wrapped_as_eligible_speech_content(self):
        context, client = client_with_response(200, b"connector-wav")
        with patch.object(tts.httpx, "Client", return_value=context):
            tts.synthesize_wav("42")

        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(json.loads(payload["content"]), {"text": "42"})

    def test_direct_kokoro_fallback_retains_requested_voice(self):
        connector_context, connector = client_with_response(503, b"")
        kokoro_context, kokoro = client_with_response(200, b"kokoro-wav")
        with patch.object(tts.httpx, "Client", side_effect=[connector_context, kokoro_context]):
            result = tts.synthesize_wav("Fallback speech", voice="am_adam")

        self.assertEqual(result, b"kokoro-wav")
        self.assertEqual(connector.post.call_args.kwargs["json"]["actor"], "am_adam")
        self.assertEqual(kokoro.post.call_args.kwargs["json"]["voice"], "am_adam")

    def test_podcast_speech_failure_is_reported_without_silence_or_direct_fallback(self):
        context, _ = client_with_response(503, b'')
        with patch.object(tts.httpx, "Client", return_value=context) as client:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 503'):
                tts.synthesize_wav('Narrator dialogue', voice='am_adam', strict=True)
        self.assertEqual(client.call_count, 1)

    def test_speech_uses_configured_connector_base_url(self):
        with patch.dict(tts.os.environ, {'CONNECTOR_BASE_URL': 'http://localhost:8401/v1', 'CONNECTOR_SPEECH_URL': ''}):
            self.assertEqual(tts.connector_speech_url(), 'http://localhost:8401/api/speech')


if __name__ == "__main__":
    unittest.main()
