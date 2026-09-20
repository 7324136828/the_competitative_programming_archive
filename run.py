#!/usr/bin/env python3
"""Run CodeJudge, Vite, and the standalone Python 3.12 Kokoro service."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, build_opener

from launcher_config import KOKORO_PYTHON, KOKORO_SERVER, kokoro_device, load_env_file

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
LOCAL_PYTHON = ROOT / ".venv" / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python"
)


class RunError(RuntimeError):
    """Raised when the application cannot be started."""


def in_active_environment() -> bool:
    return (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or bool(os.environ.get("VIRTUAL_ENV"))
        or bool(os.environ.get("CONDA_PREFIX"))
    )


def select_runtime(*, skip_kokoro: bool = False) -> Path:
    if in_active_environment():
        return Path(sys.executable)
    if not LOCAL_PYTHON.is_file():
        print("[run] No active environment or local .venv; running setup...")
        command = [sys.executable, str(ROOT / "setup.py")]
        if skip_kokoro:
            command.append("--skip-kokoro")
        if subprocess.call(command, cwd=ROOT):
            raise RunError("Setup failed")
    if not LOCAL_PYTHON.is_file():
        raise RunError(f"Python environment not found at {LOCAL_PYTHON}")
    return LOCAL_PYTHON


def parse_port(value: str | int, label: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise RunError(f"{label} must be an integer") from error
    if not 1 <= port <= 65535:
        raise RunError(f"{label} must be between 1 and 65535")
    return port


def available_port(start: int, reserved: set[int] | None = None, *, host: str = "127.0.0.1") -> int:
    reserved = reserved or set()
    for port in range(start, 65536):
        if port in reserved:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
        return port
    raise RunError(f"No available TCP port was found at or above {start}")


def lan_addresses() -> list[str]:
    """List this computer's usable IPv4 addresses without contacting another host."""
    try:
        entries = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return []
    addresses = set()
    for entry in entries:
        address = ipaddress.ip_address(entry[4][0])
        if not (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast):
            addresses.add(address)
    return [str(address) for address in sorted(addresses)]


def backend_connect_url(host: str, port: int) -> str:
    # Wildcard bind addresses are not destinations for the Vite API proxy.
    target = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    if ":" in target:
        target = f"[{target}]"
    return f"http://{target}:{port}"


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # Python venv launchers and npm can create descendants. Stop only our
        # owned process tree, including the underlying interpreter/Vite worker.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def process_options() -> dict:
    # Services have their own process group so cleanup covers their descendants.
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kokoro_url(base_url: str):
    try:
        parsed = urlsplit(base_url)
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise RunError("KOKORO_BASE_URL contains an invalid port or address.") from error
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RunError("KOKORO_BASE_URL must be an HTTP(S) service URL without credentials or a query.")
    if not 1 <= port <= 65535:
        raise RunError("KOKORO_BASE_URL port must be between 1 and 65535.")
    path = parsed.path.rstrip("/")
    health_path = path.removesuffix("/v1") + "/health"
    health_url = urlunsplit((parsed.scheme, parsed.netloc, health_path, "", ""))
    return parsed, port, health_url


def read_kokoro_health(health_url: str) -> dict | None:
    try:
        with build_opener(ProxyHandler({})).open(health_url, timeout=1) as response:
            body = json.loads(response.read(65536).decode("utf-8"))
        return body if isinstance(body, dict) else None
    except (URLError, OSError, ValueError):
        return None


def validate_kokoro_health(health: dict, device: str) -> None:
    if health.get("service") != "python-kokoro" or health.get("status") != "ok":
        raise RunError("The configured Kokoro address belongs to an incompatible service.")
    if not str(health.get("python", "")).startswith("3.12."):
        raise RunError("Kokoro must run with its standalone Python 3.12 interpreter.")
    if device != "auto" and health.get("device") != device:
        raise RunError(
            f"Kokoro is running on {health.get('device')}, but {device} was requested. "
            "Restart the speech service with the requested device "
            "(Windows: python-kokoro/run.ps1 -Device " + device + " -Restart)."
        )


