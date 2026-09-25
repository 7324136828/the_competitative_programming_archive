#!/usr/bin/env python3
"""Set up CodeJudge application dependencies."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

from launcher_config import ROOT, load_env_file

BACKEND_REQUIREMENTS = ROOT / "backend" / "requirements.txt"
FRONTEND = ROOT / "frontend"
E2E = ROOT / "e2e"
LOCAL_VENV = ROOT / ".venv"
LOCAL_PYTHON = LOCAL_VENV / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python"
)


class SetupError(RuntimeError):
    """Raised when setup cannot be completed."""


def in_active_environment() -> bool:
    return (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or bool(os.environ.get("VIRTUAL_ENV"))
        or bool(os.environ.get("CONDA_PREFIX"))
    )


def run(command: list[str | Path], *, cwd: Path = ROOT) -> None:
    rendered = [str(part) for part in command]
    print(f"[setup] $ {' '.join(rendered)}", flush=True)
    try:
        completed = subprocess.run(rendered, cwd=cwd, check=False)
    except OSError as error:
        raise SetupError(f"Could not start {rendered[0]}: {error}") from error
    if completed.returncode:
        raise SetupError(
            f"Command failed with exit code {completed.returncode}: "
            f"{' '.join(rendered)}"
        )


def select_python() -> Path:
    if in_active_environment():
        print(f"[setup] Using active Python environment: {sys.prefix}")
        return Path(sys.executable)

    if not LOCAL_PYTHON.is_file():
        print(f"[setup] Creating virtual environment at {LOCAL_VENV}")
        venv.EnvBuilder(with_pip=True).create(LOCAL_VENV)
    else:
        print(f"[setup] Reusing virtual environment at {LOCAL_VENV}")
    if not LOCAL_PYTHON.is_file():
        raise SetupError(f"Virtual environment has no interpreter at {LOCAL_PYTHON}")
    return LOCAL_PYTHON


def seed_environment_file() -> None:
    example = ROOT / ".env.example"
    target = ROOT / ".env"
    if example.is_file() and not target.exists():
        shutil.copy2(example, target)
        print("[setup] Created .env from .env.example")


def setup_application() -> None:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise SetupError("Node.js and npm were not found on PATH")
    if not BACKEND_REQUIREMENTS.is_file():
        raise SetupError(f"Requirements file not found: {BACKEND_REQUIREMENTS}")
    if not (FRONTEND / "package.json").is_file():
        raise SetupError(f"React project not found: {FRONTEND}")
    if not (E2E / "package.json").is_file():
        raise SetupError(f"End-to-end test project not found: {E2E}")

    python = select_python()
    print(f"[setup] Installing backend dependencies with {python}")
    run([python, "-m", "pip", "install", "-r", BACKEND_REQUIREMENTS])
    print("[setup] Installing frontend dependencies")
    run([npm, "install"], cwd=FRONTEND)
    print("[setup] Installing end-to-end test dependencies")
    run([npm, "install"], cwd=E2E)


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        raise SetupError("Python 3.10 or newer is required")
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    load_env_file()
    seed_environment_file()
    setup_application()

    print("\n[setup] Ready. Start The Connector, then run CodeJudge with run.bat or ./run.sh")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as error:
        print(f"\n[setup] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
