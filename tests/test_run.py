"""Process ownership, LAN sharing, and port checks for the root launcher."""

import errno
import os
import signal
import subprocess
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import launcher_config
import run as launcher


class LauncherTestCase(unittest.TestCase):
    def main_environment(self):
        self.enterContext(patch.dict(os.environ, {
            "CONNECTOR_BASE_URL": "http://127.0.0.1:8301/v1",
        }, clear=True))
        self.enterContext(patch.object(launcher, "load_env_file"))
        self.enterContext(patch.object(launcher, "parse_args", return_value=SimpleNamespace(
            backend_port=None, frontend_port=None, host="127.0.0.1", lan=False,
            command="serve",
        )))
        self.enterContext(patch.object(launcher, "select_runtime", return_value=Path(sys.executable)))
        self.enterContext(patch.object(launcher, "initialize_port_settings", return_value={
            "backend_port": 8011, "frontend_port": 5100,
        }))
        ports = self.enterContext(patch.object(launcher, "available_port", side_effect=[8011, 5100]))
        self.enterContext(patch.object(launcher.shutil, "which", return_value="npm"))
        self.enterContext(patch.object(Path, "is_dir", return_value=True))
        self.enterContext(patch.object(launcher.time, "sleep", side_effect=KeyboardInterrupt))
        backend, frontend = MagicMock(), MagicMock()
        backend.poll.return_value = frontend.poll.return_value = None
        self.enterContext(patch.object(launcher.subprocess, "Popen", side_effect=[backend, frontend]))
        stop = self.enterContext(patch.object(launcher, "stop"))
        return stop, ports, backend, frontend


class RootRunTests(LauncherTestCase):
    def test_ctrl_c_stops_only_codejudge_services(self):
        stop, ports, backend, frontend = self.main_environment()
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in stop.call_args_list], [backend, frontend])
        self.assertEqual(ports.call_args_list[0].args[1], set())
        self.assertEqual(ports.call_args_list[1].args[1], {8011})
        self.assertEqual(len(launcher.subprocess.Popen.call_args_list), 2)

    def test_termination_signal_runs_cleanup_and_restores_handler(self):
        stop, _, backend, frontend = self.main_environment()
        previous = signal.getsignal(signal.SIGTERM)
        launcher.time.sleep.side_effect = lambda _: signal.raise_signal(signal.SIGTERM)
        self.assertEqual(launcher.main(), 0)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual([call.args[0] for call in stop.call_args_list], [backend, frontend])

    def test_backend_exit_stops_frontend(self):
        stop, _, backend, frontend = self.main_environment()
        backend.poll.return_value = 2
        launcher.time.sleep.side_effect = None
        self.assertEqual(launcher.main(), 2)
        self.assertEqual([call.args[0] for call in stop.call_args_list], [backend, frontend])

    def test_windows_shutdown_bounds_taskkill_wait(self):
        process = MagicMock(pid=1234)
        process.poll.return_value = None
        with patch.object(launcher.os, "name", "nt"), patch.object(
            launcher.subprocess, "run"
        ) as taskkill:
            launcher.stop(process)
        self.assertEqual(taskkill.call_args.kwargs["timeout"], 5)
        process.wait.assert_called_once_with(timeout=5)

    def test_windows_shutdown_kills_child_if_taskkill_hangs(self):
        process = MagicMock(pid=1234)
        process.poll.return_value = None
        with patch.object(launcher.os, "name", "nt"), patch.object(
            launcher.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("taskkill", 5),
        ):
            launcher.stop(process)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    def test_dotenv_keeps_terminal_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONNECTOR_BASE_URL": "http://terminal:8301/v1"}, clear=True
        ):
            path = Path(directory) / ".env"
            path.write_text(
                'CONNECTOR_BASE_URL="http://file:8301/v1"\nCONNECTOR_SPEECH_TIMEOUT_SECONDS=200\n',
                encoding="utf-8",
            )
            launcher_config.load_env_file(path)
            self.assertEqual(os.environ["CONNECTOR_BASE_URL"], "http://terminal:8301/v1")
            self.assertEqual(os.environ["CONNECTOR_SPEECH_TIMEOUT_SECONDS"], "200")


