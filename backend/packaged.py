"""Run the portable backend and built frontend from one executable."""

from __future__ import annotations

import argparse
import asyncio
import errno
import json
import os
import secrets
import signal
import socket
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles

if not getattr(sys, "frozen", False) and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.settings import initialize_port_settings, load_port_mapping

HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}
CLIENT_FORWARDING_HEADERS = {
    "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-real-ip", "x-study-client-ip", "x-study-proxy-token",
}
_dll_directory_handles: list[object] = []


class RunError(RuntimeError):
    """Raised when the portable application cannot start or keep running."""


def runtime_directory() -> Path:
    # A one-file executable extracts its Python modules to a temporary directory.
    # Public files belong beside server.exe, outside that directory. User data
    # is stored separately through backend.settings.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / "dist" / "Release"


def load_environment(root: Path) -> None:
    env_file = root / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip():
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    # Relative overrides in a portable .env belong beside the executable.
    # Backend module paths point into the disposable one-file extraction.
    for key in ("DATABASE_PATH", "DB_PATH", "JIRA_DB_PATH", "WORKSPACE_STORAGE_DIR", "UPLOAD_DIR"):
        value = os.environ.get(key)
        if value:
            location = Path(value).expanduser()
            if not location.is_absolute():
                os.environ[key] = str((root / location).resolve())


