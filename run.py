#!/usr/bin/env python3
"""Run the CodeJudge backend and Vite frontend."""

from __future__ import annotations

import argparse
import ipaddress
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from launcher_config import load_env_file

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


def select_runtime() -> Path:
    if in_active_environment():
        return Path(sys.executable)
    if not LOCAL_PYTHON.is_file():
        print("[run] No active environment or local .venv; running setup...")
        command = [sys.executable, str(ROOT / "setup.py")]
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
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as probe:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example: run.py serve --lan --frontend-port 8080 --backend-port 8000. "
               "Busy frontend/backend ports advance to the next free port.",
    )
    parser.add_argument("command", nargs="?", choices=("serve",), default="serve", help="start the application (default)")
    parser.add_argument("--lan", action="store_true", help="share the app on your LAN through the frontend port")
    parser.add_argument("--backend-port", type=int, metavar="PORT", help="first backend port to try (1-65535; overrides PORT/BACKEND_PORT; default 3001)")
    parser.add_argument("--frontend-port", type=int, metavar="PORT", help="first frontend port to try (1-65535; overrides FRONTEND_PORT; default 5173)")
    parser.add_argument("--host", default=os.environ.get("HOST") or os.environ.get("BACKEND_HOST", "127.0.0.1"), help="backend bind address")
    return parser.parse_args()


def main() -> int:
    load_env_file()
    args = parse_args()
    requested_backend = parse_port(
        args.backend_port if args.backend_port is not None else os.environ.get("PORT") or os.environ.get("BACKEND_PORT", "3001"),
        "backend port",
    )
    requested_frontend = parse_port(
        args.frontend_port if args.frontend_port is not None else os.environ.get("FRONTEND_PORT", "5173"),
        "frontend port",
    )
    runtime = select_runtime()
    if Path(sys.executable).resolve() != runtime.resolve():
        return subprocess.call([str(runtime), str(Path(__file__).resolve()), *sys.argv[1:]])

    host = args.host
    backend_port = available_port(requested_backend, set(), host=host)
    frontend_bind = "0.0.0.0" if args.lan else "127.0.0.1"
    frontend_port = available_port(requested_frontend, {backend_port}, host=frontend_bind)
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
    print(f"Connector: {os.environ.get('CONNECTOR_BASE_URL', 'http://127.0.0.1:8301/v1')} (LLM and speech)")
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

    def request_shutdown(_signum, _frame):
        raise KeyboardInterrupt

    previous_handlers = {}
    for name in ("SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            previous_handlers[signum] = signal.signal(signum, request_shutdown)
    try:
        backend_process = subprocess.Popen(backend_command, cwd=ROOT, env=backend_env, **process_options())
        frontend_process = subprocess.Popen(
            frontend_command, cwd=FRONTEND, env=frontend_env, **process_options()
        )
        while True:
            for label, process in (
                ("Backend", backend_process),
                ("Frontend", frontend_process),
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
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunError as error:
        print(f"[run] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
