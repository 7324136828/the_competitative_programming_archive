import copy
import io
import json
import struct
import unittest
import wave
from unittest.mock import patch

import httpx

from backend.study import podcast, tts


SCRIPT = {
    'episode_title': 'Two voices',
    'cast': [{'speaker_id': 'host'}, {'speaker_id': 'guest'}],
    'script': [{'segment_name': 'Discussion', 'scenes': [
        {'speaker_id': 'host', 'dialogue': 'Welcome to our discussion.'},
        {'speaker_id': 'guest', 'dialogue': 'Welcome to our discussion.'},
        {'speaker_id': 'host', 'dialogue': 'Let us begin.'},
    ]}],
}


def spoken_wav(marker):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(struct.pack('<100h', *([marker] * 100)))
    return buffer.getvalue()


class PodcastNarrationTests(unittest.TestCase):
    def test_render_sends_two_distinct_actors_through_connector_and_keeps_both_voices(self):
        observed = []
        actual_client = httpx.Client

        def speech_service(request):
            payload = json.loads(request.content)
            observed.append(payload)
            marker = 1000 if payload['actor'] == 'af_heart' else -1000
            return httpx.Response(200, content=spoken_wav(marker), headers={'Content-Type': 'audio/wav'})

        with patch.object(tts.httpx, 'Client', side_effect=lambda **kwargs: actual_client(
            transport=httpx.MockTransport(speech_service), **kwargs,
        )):
            result = podcast.render_podcast_script(SCRIPT)

        self.assertEqual([request['actor'] for request in observed], ['af_heart', 'am_adam', 'af_heart'])
        self.assertEqual(json.loads(observed[0]['content'])['text'], json.loads(observed[1]['content'])['text'])
        with wave.open(io.BytesIO(result), 'rb') as audio:
            samples = struct.unpack(f'<{audio.getnframes()}h', audio.readframes(audio.getnframes()))
        self.assertIn(1000, samples)
        self.assertIn(-1000, samples)

    def test_cast_actor_and_legacy_voice_settings_are_applied(self):
        script = copy.deepcopy(SCRIPT)
        script['cast'][0]['actor'] = 'af_bella'
        script['cast'][0]['voice'] = 'af_heart'
        script['cast'][1]['voice'] = 'am_michael'
        self.assertEqual(podcast.validate_podcast_script(script), {'host': 'af_bella', 'guest': 'am_michael'})

    def test_monologue_and_identical_actor_configuration_are_rejected(self):
        monologue = copy.deepcopy(SCRIPT)
        monologue['script'][0]['scenes'] = [monologue['script'][0]['scenes'][0]]
        with self.assertRaisesRegex(ValueError, 'monologue'):
            podcast.render_podcast_script(monologue)
        with self.assertRaisesRegex(ValueError, 'different voice actors'):
            podcast.render_podcast_script(SCRIPT, 'af_heart', 'af_heart')

    def test_unknown_speaker_is_not_silently_assigned_the_first_narrator(self):
        script = copy.deepcopy(SCRIPT)
        script['script'][0]['scenes'][1]['speaker_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'unknown speaker'):
            podcast.render_podcast_script(script)

    def test_invalid_speech_cannot_be_dropped_from_a_successful_render(self):
        with patch.object(podcast, 'synthesize_wav', side_effect=[spoken_wav(1000), b'not a WAV', spoken_wav(1000)]):
            with self.assertRaisesRegex(ValueError, 'valid WAV'):
                podcast.render_podcast_script(SCRIPT)