class LANLauncherTests(LauncherTestCase):
    def test_serving_command_accepts_lan_and_forwarded_options(self):
        with patch.object(sys, "argv", ["run.py", "serve", "--lan", "--frontend-port", "5190"]):
            args = launcher.parse_args()
        self.assertEqual(args.command, "serve")
        self.assertTrue(args.lan)
        self.assertEqual(args.frontend_port, 5190)
        with patch.object(sys, "argv", ["run.py"]):
            self.assertFalse(launcher.parse_args().lan)

    def test_detected_lan_addresses_exclude_loopback_and_duplicates(self):
        addresses = ["127.0.0.1", "192.168.1.20", "192.168.1.20", "10.0.0.2", "169.254.1.2", "0.0.0.0", "224.0.0.1"]
        entries = [(launcher.socket.AF_INET, launcher.socket.SOCK_STREAM, 0, "", (ip, 0)) for ip in addresses]
        with patch.object(launcher.socket, "getaddrinfo", return_value=entries):
            self.assertEqual(launcher.lan_addresses(), ["10.0.0.2", "192.168.1.20"])
        with patch.object(launcher.socket, "getaddrinfo", side_effect=OSError):
            self.assertEqual(launcher.lan_addresses(), [])

    def test_proxy_uses_connectable_address_for_wildcard_backend(self):
        self.assertEqual(launcher.backend_connect_url("0.0.0.0", 3001), "http://127.0.0.1:3001")
        self.assertEqual(launcher.backend_connect_url("::", 3001), "http://[::1]:3001")
        self.assertEqual(launcher.backend_connect_url("192.168.1.20", 3001), "http://192.168.1.20:3001")

    def test_lan_exposes_frontend_and_routes_api_to_local_backend(self):
        _, ports, _, _ = self.main_environment()
        launcher.parse_args.return_value.lan = True
        launcher.parse_args.return_value.host = None
        with patch("backend.network.lan_urls_for_host", side_effect=[
            ["http://192.168.1.20:5100"], ["http://192.168.1.20:8011"],
        ]), patch("builtins.print") as output:
            self.assertEqual(launcher.main(), 0)
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertIn("0.0.0.0", backend.args[0])
        self.assertEqual(frontend.args[0][-2:], ["--host", "0.0.0.0"])
        self.assertEqual(frontend.kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:8011")
        self.assertEqual(ports.call_args_list[1].kwargs["host"], "0.0.0.0")
        self.assertTrue(any("http://192.168.1.20:5100" in str(call) for call in output.call_args_list))
        self.assertTrue(any("http://192.168.1.20:8011/docs" in str(call) for call in output.call_args_list))

    def test_default_host_shares_both_services_on_lan(self):
        self.main_environment()
        launcher.parse_args.return_value.host = None
        self.assertEqual(launcher.main(), 0)
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.kwargs["env"]["HOST"], "0.0.0.0")
        self.assertEqual(frontend.args[0][-2:], ["--host", "0.0.0.0"])

    def test_existing_env_host_and_explicit_host_bind_both_services(self):
        self.main_environment()
        args = launcher.parse_args.return_value
        args.host = None
        os.environ["BACKEND_HOST"] = "127.0.0.1"
        self.assertEqual(launcher.main(), 0)
        frontend = launcher.subprocess.Popen.call_args_list[-1]
        self.assertEqual(frontend.args[0][-2:], ["--host", "127.0.0.1"])

    def test_proxy_credentials_are_shared_only_with_owned_services(self):
        self.main_environment()
        self.assertEqual(launcher.main(), 0)
        backend, frontend = launcher.subprocess.Popen.call_args_list
        token = backend.kwargs["env"]["STUDY_PROXY_TOKEN"]
        self.assertGreater(len(token), 30)
        self.assertEqual(frontend.kwargs["env"]["STUDY_PROXY_TOKEN"], token)
        self.assertNotIn("STUDY_PROXY_TOKEN", os.environ)
        self.assertNotIn("VITE_STUDY_PROXY_TOKEN", frontend.kwargs["env"])

    def test_explicit_host_overrides_lan_flag(self):
        self.main_environment()
        launcher.parse_args.return_value.lan = True
        self.assertEqual(launcher.main(), 0)
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.kwargs["env"]["HOST"], "127.0.0.1")
        self.assertEqual(frontend.args[0][-2:], ["--host", "127.0.0.1"])