def prepare_external_toolchains() -> None:
    """Retain native app imports without passing bundle DLL paths to children."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    import ctypes

    # Python 3.8+ uses AddDllDirectory for extension imports. Its per-process
    # directory list preserves lazy lameenc/SSL imports without the inherited
    # SetDllDirectory search path installed by PyInstaller's bootloader.
    bundle = str(Path(sys._MEIPASS).resolve())
    handle = os.add_dll_directory(bundle)
    reset = ctypes.windll.kernel32.SetDllDirectoryW
    reset.argtypes = [ctypes.c_wchar_p]
    reset.restype = ctypes.c_int
    if not reset(None):
        handle.close()
        raise RunError(f"Cannot reset the Windows toolchain DLL search path: {ctypes.WinError()}")
    # Keep this registration alive for the whole process, including workers.
    _dll_directory_handles.append(handle)


def runtime_host(root: Path) -> str:
    profile_path = root / "runtime.json"
    if not profile_path.exists():
        return "0.0.0.0"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RunError(f"Cannot read runtime profile at {profile_path}: {error}") from error
    if not isinstance(profile, dict) or profile.get("host") not in ("127.0.0.1", "0.0.0.0"):
        raise RunError(
            f"Invalid runtime profile at {profile_path}: host must be 127.0.0.1 or 0.0.0.0"
        )
    return profile["host"]


def port_number(value: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_args(
    argv: list[str] | None = None, *, default_host: str = "0.0.0.0",
    default_ports: dict | None = None, defaults_path: Path | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend", "--frontend-port", dest="frontend_port", type=port_number,
        help="first frontend port to try (default: settings.json, filled from port_mapping.json)",
    )
    parser.add_argument(
        "--backend", "--backend-port", dest="backend_port", type=port_number,
        help="first backend port to try (default: settings.json, filled from port_mapping.json)",
    )
    parser.add_argument(
        "--host", default=None,
        help="bind address for both services (default: HOST/BACKEND_HOST or runtime profile)",
    )
    parser.add_argument("--lan", action="store_true", help="bind both services to all IPv4 LAN interfaces")
    parser.add_argument("--prepare-settings", action="store_true", help="create settings and populate missing port defaults, then exit")
    parser.add_argument("--ports-file", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.ports_file is not None and not options.prepare_settings:
        parser.error("--ports-file requires --prepare-settings")
    ports = load_port_mapping(defaults_path) if default_ports is None else default_ports
    for field in ("frontend_port", "backend_port"):
        if getattr(options, field) is None:
            setattr(options, field, ports[field])
    if options.host is None:
        options.host = "0.0.0.0" if options.lan else (
            os.environ.get("HOST") or os.environ.get("BACKEND_HOST", default_host)
        )
    return options


def bind_listener(
    host: str, port: int, label: str, reserved: set[int] | None = None,
) -> socket.socket:
    """Reserve the first available port so startup cannot lose a probe race."""
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise RunError(f"Cannot resolve bind address {host!r}: {error}") from error
    last_error: OSError | None = None
    busy_errors = {errno.EADDRINUSE, errno.EACCES, 10048, 10013}
    for candidate in range(port, 65536):
        if candidate in (reserved or set()):
            continue
        retry = False
        for family, kind, protocol, _, address in addresses:
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            listener = socket.socket(family, kind, protocol)
            try:
                if os.name == "nt":
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                else:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if family == socket.AF_INET6:
                    # Keep advertised URLs consistent with the actual family.
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind((address[0], candidate, *address[2:]))
                listener.listen(socket.SOMAXCONN)
                listener.setblocking(False)
                return listener
            except OSError as error:
                listener.close()
                last_error = error
                retry |= error.errno in busy_errors or getattr(error, "winerror", None) in busy_errors
        if not retry:
            break
    raise RunError(
        f"Cannot bind {label} to {host} at or above port {port}: {last_error}"
    ) from last_error


def listener_url(listener: socket.socket) -> str:
    host, port = listener.getsockname()[:2]
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}"


def forwarded_headers(
    headers: httpx.Headers | Headers, *, response: bool = False,
) -> list[tuple[bytes, bytes]]:
    excluded = HOP_BY_HOP_HEADERS | {
        item.strip().lower() for item in headers.get("connection", "").split(",")
    }
    # HTTPX decodes response bodies; let Response compute their new length.
    excluded |= {"host", "content-length"}
    if response:
        excluded.add("content-encoding")
    else:
        excluded |= CLIENT_FORWARDING_HEADERS
    return [(key, value) for key, value in headers.raw
            if key.decode("latin-1").lower() not in excluded]


class SPAStaticFiles(StaticFiles):
    """Serve React routes through index.html while preserving asset 404s."""

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            accepts_html = "text/html" in Headers(scope=scope).get("accept", "")
            if error.status_code != 404 or (Path(path).suffix and not accepts_html):
                raise
            return await super().get_response("index.html", scope)


def create_frontend_app(public: Path, backend_url: str, *, proxy_token: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Local traffic must not depend on the target machine's HTTP proxy setup.
        async with httpx.AsyncClient(
            base_url=backend_url, trust_env=False, timeout=httpx.Timeout(600.0, connect=5.0),
        ) as client:
            application.state.backend_client = client
            yield

    application = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
    )

    async def proxy(request: Request) -> Response:
        path = request.url.path
        if request.url.query:
            path += "?" + request.url.query
        try:
            headers = forwarded_headers(request.headers)
            if request.client is not None:
                headers.extend([
                    (b"x-study-client-ip", request.client.host.encode("latin-1")),
                    (b"x-study-proxy-token", proxy_token.encode("ascii")),
                ])
            upstream = await request.app.state.backend_client.request(
                request.method, path, content=await request.body(),
                headers=headers,
            )
        except httpx.RequestError:
            return JSONResponse({"detail": "Backend is unavailable"}, status_code=502)
        response = Response(content=upstream.content, status_code=upstream.status_code)
        response.raw_headers = forwarded_headers(upstream.headers, response=True) + [
            (b"content-length", str(len(upstream.content)).encode("ascii")),
        ]
        return response

    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    application.add_api_route("/api", proxy, methods=methods)
    application.add_api_route("/api/{path:path}", proxy, methods=methods)
    application.add_api_route("/uploads", proxy, methods=methods)
    application.add_api_route("/uploads/{path:path}", proxy, methods=methods)
    application.mount("/", SPAStaticFiles(directory=public, html=True), name="public")
    return application


class ManagedServer(uvicorn.Server):
    """Two listeners share one process-level signal handler."""

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield

    def install_signal_handlers(self) -> None:
        # Compatibility with Uvicorn releases before capture_signals was added.
        pass


async def serve_applications(
    backend: FastAPI, frontend: FastAPI,
    backend_socket: socket.socket, frontend_socket: socket.socket,
) -> int:
    servers = [
        ManagedServer(uvicorn.Config(
            application, loop="asyncio", http="h11", ws="none", lifespan="on",
            access_log=False, use_colors=False, timeout_graceful_shutdown=5,
            proxy_headers=False,
        ))
        for application in (backend, frontend)
    ]
    stopping = False

    def stop_services(signum: int, frame: object) -> None:
        nonlocal stopping
        for server in servers:
            server.should_exit = True
            if stopping:
                server.force_exit = True
        if not stopping:
            print("\n[run] Stopping both services...", flush=True)
        stopping = True

    async def serve(server: ManagedServer, listener: socket.socket, label: str) -> None:
        try:
            await server.serve(sockets=[listener])
        except SystemExit as error:
            # Keep startup failure inside this task so its sibling can shut down.
            raise RunError(f"{label} failed to start (exit code {error.code})") from error

    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {item: signal.signal(item, stop_services) for item in signals}
    tasks = [
        asyncio.create_task(serve(server, listener, label))
        for server, listener, label in zip(
            servers, (backend_socket, frontend_socket), ("Backend", "Frontend"),
        )
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for server in servers:
            server.should_exit = True
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for item, handler in previous.items():
            signal.signal(item, handler)
    for label, result in zip(("Backend", "Frontend"), results):
        if isinstance(result, BaseException):
            raise RunError(f"{label} failed: {result}") from result
    if not stopping:
        raise RunError("A service stopped unexpectedly; both services have been stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    root = runtime_directory()
    load_environment(root)
    defaults_path = root / "port_mapping.json"
    options = parse_args(argv, default_host=runtime_host(root), defaults_path=defaults_path)
    # Parse first so --help never creates settings or storage. The preparation
    # mode also works before public files or application data are initialized.
    ports = initialize_port_settings(defaults_path=defaults_path)
    if options.prepare_settings:
        export = f"frontend_port={ports['frontend_port']}\nbackend_port={ports['backend_port']}\n"
        if options.ports_file is not None:
            with options.ports_file.open("x", encoding="ascii") as output:
                output.write(export)
        else:
            print(export, end="")
        return 0
    options = parse_args(argv, default_host=runtime_host(root), default_ports=ports)
    public = root / "public"
    if not (public / "index.html").is_file():
        raise RunError(f"Frontend is missing at {public}; rebuild with build.bat")
    prepare_external_toolchains()

    # Backend imports open the Jira database and uploads directory. Resolve
    # persistent user configuration first, outside PyInstaller's extraction.
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.settings import initialize_settings, settings_path
    try:
        data_root = initialize_settings(defaults_path=defaults_path)
    except (ValueError, OSError) as error:
        raise RunError(f"Cannot initialize application settings: {error}") from error
    proxy_token = secrets.token_urlsafe(32)
    os.environ["STUDY_PROXY_TOKEN"] = proxy_token

    backend_socket = bind_listener(options.host, options.backend_port, "backend")
    # Connector callbacks must use the actual port, including a busy-port fallback.
    os.environ["PORT"] = str(backend_socket.getsockname()[1])
    frontend_socket: socket.socket | None = None
    try:
        frontend_socket = bind_listener(
            options.host, options.frontend_port, "frontend", {backend_socket.getsockname()[1]},
        )
        from backend.app import create_unified_app
        from backend.network import lan_urls

        backend_url = listener_url(backend_socket)
        frontend_url = listener_url(frontend_socket)
        app = create_unified_app({"CLIENT_DIST": str(public)})
        frontend = create_frontend_app(public, backend_url, proxy_token=proxy_token)
        print("Starting The Study Platform")
        if backend_socket.getsockname()[1] != options.backend_port:
            print(f"[run] Backend port {options.backend_port} is busy; using {backend_socket.getsockname()[1]}.")
        if frontend_socket.getsockname()[1] != options.frontend_port:
            print(f"[run] Frontend port {options.frontend_port} is busy; using {frontend_socket.getsockname()[1]}.")
        print(f"Backend:  {backend_url} (API docs: {backend_url}/docs)")
        print(f"Frontend: {frontend_url}")
        backend_lan_urls = {urlsplit(url).hostname: url for url in lan_urls(backend_socket)}
        frontend_lan_urls = lan_urls(frontend_socket)
        for url in frontend_lan_urls:
            print(f"LAN:      {url}")
            api_url = backend_lan_urls.get(urlsplit(url).hostname)
            if api_url is not None:
                print(f"LAN API:  {api_url}/docs")
        if frontend_lan_urls:
            print("Open a LAN URL on another device connected to the same network.")
        print(f"Settings: {settings_path()}")
        print(f"Data:     {data_root}")
        print("[run] Press Ctrl+C to stop both services.", flush=True)
        return asyncio.run(serve_applications(app, frontend, backend_socket, frontend_socket))
    finally:
        if frontend_socket is not None:
            frontend_socket.close()
        backend_socket.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except (RunError, OSError, ValueError) as error:
        print(f"[run] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
