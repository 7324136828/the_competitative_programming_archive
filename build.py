#!/usr/bin/env python3
"""Build portable Debug (local) and Release (LAN) Windows applications."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "dist"
WORK = ROOT / "build"
LOCAL_VENV = ROOT / ".venv"
LOCAL_PYTHON = LOCAL_VENV / "Scripts" / "python.exe"
APPLICATION = "server"
PORT_MAPPING = ROOT / "port_mapping.json"
PROFILES = {"Debug": "127.0.0.1", "Release": "0.0.0.0"}
ARTIFACTS = ("server.exe", "public", "run.bat", "runtime.json", "port_mapping.json")

LAUNCHER = """@echo off
setlocal EnableExtensions DisableDelayedExpansion
if not exist "%~dp0server.exe" (
  echo [run] ERROR: Backend executable is missing. Rebuild with build.bat. 1>&2
  exit /b 1
)
if not defined APPDATA (
  echo [run] ERROR: APPDATA is not defined. 1>&2
  exit /b 1
)
set "APP_SETTINGS_DIR=%APPDATA%\\the_study_platform"
set "APP_SETTINGS_FILE=%APP_SETTINGS_DIR%\\settings.json"
if not exist "%APP_SETTINGS_DIR%" mkdir "%APP_SETTINGS_DIR%"
if not exist "%APP_SETTINGS_DIR%" exit /b 1
if not exist "%APP_SETTINGS_FILE%" (
  > "%APP_SETTINGS_FILE%" echo {}
  if errorlevel 1 exit /b 1
)
rem Fill missing ports from port_mapping.json beside server.exe,
rem then reread settings.json and export validated numbers for this launch.
set "APP_PORTS_FILE=%TEMP%\\the_study_platform-ports-%RANDOM%-%RANDOM%.txt"
"%~dp0server.exe" --prepare-settings --ports-file "%APP_PORTS_FILE%"
if errorlevel 1 exit /b 1
set "APP_FRONTEND_PORT="
set "APP_BACKEND_PORT="
for /f "usebackq tokens=1,2 delims==" %%A in ("%APP_PORTS_FILE%") do (
  if "%%A"=="frontend_port" set "APP_FRONTEND_PORT=%%B"
  if "%%A"=="backend_port" set "APP_BACKEND_PORT=%%B"
)
del /q "%APP_PORTS_FILE%" >nul 2>nul
if not defined APP_FRONTEND_PORT exit /b 1
if not defined APP_BACKEND_PORT exit /b 1
"%~dp0server.exe" --frontend-port %APP_FRONTEND_PORT% --backend-port %APP_BACKEND_PORT% %*
exit /b %ERRORLEVEL%
"""


class BuildError(RuntimeError):
    """Raised when a portable build cannot be completed."""


def validate_port_defaults(path: Path) -> None:
    from backend.settings import load_port_mapping

    try:
        load_port_mapping(path)
    except (ValueError, OSError) as error:
        raise BuildError(f"Invalid port defaults: {error}") from error


def checked_path(path: Path, parent: Path) -> Path:
    """Reject symlinks/junctions that resolve outside the intended directory."""
    resolved = path.resolve()
    allowed = parent.resolve()
    if resolved == allowed or not resolved.is_relative_to(allowed):
        raise BuildError(f"Unsafe build path outside {allowed}: {path}")
    return resolved


def run(
    command: list[str | Path], *, cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    rendered = [str(part) for part in command]
    print(f"[build] $ {subprocess.list2cmdline(rendered)}", flush=True)
    completed = subprocess.run(rendered, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise BuildError(f"Command failed with exit code {completed.returncode}")


def select_python() -> Path:
    if (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or os.environ.get("VIRTUAL_ENV")
        or os.environ.get("CONDA_PREFIX")
    ):
        print(f"[build] Using active Python environment: {sys.prefix}")
        return Path(sys.executable)
    if not LOCAL_PYTHON.is_file():
        checked_path(LOCAL_VENV, ROOT)
        print(f"[build] Creating Python environment at {LOCAL_VENV}")
        venv.EnvBuilder(with_pip=True).create(LOCAL_VENV)
    if not LOCAL_PYTHON.is_file():
        raise BuildError(f"Python environment has no interpreter: {LOCAL_PYTHON}")
    return LOCAL_PYTHON


def pyinstaller_command(python: Path, stage: Path) -> list[str | Path]:
    command: list[str | Path] = [
        python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--noupx",
        "--name", APPLICATION,
        "--distpath", stage / "frozen",
        "--workpath", stage / "pyinstaller",
        "--specpath", stage,
        "--paths", ROOT,
    ]
    # Uvicorn loads these configured implementations by their string names.
    for module in (
        "uvicorn.logging",
        "uvicorn.loops.asyncio",
        "uvicorn.lifespan.on",
        "uvicorn.protocols.http.h11_impl",
        "lameenc",
    ):
        command.extend(["--hidden-import", module])
    # Jira reads its SQL schema next to the bundled module; optional archive
    # seeding reads problem.json from the bundle's application root.
    command.extend([
        "--add-data", f"{BACKEND / 'jira' / 'schema.sql'}{os.pathsep}backend/jira",
        "--add-data", f"{ROOT / 'problem.json'}{os.pathsep}.",
    ])
    command.append(BACKEND / "packaged.py")
    return command


def prepare_artifacts(stage: Path, *, defaults_path: Path = PORT_MAPPING) -> Path:
    """Create two portable packages from the shared frontend and executable."""
    validate_port_defaults(defaults_path)
    packages = stage / "packages"
    checked_path(packages, stage)
    packages.mkdir()
    for profile, host in PROFILES.items():
        package = packages / profile
        checked_path(package, packages)
        package.mkdir()
        shutil.copy2(stage / "server.exe", package / "server.exe")
        shutil.copytree(stage / "public", package / "public")
        shutil.copy2(defaults_path, package / "port_mapping.json")
        (package / "run.bat").write_text(LAUNCHER, encoding="ascii", newline="\r\n")
        (package / "runtime.json").write_text(
            json.dumps({"host": host}, indent=2) + "\n", encoding="ascii",
        )
    return packages


def validate_artifacts(stage: Path, *, host: str) -> None:
    if not (stage / "server.exe").is_file():
        raise BuildError("PyInstaller did not produce the backend executable")
    if not (stage / "public" / "index.html").is_file():
        raise BuildError("Vite did not produce public/index.html")
    if json.loads((stage / "runtime.json").read_text(encoding="ascii")) != {"host": host}:
        raise BuildError(f"Unexpected runtime defaults in {stage}")
    validate_port_defaults(stage / "port_mapping.json")
    batch_files = [path.relative_to(stage) for path in stage.rglob("*")
                   if path.is_file() and path.suffix.lower() == ".bat"]
    if batch_files != [Path("run.bat")]:
        raise BuildError(f"Unexpected batch files in portable artifacts: {batch_files}")


def publish_artifacts(stage: Path, *, repository: Path = ROOT) -> None:
    """Publish both profiles together, preserving their data and local settings."""
    output = repository / "dist"
    checked_path(output, repository)
    checked_path(stage, repository / "build")
    output.mkdir(exist_ok=True)
    previous = stage / "previous"
    checked_path(previous, stage)
    previous.mkdir()
    installed: list[tuple[str, str]] = []
    backed_up: list[tuple[str, str]] = []
    # Check every mutation target before moving anything. In particular, a
    # junction used for one output must not leave another output half updated.
    for profile in PROFILES:
        checked_path(stage / profile, stage)
        checked_path(output / profile, output)
        checked_path(previous / profile, previous)
        for name in ARTIFACTS:
            checked_path(stage / profile / name, stage / profile)
            checked_path(output / profile / name, output / profile)
            checked_path(previous / profile / name, previous / profile)
    for profile in PROFILES:
        (output / profile).mkdir(exist_ok=True)
        (previous / profile).mkdir()
    try:
        for profile in PROFILES:
            for name in ARTIFACTS:
                source = stage / profile / name
                target = output / profile / name
                backup = previous / profile / name
                checked_path(source, stage / profile)
                checked_path(target, output / profile)
                checked_path(backup, previous / profile)
                if target.exists():
                    target.rename(backup)
                    backed_up.append((profile, name))
                source.rename(target)
                installed.append((profile, name))
    except OSError as error:
        # A locked artifact in either profile restores both previous packages.
        # User state in each distribution is never moved.
        for profile, name in reversed(installed):
            target = output / profile / name
            checked_path(target, output / profile)
            target.rename(stage / profile / name)
        for profile, name in reversed(backed_up):
            backup = previous / profile / name
            checked_path(backup, previous / profile)
            backup.rename(output / profile / name)
        raise BuildError(
            "Could not replace Debug/Release artifacts; close the running application "
            f"and retry. {error}"
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-install", action="store_true",
        help="Reuse installed Python/npm dependencies instead of installing them",
    )
    options = parser.parse_args(argv)
    if os.name != "nt":
        raise BuildError("Build the Windows executable on Windows")
    if sys.version_info < (3, 10):
        raise BuildError("Python 3.10 or newer is required")
    # Fail before creating build work, environments, or installing dependencies.
    validate_port_defaults(PORT_MAPPING)
    npm = shutil.which("npm.cmd")
    if npm is None:
        raise BuildError("Node.js and npm were not found on PATH")
    if not (BACKEND / "packaged.py").is_file():
        raise BuildError("Backend packaged entrypoint is missing")
    checked_path(WORK, ROOT)
    WORK.mkdir(exist_ok=True)
    python = select_python()
    if not options.skip_install:
        run([python, "-m", "pip", "install", "--cache-dir", WORK / "pip-cache",
             "-r", BACKEND / "requirements.txt",
             "-r", BACKEND / "requirements-build.txt"])
        run([npm, "ci", "--cache", WORK / "npm-cache"], cwd=FRONTEND)
    # The application is JavaScript and has no typecheck script. Its existing
    # frontend tests and Vite build are the relevant validation here.
    run([npm, "test"], cwd=FRONTEND)

    stage = WORK / ("portable-" + uuid.uuid4().hex)
    checked_path(stage, WORK)
    stage.mkdir()
    published = False
    try:
        run([npm, "run", "build", "--", "--outDir", stage / "public"], cwd=FRONTEND)
        freeze_env = os.environ.copy()
        freeze_env["PYINSTALLER_CONFIG_DIR"] = str(WORK / "pyinstaller-cache")
        checked_path(WORK / "pyinstaller-cache", WORK)
        run(pyinstaller_command(python, stage), env=freeze_env)
        frozen = stage / "frozen" / f"{APPLICATION}.exe"
        checked_path(frozen, stage)
        frozen.rename(stage / "server.exe")
        # Validate both portable folders rather than PyInstaller's work/spec files.
        artifacts = prepare_artifacts(stage)
        for profile, host in PROFILES.items():
            validate_artifacts(artifacts / profile, host=host)
            run([artifacts / profile / "server.exe", "--help"])
        publish_artifacts(artifacts)
        published = True
    finally:
        if published:
            checked_path(stage, WORK)
            shutil.rmtree(stage)
        else:
            print(f"[build] Build files retained for troubleshooting: {stage}")

    print(f"\n[build] Ready: {OUTPUT / 'Debug'} (local) and {OUTPUT / 'Release'} (LAN)")
    print("[build] Local: dist\\Debug\\run.bat --frontend 4000 --backend 9000")
    print("[build] LAN:   dist\\Release\\run.bat --frontend 4000 --backend 9000")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, OSError) as error:
        print(f"\n[build] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