def start_kokoro(base_url: str, device: str, *, timeout: float = 60) -> subprocess.Popen | None:
    """Reuse a compatible service, or own a local child until CodeJudge exits."""
    parsed, port, health_url = kokoro_url(base_url)
    health = read_kokoro_health(health_url)
    if health is not None:
        validate_kokoro_health(health, device)
        print(f"[run] Reusing Kokoro ({health['device']}, Python {health['python']}).", flush=True)
        return None
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path.rstrip("/") not in ("", "/v1"):
        raise RunError("The configured external Kokoro service is unavailable. Start it before running CodeJudge.")
    if not KOKORO_PYTHON.is_file() or not KOKORO_SERVER.is_file():
        raise RunError("Kokoro is not set up. Run setup.py --kokoro-only (Python 3.12 required).")
    try:
        check = subprocess.run(
            [str(KOKORO_PYTHON), "-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"],
            capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RunError("Cannot start Kokoro's Python 3.12 interpreter. Run setup.py --kokoro-only.") from error
    if check.returncode:
        raise RunError("Kokoro's environment must use Python 3.12. Run setup.py --kokoro-only.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RunError(f"Kokoro port {port} is occupied by an unresponsive or incompatible service.") from error
    command = [str(KOKORO_PYTHON), "-u", str(KOKORO_SERVER), "--host", "127.0.0.1", "--port", str(port), "--device", device]
    print(f"[run] Starting standalone Python 3.12 Kokoro ({device})...", flush=True)
    try:
        process = subprocess.Popen(command, cwd=ROOT, **process_options())
    except OSError as error:
        raise RunError("Unable to launch the Kokoro service. Run setup.py --kokoro-only.") from error
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RunError("Kokoro exited during startup. Check its output and run setup.py --kokoro-only.")
            health = read_kokoro_health(health_url)
            if health is not None:
                validate_kokoro_health(health, device)
                print(f"[run] Kokoro ready ({health['device']}, Python {health['python']}).", flush=True)
                return process
            time.sleep(0.25)
        raise RunError(f"Kokoro did not become healthy within {timeout:g} seconds.")
    except BaseException:
        stop(process)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("serve",), default="serve", help="start the application (default)")
    parser.add_argument("--lan", action="store_true", help="share the app on your LAN through the frontend port")
    parser.add_argument("--backend-port", type=int, help="first backend port to try (default 3001)")
    parser.add_argument("--frontend-port", type=int, help="first frontend port to try (default 5173)")
    parser.add_argument("--host", default=os.environ.get("HOST") or os.environ.get("BACKEND_HOST", "127.0.0.1"), help="backend bind address")
    parser.add_argument("--kokoro-device", choices=("cuda", "cpu", "auto"), help="speech device (default KOKORO_DEVICE or cuda)")
    parser.add_argument("--skip-kokoro", action="store_true", help="do not start or validate the speech service")
    return parser.parse_args()


def main() -> int:
    load_env_file()
    args = parse_args()
    device = None
    if not args.skip_kokoro:
        try:
            device = kokoro_device(args.kokoro_device)
        except ValueError as error:
            raise RunError(str(error)) from error
        os.environ["KOKORO_DEVICE"] = device
    runtime = select_runtime(skip_kokoro=args.skip_kokoro)
    if Path(sys.executable).resolve() != runtime.resolve():
        return subprocess.call([str(runtime), str(Path(__file__).resolve()), *sys.argv[1:]])

    requested_backend = parse_port(
        args.backend_port or os.environ.get("PORT") or os.environ.get("BACKEND_PORT", "3001"),
        "backend port",
    )
    requested_frontend = parse_port(
        args.frontend_port or os.environ.get("FRONTEND_PORT", "5173"),
        "frontend port",
    )
    kokoro_base = os.environ.get("KOKORO_BASE_URL") or "http://127.0.0.1:8880"
    reserved = set()
    if not args.skip_kokoro:
        parsed, kokoro_port, _ = kokoro_url(kokoro_base)
        if parsed.hostname in ("127.0.0.1", "localhost"):
            reserved.add(kokoro_port)
    backend_port = available_port(requested_backend, reserved)
    frontend_bind = "0.0.0.0" if args.lan else "127.0.0.1"
    frontend_port = available_port(requested_frontend, reserved | {backend_port}, host=frontend_bind)
    host = args.host
    backend_url = backend_connect_url(host, backend_port)
    frontend_url = f"http://localhost:{frontend_port}"

    backend_env = os.environ.copy()
    backend_env["PORT"] = str(backend_port)
    backend_env["HOST"] = host

    frontend_env = os.environ.copy()
    frontend_env["VITE_BACKEND_URL"] = backend_url

    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise RunError("npm was not found; run setup first")
    if not (FRONTEND / "node_modules").is_dir():
        raise RunError("Frontend dependencies are missing; run setup.bat or setup.py first")

    if backend_port != requested_backend:
        print(f"[run] Backend port {requested_backend} is busy; using {backend_port}.")
    if frontend_port != requested_frontend:
        print(f"[run] Frontend port {requested_frontend} is busy; using {frontend_port}.")
    print("=" * 62)
    print("CodeJudge LeetCode Platform")
    print(f"Python:   {sys.executable}")
    print(f"Backend:  {backend_url} (API: {backend_url}/api/problems)")
    print(f"Frontend: {frontend_url}")
    if args.lan:
        addresses = lan_addresses()
        for address in addresses:
            print(f"LAN:      http://{address}:{frontend_port}")
        if not addresses:
            print(f"LAN:      http://<this-computer-LAN-IP>:{frontend_port}")
    if not args.skip_kokoro:
        # Validate before displaying the address, which must not contain credentials.
        kokoro_url(kokoro_base)
        print(f"Kokoro:   {kokoro_base} ({device}, standalone Python 3.12)")
    print("Press Ctrl+C to stop services started by this launcher.")
    print("=" * 62, flush=True)

    backend_command = [
        sys.executable,
        "-m",
        "backend.app",
        "--host",
        host,
        "--port",
        str(backend_port),
    ]
    frontend_command = [
        npm,
        "run",
        "dev",
        "--",
        "--port",
        str(frontend_port),
        "--strictPort",
        "--host",
        frontend_bind,
    ]

    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    kokoro_process: subprocess.Popen[bytes] | None = None
    def request_shutdown(_signum, _frame):
        raise KeyboardInterrupt

    previous_handlers = {}
    for name in ("SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            previous_handlers[signum] = signal.signal(signum, request_shutdown)
    try:
        if not args.skip_kokoro:
            kokoro_process = start_kokoro(kokoro_base, device)
        backend_process = subprocess.Popen(backend_command, cwd=ROOT, env=backend_env, **process_options())
        frontend_process = subprocess.Popen(
            frontend_command, cwd=FRONTEND, env=frontend_env, **process_options()
        )
        while True:
            for label, process in (
                ("Backend", backend_process),
                ("Frontend", frontend_process),
                ("Kokoro", kokoro_process),
            ):
                if process is None:
                    continue
                status = process.poll()
                if status is not None:
                    print(f"[run] {label} exited with code {status}.")
                    return status or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[run] Stopping services...")
        return 0
    finally:
        stop(frontend_process)
        stop(backend_process)
        stop(kokoro_process)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunError as error:
        print(f"[run] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
