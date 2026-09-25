"""Generate persistent MP3 narration through The Connector speech skill.

The web process does not import Kokoro or call its private service. Its one
bounded worker requests 16-bit WAV from The Connector and encodes MP3 with
LAME. Content-addressed files survive application restarts; unfinished jobs
can retry.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html import unescape
import io
import json
import logging
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from urllib.parse import urlsplit, urlunsplit
import wave

import httpx


logger = logging.getLogger(__name__)
MAX_TEXT_CHARS = 40_000
MAX_WAV_BYTES = 96 * 1024 * 1024
KEY_PATTERN = re.compile(r"[0-9a-f]{64}")
# Require known element names and explicit attribute assignments. Generic
# '<...>' stripping mistakes C++ types and compact inequalities for HTML.
HTML_TAG_PATTERN = re.compile(
    r"</?(?P<tag>p|div|br|h[1-6]|li|ul|ol|pre|table|tr|td|th|thead|tbody|"
    r"section|article|blockquote|hr|span|strong|em|b|i|u|s|del|code|a|img|sub|sup)"
    r"(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))*\s*/?>",
    re.I,
)
BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
              "pre", "table", "tr", "section", "article", "blockquote", "hr"}


class AudioError(RuntimeError):
    """A user-actionable failure preparing narration."""


class AudioQueueFull(AudioError):
    """The narration worker's bounded queue is full."""


