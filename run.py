#!/usr/bin/env python3
"""Run The Study Platform backend and Vite frontend."""

from __future__ import annotations

import argparse
import errno
import ipaddress
import os
import shutil
import signal
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from backend.settings import initialize_port_settings
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
    try:
        family, _, _, _, address = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM)[0]
    except OSError as error:
        raise RunError(f"Cannot resolve bind address {host!r}: {error}") from error
    for port in range(start, 65536):
        if port in reserved:
            continue
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            try:
                if os.name == "nt":
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((address[0], port))
            except OSError as error:
                if error.errno in (errno.EADDRINUSE, errno.EACCES):
                    continue
                raise RunError(f"Cannot bind to {host}:{port}: {error}") from error
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
        # taskkill can itself hang while a console process is handling Ctrl+C,
        # so bound the wait and still terminate the direct child as a fallback.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            try:
                process.kill()
            except OSError:
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if os.name == "nt":
            try:
                process.kill()
            except OSError:
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        try:
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            pass


def process_options() -> dict:
    # Services have their own process group so cleanup covers their descendants.
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example: run.py serve --lan --frontend-port 8080 --backend-port 8000. "
               "Busy frontend/backend ports advance to the next free port.",
    )
    parser.add_argument("command", nargs="?", choices=("serve",), default="serve", help="start the application (default)")
    parser.add_argument("--lan", action="store_true", help="bind both services to 0.0.0.0 (overrides an existing loopback .env default)")
    parser.add_argument("--backend-port", "--backend", type=int, metavar="PORT", help="first backend port to try (1-65535; overrides settings.json; missing default from port_mapping.json)")
    parser.add_argument("--frontend-port", "--frontend", type=int, metavar="PORT", help="first frontend port to try (1-65535; overrides settings.json; missing default from port_mapping.json)")
    parser.add_argument("--host", help="bind address for both services (default: HOST/BACKEND_HOST or 0.0.0.0; use 127.0.0.1 for local access)")
    return parser.parse_args(argv)


def main() -> int:
    load_env_file()
    args = parse_args()
    # Reject explicit mistakes before bootstrapping a development environment.
    for value, label in ((args.backend_port, "backend port"), (args.frontend_port, "frontend port")):
        if value is not None:
            parse_port(value, label)
    runtime = select_runtime()
    if Path(sys.executable).resolve() != runtime.resolve():
        return subprocess.call([str(runtime), str(Path(__file__).resolve()), *sys.argv[1:]])

    try:
        settings = initialize_port_settings()
    except (OSError, ValueError) as error:
        raise RunError(f"Cannot initialize settings: {error}") from error
    requested_backend = parse_port(
        args.backend_port if args.backend_port is not None else settings["backend_port"],
        "backend port",
    )
    requested_frontend = parse_port(
        args.frontend_port if args.frontend_port is not None else settings["frontend_port"],
        "frontend port",
    )

    host = args.host or ("0.0.0.0" if args.lan else os.environ.get("HOST") or os.environ.get("BACKEND_HOST") or "0.0.0.0")
    backend_port = available_port(requested_backend, set(), host=host)
    frontend_bind = host
    frontend_port = available_port(requested_frontend, {backend_port}, host=frontend_bind)
    backend_url = backend_connect_url(host, backend_port)
    frontend_url = f"http://localhost:{frontend_port}" if host == "0.0.0.0" else backend_connect_url(host, frontend_port)
    from backend.network import lan_urls_for_host
    frontend_lan_urls = lan_urls_for_host(host, frontend_port)
    backend_lan_urls = lan_urls_for_host(host, backend_port)

    backend_env = os.environ.copy()
    backend_env["PORT"] = str(backend_port)
    backend_env["HOST"] = host
    proxy_token = secrets.token_urlsafe(32)
    backend_env["STUDY_PROXY_TOKEN"] = proxy_token

    frontend_env = os.environ.copy()
    frontend_env["VITE_BACKEND_URL"] = backend_url
    # This secret is used only by Vite's server-side proxy configuration.
    frontend_env["STUDY_PROXY_TOKEN"] = proxy_token

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
    print("The Study Platform - Universal Intelligence in Researchs")
    print(f"Python:   {sys.executable}")
    print(f"Backend:  {backend_url} (API: {backend_url}/api/problems)")
    print(f"Frontend: {frontend_url}")
    for frontend_lan_url, backend_lan_url in zip(frontend_lan_urls, backend_lan_urls):
        print(f"LAN:      {frontend_lan_url}")
        print(f"LAN API:  {backend_lan_url}/docs")
    if host == "0.0.0.0" and not frontend_lan_urls:
        print(f"LAN:      http://<this-computer-LAN-IP>:{frontend_port}")
    if frontend_lan_urls or host == "0.0.0.0":
        if os.name == "nt":
            print("LAN note: allow Python and Node.js on Private networks if Windows Firewall prompts.")
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
        stop(backend_process)
        stop(frontend_process)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunError as error:
        print(f"[run] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
