"""Podcast generation and rendering module.

Combines script turn speech synthesized via The Connector into podcast audio files.
"""

from __future__ import annotations

import io
import json
import logging
import wave
from pathlib import Path
from typing import Any

from .tts import synthesize_wav, make_silent_wav

logger = logging.getLogger("uvicorn.error")


def combine_wavs(wav_bytes_list: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte chunks of identical format into a single WAV buffer."""
    if not wav_bytes_list:
        return make_silent_wav(1.0)

    frames = bytearray()
    sample_rate = 24000
    nchannels = 1
    sampwidth = 2

    for raw in wav_bytes_list:
        try:
            with wave.open(io.BytesIO(raw), 'rb') as w:
                nchannels = w.getnchannels()
                sampwidth = w.getsampwidth()
                sample_rate = w.getframerate()
                frames.extend(w.readframes(w.getnframes()))
        except Exception:
            pass

    out_buf = io.BytesIO()
    with wave.open(out_buf, 'wb') as out_w:
        out_w.setnchannels(nchannels)
        out_w.setsampwidth(sampwidth)
        out_w.setframerate(sample_rate)
        out_w.writeframes(frames)
    return out_buf.getvalue()


def render_podcast_script(script_data: dict[str, Any], voice_a: str = "af_heart", voice_b: str = "am_adam") -> bytes:
    """Render a parsed podcast JSON script into a combined WAV audio buffer."""
    cast = script_data.get("cast", [])
    speaker_voices: dict[str, str] = {}
    if len(cast) > 0:
        speaker_voices[cast[0].get("speaker_id", "speaker1")] = cast[0].get("voice", voice_a)
    if len(cast) > 1:
        speaker_voices[cast[1].get("speaker_id", "speaker2")] = cast[1].get("voice", voice_b)

    audio_segments: list[bytes] = []
    pause = make_silent_wav(0.4)

    for segment in script_data.get("script", []):
        for scene in segment.get("scenes", []):
            dialogue = scene.get("dialogue", "").strip()
            if not dialogue:
                continue
            speaker_id = scene.get("speaker_id", "")
            voice = speaker_voices.get(speaker_id, voice_a)
            turn_audio = synthesize_wav(dialogue, voice=voice)
            audio_segments.append(turn_audio)
            audio_segments.append(pause)

    return combine_wavs(audio_segments)
