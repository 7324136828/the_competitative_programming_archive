"""Portable listener reservations, frontend proxy, and coordinated shutdown."""

import asyncio
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import tempfile
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from starlette.testclient import TestClient

from backend import packaged


class PortableArgumentsTests(unittest.TestCase):
    def test_saved_ports_and_cli_overrides_are_independent(self):
        with patch.dict(os.environ, {"FRONTEND_PORT": "6000", "PORT": "9000"}, clear=True):
            ports = {"frontend_port": 5102, "backend_port": 8013}
            args = packaged.parse_args(["--backend", "8200"], default_ports=ports)
            self.assertEqual((args.frontend_port, args.backend_port), (5102, 8200))

    def test_prepare_settings_exports_persisted_ports_without_starting_services(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APPDATA": str(Path(directory) / "roaming"), "TEMP": str(Path(directory) / "temp"),
        }), patch.object(packaged, "runtime_directory", return_value=Path(directory)), patch.object(
            packaged, "bind_listener"
        ) as bind:
            root = Path(directory)
            mapping = root / "port_mapping.json"
            mapping.write_text('{"frontend_port": 4510, "backend_port": 8420}')
            exported = root / "ports.txt"
            self.assertEqual(packaged.main(["--prepare-settings", "--ports-file", str(exported)]), 0)
            self.assertEqual(exported.read_text(), "frontend_port=4510\nbackend_port=8420\n")
            location = root / "roaming" / "the_study_platform" / "settings.json"
            self.assertEqual(json.loads(location.read_text()), {"frontend_port": 4510, "backend_port": 8420})
            payload = {"frontend_port": 5105, "data_dir": str(root / "stored data"), "extra": "preserved"}
            location.write_text(json.dumps(payload))
            exported.unlink()
            self.assertEqual(packaged.main(["--prepare-settings", "--ports-file", str(exported)]), 0)
            self.assertEqual(exported.read_text(), "frontend_port=5105\nbackend_port=8420\n")
            self.assertEqual(json.loads(location.read_text()), {**payload, "backend_port": 8420})
            self.assertFalse((root / "stored data").exists())
            mapping.write_text('{"frontend_port": 4520, "backend_port": 8430}')
            original = location.read_bytes()
            exported.unlink()
            self.assertEqual(packaged.main(["--prepare-settings", "--ports-file", str(exported)]), 0)
            self.assertEqual(exported.read_text(), "frontend_port=5105\nbackend_port=8420\n")
            self.assertEqual(location.read_bytes(), original)
            bind.assert_not_called()

    def test_help_never_creates_user_settings(self):
        with patch.object(packaged, "initialize_port_settings") as prepare, patch.object(
            packaged, "load_port_mapping"
        ) as mapping, patch("sys.stdout"):
            with self.assertRaises(SystemExit) as result:
                packaged.main(["--help"])
            self.assertEqual(result.exception.code, 0)
        prepare.assert_not_called()
        mapping.assert_not_called()

    def test_missing_or_invalid_artifact_mapping_stops_before_settings_and_services(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APPDATA": str(Path(directory) / "roaming"),
        }), patch.object(packaged, "runtime_directory", return_value=Path(directory)), patch.object(
            packaged, "bind_listener"
        ) as bind:
            root = Path(directory)
            mapping = root / "port_mapping.json"
            location = root / "roaming" / "the_study_platform" / "settings.json"
            location.parent.mkdir(parents=True)
            original = '{"frontend_port": 4510, "backend_port": 8420, "data_dir": ""}'
            location.write_text(original)
            for contents in (None, "{broken", "[]", "{}", '{"frontend_port": 0, "backend_port": 8420}'):
                with self.subTest(contents=contents):
                    if contents is None:
                        mapping.unlink(missing_ok=True)
                    else:
                        mapping.write_text(contents)
                    for arguments in ([], ["--prepare-settings"]):
                        with self.assertRaises((OSError, ValueError)) as error:
                            packaged.main(arguments)
                        self.assertIn("port_mapping.json", str(error.exception))
                        self.assertEqual(location.read_text(), original)
            bind.assert_not_called()

    def test_ports_file_requires_preparation_mode(self):
        with patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                packaged.parse_args(["--ports-file", "unexpected.txt"])

    def test_profile_host_and_cli_ports_have_consistent_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(packaged, "load_port_mapping", return_value={
            "frontend_port": 4510, "backend_port": 8420,
        }):
            args = packaged.parse_args([], default_host="127.0.0.1")
            self.assertEqual((args.host, args.frontend_port, args.backend_port), ("127.0.0.1", 4510, 8420))
            args = packaged.parse_args(["--frontend", "5200", "--backend-port", "3200", "--host", "study-pc"])
            self.assertEqual((args.host, args.frontend_port, args.backend_port), ("study-pc", 5200, 3200))
            args = packaged.parse_args(["--lan"], default_host="127.0.0.1")
            self.assertEqual(args.host, "0.0.0.0")
            args = packaged.parse_args(["--lan", "--host", "127.0.0.1"])
            self.assertEqual(args.host, "127.0.0.1")

    def test_runtime_profile_rejects_corrupt_or_unknown_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(packaged.runtime_host(root), "0.0.0.0")
            profile = root / "runtime.json"
            profile.write_text(json.dumps({"host": "127.0.0.1"}))
            self.assertEqual(packaged.runtime_host(root), "127.0.0.1")
            for payload in ('{"host": "example.com"}', '[]', '{invalid'):
                profile.write_text(payload)
                with self.assertRaises(packaged.RunError):
                    packaged.runtime_host(root)

    def test_dotenv_ports_do_not_override_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BACKEND_PORT": "3100"}, clear=True):
            root = Path(directory)
            (root / ".env").write_text('BACKEND_PORT=3200\nFRONTEND_PORT="5300"\n')
            packaged.load_environment(root)
            args = packaged.parse_args([], default_ports={"frontend_port": 5101, "backend_port": 8012})
            self.assertEqual((args.backend_port, args.frontend_port), (8012, 5101))
            self.assertEqual(os.environ["BACKEND_PORT"], "3100")
            self.assertEqual(os.environ["FRONTEND_PORT"], "5300")

    def test_relative_storage_overrides_use_the_persistent_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            values = {
                "DATABASE_PATH": "data/main.db", "DB_PATH": "data/alias.db",
                "JIRA_DB_PATH": "data/jira.db", "WORKSPACE_STORAGE_DIR": "workspace",
                "UPLOAD_DIR": "uploads",
            }
            (root / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()))
            packaged.load_environment(root)
            for key, value in values.items():
                self.assertEqual(os.environ[key], str((root / value).resolve()))
            absolute = str(root / "custom.db")
            os.environ["DATABASE_PATH"] = absolute
            packaged.load_environment(root)
            self.assertEqual(os.environ["DATABASE_PATH"], absolute)

    def test_startup_publishes_actual_backend_port_before_application_creation(self):
        root = Path(__file__).resolve().parent / "portable-runtime"
        backend_socket, frontend_socket = MagicMock(), MagicMock()
        backend_socket.getsockname.return_value = ("127.0.0.1", 8129)
        frontend_socket.getsockname.return_value = ("127.0.0.1", 5129)
        backend_app, frontend_app = MagicMock(), MagicMock()
        factory_ports = []

        def create_app(configuration):
            factory_ports.append(os.environ.get("PORT"))
            return backend_app

        app_module = ModuleType("backend.app")
        app_module.create_unified_app = MagicMock(side_effect=create_app)
        with patch.dict(os.environ, {"PORT": "3001"}, clear=True), patch.dict(
            packaged.sys.modules, {"backend.app": app_module}
        ), patch.object(packaged.sys, "frozen", True, create=True), patch.object(
            packaged, "runtime_directory", return_value=root
        ), patch.object(packaged, "runtime_host", return_value="127.0.0.1"), patch.object(
            packaged, "load_environment"
        ), patch.object(packaged, "initialize_port_settings", return_value={
            "backend_port": 8011, "frontend_port": 5100,
        }), patch.object(packaged, "load_port_mapping", return_value={
            "backend_port": 8011, "frontend_port": 5100,
        }), patch.object(Path, "is_file", return_value=True), patch.object(
            packaged, "prepare_external_toolchains"
        ), patch("backend.settings.initialize_settings", return_value=root / "data"), patch(
            "backend.settings.settings_path", return_value=root / "settings.json"
        ), patch.object(packaged, "bind_listener", side_effect=[backend_socket, frontend_socket]) as bind, patch.object(
            packaged, "create_frontend_app", return_value=frontend_app
        ) as create_frontend, patch("backend.network.lan_urls", return_value=[]), patch.object(
            packaged, "serve_applications", new_callable=AsyncMock, return_value=0
        ) as serve, patch("builtins.print"):
            self.assertEqual(packaged.main([]), 0)
            self.assertEqual(os.environ["PORT"], "8129")

        self.assertEqual(factory_ports, ["8129"])
        app_module.create_unified_app.assert_called_once_with({"CLIENT_DIST": str(root / "public")})
        self.assertEqual(bind.call_args_list[0].args, ("127.0.0.1", 8011, "backend"))
        self.assertEqual(bind.call_args_list[1].args, ("127.0.0.1", 5100, "frontend", {8129}))
        self.assertEqual(create_frontend.call_args.args, (root / "public", "http://127.0.0.1:8129"))
        serve.assert_awaited_once_with(backend_app, frontend_app, backend_socket, frontend_socket)
        backend_socket.close.assert_called_once_with()
        frontend_socket.close.assert_called_once_with()


class PortableDLLTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows DLL search paths")
    def test_frozen_runtime_preserves_native_imports_without_inherited_dll_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            packaged.sys, "frozen", True, create=True
        ), patch.object(packaged.sys, "_MEIPASS", directory, create=True), patch.object(
            packaged.os, "add_dll_directory"
        ) as add_directory, patch("ctypes.windll.kernel32.SetDllDirectoryW", return_value=1) as reset, patch.object(
            packaged, "_dll_directory_handles", []
        ):
            packaged.prepare_external_toolchains()
            add_directory.assert_called_once_with(str(Path(directory).resolve()))
            reset.assert_called_once_with(None)
            self.assertEqual(packaged._dll_directory_handles, [add_directory.return_value])
            add_directory.return_value.close.assert_not_called()

    def test_source_runtime_does_not_change_native_library_paths(self):
        with patch.object(packaged.sys, "frozen", False, create=True), patch.object(
            packaged.os, "add_dll_directory", create=True
        ) as add_directory:
            packaged.prepare_external_toolchains()
        add_directory.assert_not_called()


class PortableSocketTests(unittest.TestCase):
    def test_occupied_port_advances_and_stays_reserved(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            busy_port = occupied.getsockname()[1]
            if busy_port == 65535:
                self.skipTest("Ephemeral port is at end of range")
            listener = packaged.bind_listener("127.0.0.1", busy_port, "backend")
            self.addCleanup(listener.close)
            self.assertGreater(listener.getsockname()[1], busy_port)
            self.assertEqual(listener.getblocking(), False)
            with socket.socket() as probe:
                with self.assertRaises(OSError):
                    probe.bind(listener.getsockname())

    def test_shared_requested_ports_are_separated_and_urls_use_actual_bindings(self):
        backend = packaged.bind_listener("localhost", 49000, "backend")
        self.addCleanup(backend.close)
        backend_port = backend.getsockname()[1]
        frontend = packaged.bind_listener("localhost", backend_port, "frontend", {backend_port})
        self.addCleanup(frontend.close)
        self.assertGreater(frontend.getsockname()[1], backend_port)
        self.assertNotIn("localhost", packaged.listener_url(backend))

    def test_ipv6_listener_uses_bracketed_loopback_url(self):
        try:
            listener = packaged.bind_listener("::1", 49010, "IPv6 backend")
        except (packaged.RunError, OSError):
            self.skipTest("IPv6 is unavailable")
        self.addCleanup(listener.close)
        self.assertEqual(listener.family, socket.AF_INET6)
        self.assertEqual(listener.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY), 1)
        self.assertEqual(packaged.listener_url(listener), f"http://[::1]:{listener.getsockname()[1]}")

    def test_unresolvable_host_fails_without_searching_ports(self):
        with patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("unknown host")):
            with self.assertRaisesRegex(packaged.RunError, "Cannot resolve"):
                packaged.bind_listener("invalid-host", 3001, "backend")


class PortableProxyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.public = Path(self.directory.name)
        (self.public / "index.html").write_text("<html>The Study Platform</html>")
        (self.public / "assets").mkdir()
        (self.public / "assets" / "app.js").write_text("console.log('study')")

    def client(self, handler):
        original_client = httpx.AsyncClient

        def backend_client(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        self.enterContext(patch.object(packaged.httpx, "AsyncClient", side_effect=backend_client))
        app = packaged.create_frontend_app(self.public, "http://127.0.0.1:3001", proxy_token="shared-secret")
        return self.enterContext(TestClient(app, client=("192.168.1.55", 5000)))

    def test_proxy_preserves_query_uploads_and_strips_spoofed_identity(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(201, json={"success": True})

        client = self.client(handler)
        response = client.post("/api/problems/upload?source=lan", content=b"multipart content", headers={
            "Content-Type": "multipart/form-data; boundary=study", "Connection": "x-extra",
            "X-Extra": "remove", "X-Forwarded-For": "127.0.0.1",
            "X-Study-Client-IP": "127.0.0.1", "X-Study-Proxy-Token": "forged",
        })
        self.assertEqual(response.status_code, 201)
        request = requests[0]
        self.assertEqual(str(request.url), "http://127.0.0.1:3001/api/problems/upload?source=lan")
        self.assertEqual(request.content, b"multipart content")
        self.assertIn("multipart/form-data", request.headers["content-type"])
        self.assertEqual(request.headers["x-study-client-ip"], "192.168.1.55")
        self.assertEqual(request.headers["x-study-proxy-token"], "shared-secret")
        self.assertNotIn("x-forwarded-for", request.headers)
        self.assertNotIn("x-extra", request.headers)
        self.assertEqual(client.get("/uploads/sample.txt").status_code, 201)
        self.assertEqual(requests[-1].url.path, "/uploads/sample.txt")

    def test_compressed_responses_keep_valid_length_and_headers(self):
        def handler(request):
            return httpx.Response(206, content=gzip.compress(b"narration"), headers={
                "Content-Encoding": "gzip", "Content-Type": "audio/mpeg", "ETag": '"asset"',
                "Connection": "x-extra", "X-Extra": "remove",
            })

        response = self.client(handler).get("/api/audio/test.mp3")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"narration")
        self.assertNotIn("content-encoding", response.headers)
        self.assertNotIn("x-extra", response.headers)
        self.assertEqual(int(response.headers["content-length"]), len(response.content))
        self.assertEqual(response.headers["etag"], '"asset"')

    def test_backend_failure_returns_502_and_spa_routes_keep_working(self):
        def handler(request):
            raise httpx.ConnectError("Backend stopped", request=request)

        client = self.client(handler)
        self.assertEqual(client.get("/api/health").status_code, 502)
        self.assertEqual(client.get("/settings").status_code, 200)
        self.assertEqual(client.get("/projects/42/issues").text, "<html>The Study Platform</html>")
        self.assertEqual(client.get("/assets/app.js").status_code, 200)
        self.assertEqual(client.get("/assets/missing.js").status_code, 404)


class PortableLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_service_failure_stops_sibling_and_restores_signals(self):
        servers = []

        class FakeServer:
            def __init__(self, config):
                self.config = config
                self.should_exit = False
                self.force_exit = False
                servers.append(self)

            async def serve(self, sockets):
                if self is servers[0]:
                    raise RuntimeError("Backend startup failed")
                while not self.should_exit:
                    await asyncio.sleep(0)

        previous = signal.getsignal(signal.SIGTERM)
        with patch.object(packaged, "ManagedServer", FakeServer):
            with self.assertRaisesRegex(packaged.RunError, "Backend startup failed"):
                await packaged.serve_applications(None, None, None, None)
        self.assertTrue(all(server.should_exit for server in servers))
        self.assertTrue(all(server.config.proxy_headers is False for server in servers))
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)


if __name__ == "__main__":
    unittest.main()