class PortLauncherTests(LauncherTestCase):
    def test_sample_port_aliases(self):
        args = launcher.parse_args(["--frontend", "4000", "--backend", "9000"])
        self.assertEqual((args.frontend_port, args.backend_port), (4000, 9000))

    def test_both_port_flags_are_forwarded_with_or_without_serve(self):
        for command in ([], ["serve"]):
            with self.subTest(command=command), patch.object(
                sys, "argv", ["run.py", *command, "--frontend-port", "5200", "--backend-port", "3100"]
            ):
                args = launcher.parse_args()
                self.assertEqual((args.frontend_port, args.backend_port), (5200, 3100))

    def test_cli_ports_override_settings_and_environment_and_reach_both_services(self):
        _, ports, _, _ = self.main_environment()
        launcher.parse_args.return_value.backend_port = 3100
        launcher.parse_args.return_value.frontend_port = 5200
        os.environ.update(PORT="3200", BACKEND_PORT="3300", FRONTEND_PORT="5300")
        ports.side_effect = [3100, 5200]
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [3100, 5200])
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.args[0][-2:], ["--port", "3100"])
        self.assertEqual(backend.kwargs["env"]["PORT"], "3100")
        self.assertEqual(frontend.args[0][-5:], ["--port", "5200", "--strictPort", "--host", "127.0.0.1"])
        launcher.initialize_port_settings.assert_called_once_with()

    def test_default_ports_when_no_overrides_are_configured(self):
        _, ports, _, _ = self.main_environment()
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [8011, 5100])

    def test_saved_ports_override_dotenv_and_terminal_ports(self):
        _, ports, _, _ = self.main_environment()
        launcher.initialize_port_settings.return_value = {"backend_port": 8112, "frontend_port": 5112}
        ports.side_effect = [8112, 5112]
        os.environ["PORT"] = "3400"
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("PORT=3500\nBACKEND_PORT=3600\nFRONTEND_PORT=5400\n", encoding="utf-8")
            launcher.load_env_file.side_effect = lambda: launcher_config.load_env_file(env_file)
            self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [8112, 5112])
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.args[0][-2:], ["--port", "8112"])
        self.assertEqual(backend.kwargs["env"]["PORT"], "8112")
        self.assertEqual(frontend.args[0][-5:], ["--port", "5112", "--strictPort", "--host", "127.0.0.1"])
        self.assertEqual(frontend.kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:8112")

    def test_old_port_environment_does_not_mask_settings_defaults(self):
        _, ports, _, _ = self.main_environment()
        os.environ.update(BACKEND_PORT="3500", FRONTEND_PORT="5500")
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [8011, 5100])

    def test_one_cli_override_preserves_other_saved_port(self):
        _, ports, _, _ = self.main_environment()
        launcher.parse_args.return_value.frontend_port = 5401
        launcher.initialize_port_settings.return_value = {"backend_port": 8123, "frontend_port": 5123}
        ports.side_effect = [8123, 5401]
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [8123, 5401])

    def test_settings_errors_stop_before_service_start(self):
        self.main_environment()
        for error in (ValueError("backend_port is invalid"), OSError("settings.json is not writable")):
            with self.subTest(error=error):
                launcher.initialize_port_settings.side_effect = error
                with self.assertRaisesRegex(launcher.RunError, "Cannot initialize settings"):
                    launcher.main()
        launcher.available_port.assert_not_called()
        launcher.subprocess.Popen.assert_not_called()

    def test_invalid_explicit_ports_fail_before_runtime_setup(self):
        self.main_environment()
        for flag in ("backend_port", "frontend_port"):
            for value in (0, -1, 65536):
                with self.subTest(flag=flag, value=value):
                    args = launcher.parse_args.return_value
                    args.backend_port = args.frontend_port = None
                    setattr(args, flag, value)
                    with self.assertRaisesRegex(launcher.RunError, "between 1 and 65535"):
                        launcher.main()
        launcher.select_runtime.assert_not_called()
        launcher.initialize_port_settings.assert_not_called()
        launcher.subprocess.Popen.assert_not_called()

    def test_fallback_ports_are_reserved_and_proxy_tracks_selected_backend(self):
        _, ports, _, _ = self.main_environment()
        args = launcher.parse_args.return_value
        args.backend_port = args.frontend_port = 5200
        args.host = "0.0.0.0"
        args.lan = True
        ports.side_effect = [5201, 5202]
        with patch.object(launcher, "lan_addresses", return_value=["192.168.1.20"]):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(ports.call_args_list[0].args, (5200, set()))
        self.assertEqual(ports.call_args_list[1].args, (5200, {5201}))
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.args[0][-4:], ["--host", "0.0.0.0", "--port", "5201"])
        self.assertEqual(frontend.kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:5201")

    def test_port_search_skips_busy_and_reserved_ports(self):
        with patch.object(launcher.socket, "socket") as make_socket:
            bind = make_socket.return_value.__enter__.return_value.bind
            bind.side_effect = [OSError(errno.EADDRINUSE, "busy"), None]
            self.assertEqual(launcher.available_port(5200, {5201}, host="0.0.0.0"), 5202)
        self.assertEqual([call.args[0] for call in bind.call_args_list], [("0.0.0.0", 5200), ("0.0.0.0", 5202)])

    def test_ipv6_backend_port_probe_uses_ipv6_socket(self):
        with patch.object(launcher.socket, "socket") as make_socket:
            self.assertEqual(launcher.available_port(3100, host="::"), 3100)
        make_socket.assert_called_once_with(launcher.socket.AF_INET6, launcher.socket.SOCK_STREAM)
        make_socket.return_value.__enter__.return_value.bind.assert_called_once_with(("::", 3100))

    def test_invalid_host_and_bind_errors_fail_without_scanning_ports(self):
        with patch.object(launcher.socket, "getaddrinfo", side_effect=OSError("unknown host")):
            with self.assertRaisesRegex(launcher.RunError, "Cannot resolve"):
                launcher.available_port(3001, host="invalid-host")
        with patch.object(launcher.socket, "socket") as make_socket:
            bind = make_socket.return_value.__enter__.return_value.bind
            bind.side_effect = OSError(errno.EADDRNOTAVAIL, "invalid adapter")
            with self.assertRaisesRegex(launcher.RunError, "Cannot bind"):
                launcher.available_port(3001)
            bind.assert_called_once()


if __name__ == "__main__":
    unittest.main()
