"""Shared configuration for the setup and development launchers."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KOKORO_DIR = ROOT / "python-kokoro"
KOKORO_PYTHON = KOKORO_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
KOKORO_SERVER = KOKORO_DIR / "server.py"


def load_env_file(path: Path = ROOT / ".env") -> None:
    """Keep terminal overrides while loading local configuration without logging it."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def kokoro_device(value: str | None = None) -> str:
    device = (value or os.environ.get("KOKORO_DEVICE") or "cuda").strip().lower()
    if device not in ("cuda", "cpu", "auto"):
        raise ValueError("KOKORO_DEVICE must be cuda, cpu, or auto.")
    return device
