"""Speech synthesis using The Connector's speech endpoint.

Connects to The Connector at port 8301 (or configured URL) to generate speech.
Includes safe fallback audio generation so operations never fail when offline.
"""

from __future__ import annotations

import io
import os
import struct
import wave
import httpx

CONNECTOR_SPEECH_URL = os.environ.get(
    "CONNECTOR_SPEECH_URL",
    os.environ.get("CONNECTOR_URL", "http://127.0.0.1:8301") + "/api/speech"
)
KOKORO_DIRECT_URL = os.environ.get("KOKORO_DIRECT_URL", "http://127.0.0.1:8302/v1/audio/speech")


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
                json={"content": cleaned, "voice": voice},
            )
            if resp.status_code == 200 and resp.content:
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
            if resp.status_code == 200 and resp.content:
                return resp.content
    except Exception:
        pass

    # 3. Graceful fallback silence
    return make_silent_wav(max(0.5, len(cleaned) * 0.05))