def narration_text(problem: dict) -> str:
    """Remove markup while retaining visible prose, formulas and code examples."""
    title = problem.get("title") or ""
    statement = problem.get("problem_statements") or problem.get("description") or ""
    if not isinstance(title, str) or not isinstance(statement, str) or not statement.strip():
        raise ValueError("A problem description is required for narration.")
    text = f"{title.strip()}.\n\n{statement.strip()}" if title.strip() else statement
    # Convert only delimited mathematics. C++ escapes, JSON strings and code
    # samples remain intact, even when they happen to contain a dollar sign.
    text = readable_math(text)
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", "", text, flags=re.I | re.S)
    text = HTML_TAG_PATTERN.sub(lambda match: "\n" if match["tag"].lower() in BLOCK_TAGS else "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:`{3,}|~{3,})[^\n]*$", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(`+|\*\*|__)", "", text)
    text = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        raise ValueError("The problem has no readable description.")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Narration supports at most {MAX_TEXT_CHARS:,} characters per problem.")
    return text


def readable_math(text: str) -> str:
    """Make common LaTeX notation pronounceable without rewriting code."""
    try:
        structured = json.loads(text)
    except (ValueError, RecursionError):
        structured = None
    if isinstance(structured, (dict, list)):
        return text

    def formula(match):
        value = next(group for group in match.groups() if group is not None)
        value = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1) divided by (\2)", value)
        value = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"square root of (\1)", value)
        value = re.sub(r"\\(?:text|mathrm|mathbf|operatorname)\s*\{([^{}]+)\}", r"\1", value)
        words = {
            "le": "less than or equal to", "leq": "less than or equal to",
            "ge": "greater than or equal to", "geq": "greater than or equal to",
            "lt": "less than", "gt": "greater than", "ne": "not equal to", "neq": "not equal to",
            "times": "times", "cdot": "times", "div": "divided by",
            "to": "to", "rightarrow": "to", "implies": "implies", "iff": "if and only if",
            "infty": "infinity", "sum": "sum", "prod": "product",
            "bmod": "modulo", "pmod": "modulo", "mod": "modulo",
            "left": "", "right": "", "quad": " ", "qquad": " ",
        }
        value = re.sub(r"\\([A-Za-z]+)\b", lambda command: f" {words.get(command[1], command[1])} ", value)
        value = re.sub(r"\^\{?2\}?(?!\d)", " squared", value)
        value = re.sub(r"\^\{?3\}?(?!\d)", " cubed", value)
        value = re.sub(r"\^\{([^{}]+)\}", r" to the power of \1", value)
        value = re.sub(r"\^([A-Za-z0-9]+)", r" to the power of \1", value)
        return value.replace("{", "(").replace("}", ")").replace("\\,", " ").replace("\\;", " ")

    math_pattern = re.compile(r"\$\$([\s\S]*?)\$\$|(?<!\\)\$([^$\n]+?)(?<!\\)\$|\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]")
    # Preserve fenced and inline code verbatim while processing prose around it.
    chunks = re.split(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)", text)
    return "".join(chunk if index % 2 else math_pattern.sub(formula, chunk) for index, chunk in enumerate(chunks))


def wav_to_mp3(data: bytes) -> bytes:
    """Encode the service's PCM audio rather than renaming WAV bytes as MP3."""
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            channels, rate = source.getnchannels(), source.getframerate()
            if source.getsampwidth() != 2 or channels not in (1, 2) or source.getcomptype() != "NONE":
                raise AudioError("Kokoro returned unsupported audio; expected 16-bit PCM WAV.")
            if rate not in (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000):
                raise AudioError("Kokoro returned an unsupported audio sample rate.")
            frame_count = source.getnframes()
            pcm = source.readframes(frame_count)
            if not pcm or len(pcm) != frame_count * channels * 2:
                raise AudioError("Kokoro returned empty or incomplete audio.")
    except (wave.Error, EOFError) as error:
        raise AudioError("Kokoro did not return valid WAV audio.") from error
    try:
        import lameenc
    except ImportError as error:
        raise AudioError("MP3 encoding is unavailable. Install backend/requirements.txt and restart the backend.") from error
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    encoder.silence()
    output = bytes(encoder.encode(pcm) + encoder.flush())
    if len(output) < 4 or not (output.startswith(b"ID3") or output[0] == 0xFF and output[1] & 0xE0 == 0xE0):
        raise AudioError("The MP3 encoder returned invalid audio.")
    return output


class AudioStore:
    def __init__(
        self, root: str | Path, *, base_url: str = "http://127.0.0.1:8301/v1",
        timeout_seconds: float = 180, max_pending: int = 4,
    ):
        self.root = Path(root).expanduser().resolve()
        self.base_url = base_url.rstrip("/")
        try:
            parsed = urlsplit(self.base_url)
            parsed.port
        except ValueError as error:
            raise ValueError("CONNECTOR_BASE_URL contains an invalid port or address.") from error
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("CONNECTOR_BASE_URL must be an HTTP service URL without credentials or a query.")
        connector_path = parsed.path.rstrip("/")
        if connector_path.endswith("/v1"):
            connector_path = connector_path[:-3]
        self.speech_url = urlunsplit((parsed.scheme, parsed.netloc, connector_path + "/api/speech", "", ""))
        self.timeout_seconds = float(timeout_seconds)
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("CONNECTOR_SPEECH_TIMEOUT_SECONDS must be between 1 and 600.")
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="narration")
        self._slots = threading.BoundedSemaphore(max(1, int(max_pending)))
        self._lock = threading.RLock()
        self._states: dict[str, dict] = {}
        self._jobs = {}
        self._epoch = 0
        self._closed = False

    def _request(self, problem: dict) -> tuple[str, dict]:
        request = {"content": narration_text(problem)}
        # Raw fields are included so any edited statement/title invalidates audio,
        # even if its normalized spoken representation happens to be identical.
        identity = {"version": 2, "encoding": "mp3-lame-128-q2", "endpoint": self.speech_url,
                    "request": request, "title": problem.get("title"),
                    "statement": problem.get("problem_statements", problem.get("description")),
                    "sourceLanguage": problem.get("language")}
        if problem.get("_audio_kind") == "response":
            identity["kind"] = "response"
        key = sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return key, request

    def path_for(self, key: str) -> Path | None:
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            return None
        candidate = self.root / f"{key}.mp3"
        try:
            if candidate.is_symlink() or candidate.resolve().parent != self.root or not candidate.is_file() or candidate.stat().st_size < 4:
                return None
        except FileNotFoundError:
            return None
        return candidate

    @staticmethod
    def _state(key: str, status: str, **extras) -> dict:
        return {"key": key, "status": status, "done": status in ("missing", "ready", "failed"),
                "cached": status == "ready", **extras}

    def get(self, problem: dict) -> dict:
        key, _ = self._request(problem)
        return self.get_by_key(key)

    def get_by_key(self, key: str) -> dict:
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid narration file key.")
        with self._lock:
            if self.path_for(key):
                return self._state(key, "ready")
            return dict(self._states.get(key) or self._state(key, "missing"))

    def start(self, problem: dict) -> dict:
        key, payload = self._request(problem)
        return self._start_request(key, payload)

    @staticmethod
    def _text_source(text: str, language: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("AI response text is required for narration.")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Narration supports at most {MAX_TEXT_CHARS:,} characters per response.")
        if not isinstance(language, str) or not language.strip() or len(language) > 30:
            raise ValueError("A supported narration language is required.")
        return {"description": text, "language": language.strip(), "_audio_kind": "response"}

    def get_text(self, text: str, language: str = "en") -> dict:
        return self.get(self._text_source(text, language))

    def start_text(self, text: str, language: str = "en") -> dict:
        return self.start(self._text_source(text, language))

    def _start_request(self, key: str, payload: dict) -> dict:
        with self._lock:
            if self.path_for(key):
                return self._state(key, "ready")
            previous = self._states.get(key)
            if previous and not previous["done"]:
                return dict(previous)
            if self._closed or not self._slots.acquire(blocking=False):
                raise AudioQueueFull("The narration queue is busy. Please try again shortly.")
            # Failures are retained only for polling, not as a permanent cache.
            # Bound their metadata while retaining every active job.
            if len(self._states) >= 128:
                self._states = {key: value for key, value in self._states.items() if not value["done"]}
            pending = self._state(key, "queued", cached=False)
            self._states[key] = pending
            try:
                epoch = self._epoch
                self._jobs[(epoch, key)] = self._pool.submit(self._generate, key, payload, epoch)
            except Exception:
                self._slots.release()
                self._states.pop(key, None)
                raise
            return dict(pending)

    def _cache_entries(self) -> list[tuple[Path, int]]:
        try:
            self.root.stat()
        except FileNotFoundError:
            return []
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise AudioError("The saved audio directory changed. Restart the backend before clearing audio.")
        entries = []
        for candidate in self.root.iterdir():
            if candidate.suffix != ".mp3" or not KEY_PATTERN.fullmatch(candidate.stem):
                continue
            metadata = candidate.lstat()
            if stat.S_ISREG(metadata.st_mode):
                entries.append((candidate, metadata.st_size))
        return entries

    def cache_info(self) -> dict:
        with self._lock:
            try:
                entries = self._cache_entries()
                return {"files": len(entries), "bytes": sum(size for _, size in entries)}
            except OSError as error:
                raise AudioError("Unable to inspect saved audio. Check the audio folder permissions and retry.") from error

    def clear_cache(self) -> dict:
        """Delete owned MP3s and invalidate older jobs before they can commit."""
        with self._lock:
            self._epoch += 1
            self._states.clear()
            for job, future in list(self._jobs.items()):
                if future.cancel():
                    self._jobs.pop(job, None)
                    self._slots.release()
            removed_files, removed_bytes = 0, 0
            try:
                for candidate, size in self._cache_entries():
                    candidate.unlink()
                    removed_files += 1
                    removed_bytes += size
                remaining = self.cache_info()
            except OSError as error:
                raise AudioError("Unable to clear all saved audio. Check the audio folder permissions and retry.") from error
            return {"removedFiles": removed_files, "removedBytes": removed_bytes, **remaining}

    def _wav(self, payload: dict) -> bytes:
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout_seconds, connect=5), trust_env=False) as client:
                with client.stream("POST", self.speech_url, json=payload) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_WAV_BYTES:
                            raise AudioError("Kokoro audio exceeded the supported size. Shorten the description.")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except httpx.TimeoutException as error:
            raise AudioError("The Connector speech request timed out. Retry when its speech model has finished loading.") from error
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            message = {
                422: ("The Connector rejected this narration content. Use non-empty plain text "
                      "or a JSON object with a non-empty string text field."),
                502: "The Connector received an invalid response from its speech service. Check The Connector and retry.",
                503: "The Connector speech service is unavailable. Start it in The Connector and retry.",
            }.get(status, f"The Connector speech endpoint returned HTTP {status}. Check The Connector and retry.")
            raise AudioError(message) from error
        except httpx.RequestError as error:
            raise AudioError("Cannot reach The Connector speech endpoint. Start The Connector and check CONNECTOR_BASE_URL.") from error

    def _generate(self, key: str, payload: dict, epoch: int) -> None:
        temporary = None
        try:
            with self._lock:
                if epoch != self._epoch:
                    return
                self._states[key] = self._state(key, "generating", cached=False)
            encoded = wav_to_mp3(self._wav(payload))
            with self._lock:
                if epoch != self._epoch:
                    return
                self.root.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=self.root, prefix=f".{key}.", suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.root / f"{key}.mp3")
                self._states.pop(key, None)
        except Exception as error:
            with self._lock:
                if epoch == self._epoch:
                    logger.exception("Narration failed for %s", key)
                    message = str(error) if isinstance(error, AudioError) else "Unable to save narration. Check the backend logs and retry."
                    self._states[key] = self._state(key, "failed", cached=False, error=message)
        finally:
            try:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self._jobs.pop((epoch, key), None)
                    self._slots.release()

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=wait)
