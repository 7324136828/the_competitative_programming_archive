"""Speech synthesis using The Connector's speech endpoint.

Connects to The Connector at port 8301 (or configured URL) to generate speech.
Includes safe fallback audio generation so operations never fail when offline.
"""

from __future__ import annotations

import io
import json
import os
import struct
import wave
import httpx

CONNECTOR_SPEECH_URL = os.environ.get(
    "CONNECTOR_SPEECH_URL",
    os.environ.get("CONNECTOR_URL", "http://127.0.0.1:8301") + "/api/speech"
)
KOKORO_DIRECT_URL = os.environ.get("KOKORO_DIRECT_URL", "http://127.0.0.1:8302/v1/audio/speech")


def _connector_content(text: str) -> str:
    """Wrap all study text so JSON-looking flashcards cannot be rejected."""
    return json.dumps({"text": text}, ensure_ascii=False)


def _is_wav(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    return (
        response.status_code == 200
        and bool(response.content)
        and (content_type == "audio/wav" or response.content.startswith(b"RIFF"))
    )


def make_silent_wav(duration_seconds: float = 0.5, sample_rate: int = 24000) -> bytes:
    """Generate a valid PCM 16-bit mono WAV buffer containing silence."""
    num_samples = int(duration_seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b'\x00\x00' * num_samples)
    return buf.getvalue()


def synthesize_wav(text: str, voice: str = "af_heart", timeout: float = 15.0) -> bytes:
    """Synthesize speech audio for the given text using The Connector."""
    cleaned = (text or "").strip()
    if not cleaned:
        return make_silent_wav(0.2)

    # 1. Try The Connector speech endpoint
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                CONNECTOR_SPEECH_URL,
                # Voice/language configuration belongs to The Connector. Its
                # public contract accepts only the complete content string.
                json={"content": _connector_content(cleaned)},
            )
            if _is_wav(resp):
                return resp.content
    except Exception:
        pass

    # 2. Try Kokoro direct endpoint
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                KOKORO_DIRECT_URL,
                json={"input": cleaned, "voice": voice, "response_format": "wav"},
            )
            if _is_wav(resp):
                return resp.content
    except Exception:
        pass

    # 3. Graceful fallback silence
    return make_silent_wav(max(0.5, len(cleaned) * 0.05))
