"""Speech synthesis using The Connector's speech endpoint.

Connects to The Connector at port 8301 (or configured URL) to generate speech.
Podcasts require successful speech; other callers can use the offline fallback.
"""

from __future__ import annotations

import io
import json
import os
import wave
import httpx

def connector_speech_url() -> str:
    explicit = os.environ.get("CONNECTOR_SPEECH_URL")
    if explicit:
        return explicit
    base = (os.environ.get("CONNECTOR_BASE_URL") or os.environ.get("CONNECTOR_URL")
            or "http://127.0.0.1:8301").rstrip("/").removesuffix("/v1")
    return f"{base}/api/speech"


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


def synthesize_wav(
    text: str, voice: str = "af_heart", timeout: float | None = None, *, strict: bool = False,
) -> bytes:
    """Send each turn's narrator as the Connector's explicit actor setting."""
    cleaned = (text or "").strip()
    if not cleaned:
        if strict:
            raise ValueError("Spoken dialogue must not be empty")
        return make_silent_wav(0.2)
    if timeout is None:
        timeout = float(os.environ.get("CONNECTOR_SPEECH_TIMEOUT_SECONDS", "180"))
    if not 1 <= timeout <= 600:
        raise ValueError("Speech timeout must be between 1 and 600 seconds")

    # 1. Try The Connector speech endpoint
    failure = "The Connector did not return WAV speech. Check its speech service and retry."
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=5), trust_env=False) as client:
            resp = client.post(
                connector_speech_url(),
                json={"content": _connector_content(cleaned), "actor": voice},
            )
            if _is_wav(resp):
                return resp.content
            if resp.status_code != 200:
                failure = f"The Connector speech service returned HTTP {resp.status_code}."
            try:
                payload = resp.json()
                detail = payload.get("detail") if isinstance(payload, dict) else None
                if isinstance(detail, str):
                    failure += f" {detail[:500]}"
            except ValueError:
                pass
    except Exception as error:
        failure = "Cannot render speech through The Connector. Check its speech service and retry."
        if strict:
            raise RuntimeError(failure) from error
    if strict:
        # A podcast must never be marked complete using silence or a different
        # service that bypasses the Connector's narrator configuration.
        raise RuntimeError(failure)

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
