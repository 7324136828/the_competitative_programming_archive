"""Podcast generation and rendering module.

Combines script turn speech synthesized via The Connector into podcast audio files.
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Any

from .tts import synthesize_wav, make_silent_wav

logger = logging.getLogger("uvicorn.error")


def combine_wavs(wav_bytes_list: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte chunks of identical format into a single WAV buffer."""
    if not wav_bytes_list:
        raise ValueError("Podcast has no rendered speech")

    frames = bytearray()
    sample_rate = 24000
    nchannels = 1
    sampwidth = 2
    audio_format = None

    for raw in wav_bytes_list:
        try:
            with wave.open(io.BytesIO(raw), 'rb') as w:
                current_format = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                if audio_format is not None and current_format != audio_format:
                    raise ValueError("Podcast speech returned incompatible WAV formats")
                audio_format = current_format
                nchannels, sampwidth, sample_rate = current_format
                chunk = w.readframes(w.getnframes())
                if not chunk or len(chunk) != w.getnframes() * nchannels * sampwidth:
                    raise ValueError("Podcast speech returned empty or incomplete audio")
                frames.extend(chunk)
        except (wave.Error, EOFError) as error:
            raise ValueError("Podcast speech service did not return valid WAV audio") from error

    out_buf = io.BytesIO()
    with wave.open(out_buf, 'wb') as out_w:
        out_w.setnchannels(nchannels)
        out_w.setsampwidth(sampwidth)
        out_w.setframerate(sample_rate)
        out_w.writeframes(frames)
    return out_buf.getvalue()


def validate_podcast_script(
    script_data: dict[str, Any], voice_a: str = "af_heart", voice_b: str = "am_adam",
) -> dict[str, str]:
    """Require dialogue from at least two speakers with distinct voice actors."""
    if not isinstance(script_data, dict):
        raise ValueError("Podcast script must be an object")
    cast = script_data.get("cast")
    if not isinstance(cast, list) or len(cast) < 2:
        raise ValueError("Podcast needs at least two narrators in its cast")
    if not all(isinstance(voice, str) and voice.strip() for voice in (voice_a, voice_b)):
        raise ValueError("Choose a voice actor for each narrator")
    speaker_voices: dict[str, str] = {}
    for index, member in enumerate(cast):
        if not isinstance(member, dict):
            raise ValueError("Each podcast narrator must be an object")
        speaker_id = member.get("speaker_id")
        if not isinstance(speaker_id, str) or not speaker_id.strip() or speaker_id in speaker_voices:
            raise ValueError("Podcast narrators need unique speaker IDs")
        actor = member.get("actor")
        if actor is None:
            actor = member.get("voice")
        if actor is None:
            actor = voice_a if index % 2 == 0 else voice_b
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("Each podcast narrator needs a valid voice actor")
        speaker_voices[speaker_id] = actor.strip()

    script = script_data.get("script")
    if not isinstance(script, list):
        raise ValueError("Podcast script must contain dialogue segments")
    active_speakers = set()
    for segment in script:
        if not isinstance(segment, dict) or not isinstance(segment.get("scenes"), list):
            raise ValueError("Each podcast segment must contain dialogue scenes")
        for scene in segment["scenes"]:
            if not isinstance(scene, dict) or not isinstance(scene.get("dialogue", ""), str):
                raise ValueError("Podcast dialogue must be text")
            if not scene.get("dialogue", "").strip():
                continue
            speaker_id = scene.get("speaker_id")
            if not isinstance(speaker_id, str) or speaker_id not in speaker_voices:
                raise ValueError("Podcast dialogue references an unknown speaker")
            active_speakers.add(speaker_id)
    if len(active_speakers) < 2:
        raise ValueError("Podcast dialogue must include at least two speakers; this script is a monologue")
    if len({speaker_voices[speaker] for speaker in active_speakers}) < 2:
        raise ValueError("Choose different voice actors for the podcast's two narrators")
    return speaker_voices


def render_podcast_script(script_data: dict[str, Any], voice_a: str = "af_heart", voice_b: str = "am_adam") -> bytes:
    """Render each narrator's dialogue through the Connector using its actor ID."""
    speaker_voices = validate_podcast_script(script_data, voice_a, voice_b)

    audio_segments: list[bytes] = []
    pause = make_silent_wav(0.4)

    for segment in script_data.get("script", []):
        for scene in segment.get("scenes", []):
            dialogue = scene.get("dialogue", "").strip()
            if not dialogue:
                continue
            speaker_id = scene.get("speaker_id", "")
            voice = speaker_voices[speaker_id]
            turn_audio = synthesize_wav(dialogue, voice=voice, strict=True)
            audio_segments.append(turn_audio)
            audio_segments.append(pause)

    return combine_wavs(audio_segments)
