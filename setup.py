#!/usr/bin/env python3
"""Set up CodeJudge and its separate Python 3.12 Kokoro speech service."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

from launcher_config import (
    KOKORO_DIR,
    KOKORO_PYTHON,
    ROOT,
    kokoro_device,
    load_env_file,
)

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


def is_python312(command: list[str | Path]) -> bool:
    """Probe the interpreter itself, regardless of the currently active venv."""
    try:
        completed = subprocess.run(
            [str(part) for part in command]
            + ["-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def find_python312() -> list[str]:
    candidates: list[list[str]] = []
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            candidates.append([launcher, "-3.12"])
    python312 = shutil.which("python3.12")
    if python312:
        candidates.append([python312])
    if sys.version_info[:2] == (3, 12):
        candidates.append([sys.executable])
    for candidate in candidates:
        if is_python312(candidate):
            return candidate
    raise SetupError(
        "Kokoro requires standalone Python 3.12. Install Python 3.12 "
        "(with the py launcher on Windows, or python3.12 on PATH), then retry. "
        "Use --skip-kokoro to set up only the application."
    )


def setup_kokoro(device: str, *, reuse_system_packages: bool = False) -> None:
    if device not in {"cuda", "cpu"}:
        raise SetupError("Kokoro setup device must be cuda or cpu")
    requirements = KOKORO_DIR / "requirements.txt"
    cuda_requirements = KOKORO_DIR / "requirements-cuda.txt"
    for required in [requirements] + ([cuda_requirements] if device == "cuda" else []):
        if not required.is_file():
            raise SetupError(f"Kokoro requirements file not found: {required}")

    if not KOKORO_PYTHON.is_file():
        base_python = find_python312()
        environment = KOKORO_DIR / ".venv"
        command = [*base_python, "-m", "venv"]
        if reuse_system_packages:
            command.append("--system-site-packages")
        command.append(str(environment))
        print(f"[setup] Creating separate Python 3.12 environment at {environment}")
        run(command)
    else:
        print(f"[setup] Reusing Kokoro environment at {KOKORO_DIR / '.venv'}")
    if not KOKORO_PYTHON.is_file() or not is_python312([KOKORO_PYTHON]):
        raise SetupError(
            f"Kokoro's interpreter must be Python 3.12: {KOKORO_PYTHON}. "
            "Move the existing python-kokoro/.venv aside and retry setup "
            "with Python 3.12 installed."
        )

    print(f"[setup] Installing Kokoro dependencies for {device} with {KOKORO_PYTHON}")
    if device == "cuda":
        run([KOKORO_PYTHON, "-m", "pip", "install", "--upgrade", "-r", cuda_requirements])
    else:
        run([
            KOKORO_PYTHON, "-m", "pip", "install", "torch==2.11.0",
            "--index-url", "https://download.pytorch.org/whl/cpu",
        ])
    run([KOKORO_PYTHON, "-m", "pip", "install", "-r", requirements])
    run([
        KOKORO_PYTHON, "-c",
        "import sys, kokoro, torch; print('Kokoro Python:', sys.executable); "
        "print('Python:', sys.version.split()[0]); print('PyTorch:', torch.__version__)",
    ])
    if device == "cuda":
        try:
            run([
                KOKORO_PYTHON, "-c",
                "import torch; "
                "assert torch.version.cuda, 'Install a CUDA-enabled PyTorch build'; "
                "assert torch.cuda.is_available(), 'CUDA is unavailable; check the NVIDIA driver'; "
                "torch.ones(1, device='cuda').add_(1).item(); "
                "print('CUDA:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0))",
            ])
        except SetupError as error:
            raise SetupError(
                "Kokoro CUDA verification failed. Check the NVIDIA driver, or explicitly "
                "use --kokoro-device cpu for setup and run. CUDA will not silently fall back to CPU."
            ) from error
    print("[setup] Kokoro model and language data are downloaded on the first speech request.")


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
    load_env_file()
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--skip-kokoro", action="store_true", help="Set up only the application")
    scope.add_argument("--kokoro-only", action="store_true", help="Set up only the speech service")
    parser.add_argument(
        "--kokoro-device", choices=("cuda", "cpu"),
        help="Kokoro PyTorch build (default: KOKORO_DEVICE, otherwise cuda)",
    )
    parser.add_argument(
        "--reuse-kokoro-system-packages", action="store_true",
        help="Allow a new Kokoro venv to use packages from the standalone Python 3.12 installation",
    )
    options = parser.parse_args(argv)
    device = None
    if not options.skip_kokoro:
        try:
            device = kokoro_device(options.kokoro_device)
        except ValueError as error:
            raise SetupError(str(error)) from error
        # An automatic runtime still needs a CUDA-capable installation to use the GPU.
        if device == "auto":
            device = "cuda"
    seed_environment_file()
    if not options.kokoro_only:
        setup_application()
    if device:
        setup_kokoro(device, reuse_system_packages=options.reuse_kokoro_system_packages)

    print("\n[setup] Ready. Start CodeJudge and Kokoro with run.bat or ./run.sh")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as error:
        print(f"\n[setup] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
