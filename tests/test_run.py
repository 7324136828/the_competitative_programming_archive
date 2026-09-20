"""Service ownership, readiness, and device checks for the root launcher."""

import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import launcher_config
import run as launcher


HEALTH = {"service": "python-kokoro", "status": "ok", "python": "3.12.10", "device": "cuda"}


class KokoroLauncherTests(unittest.TestCase):
    def test_existing_compatible_service_is_reused_without_owning_a_process(self):
        with patch.object(launcher, "read_kokoro_health", return_value=HEALTH), patch.object(launcher.subprocess, "Popen") as spawn:
            self.assertIsNone(launcher.start_kokoro("http://127.0.0.1:8880/v1", "cuda"))
        spawn.assert_not_called()

    def test_existing_cpu_or_wrong_python_service_cannot_satisfy_cuda(self):
        for health in ({**HEALTH, "device": "cpu"}, {**HEALTH, "python": "3.14.0"}, {"status": "ok"}):
            with self.subTest(health=health), patch.object(launcher, "read_kokoro_health", return_value=health), patch.object(launcher.subprocess, "Popen") as spawn:
                with self.assertRaises(launcher.RunError):
                    launcher.start_kokoro("http://127.0.0.1:8880", "cuda")
                spawn.assert_not_called()

    def test_external_unavailable_service_is_not_started_locally(self):
        with patch.object(launcher, "read_kokoro_health", return_value=None), patch.object(launcher.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(launcher.RunError, "external Kokoro"):
                launcher.start_kokoro("https://speech.example.com/v1", "cuda")
        spawn.assert_not_called()

    def test_health_url_and_bad_configuration(self):
        self.assertEqual(launcher.kokoro_url("http://localhost:8880/v1/")[2], "http://localhost:8880/health")
        for value in ("http://localhost:0", "http://localhost:70000", "file:///tmp/test", "http://user:secret@localhost", "http://localhost/?key=secret"):
            with self.subTest(value=value), self.assertRaises(launcher.RunError):
                launcher.kokoro_url(value)

    def child_environment(self, healths):
        self.enterContext(patch.object(launcher.KOKORO_PYTHON.__class__, "is_file", return_value=True))
        self.enterContext(patch.object(launcher.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
        self.enterContext(patch.object(launcher.socket, "socket"))
        self.enterContext(patch.object(launcher.time, "sleep"))
        self.enterContext(patch.object(launcher, "read_kokoro_health", side_effect=healths))
        child = MagicMock()
        child.poll.return_value = None
        spawn = self.enterContext(patch.object(launcher.subprocess, "Popen", return_value=child))
        stop = self.enterContext(patch.object(launcher, "stop"))
        return child, spawn, stop

    def test_new_service_waits_for_ready_and_uses_dedicated_interpreter(self):
        child, spawn, stop = self.child_environment([None, None, HEALTH])
        self.assertIs(launcher.start_kokoro("http://127.0.0.1:8880", "cuda"), child)
        arguments = spawn.call_args.args[0]
        self.assertEqual(arguments[0], str(launcher.KOKORO_PYTHON))
        self.assertIn(str(launcher.KOKORO_SERVER), arguments)
        self.assertEqual(arguments[-2:], ["--device", "cuda"])
        stop.assert_not_called()

    def test_failed_startup_cleans_up_owned_child(self):
        child, _, stop = self.child_environment([None])
        child.poll.return_value = 1
        with self.assertRaisesRegex(launcher.RunError, "exited during startup"):
            launcher.start_kokoro("http://127.0.0.1:8880", "cuda")
        stop.assert_called_once_with(child)

    def test_startup_timeout_cleans_up_owned_child(self):
        child, _, stop = self.child_environment([None])
        with self.assertRaisesRegex(launcher.RunError, "did not become healthy"):
            launcher.start_kokoro("http://127.0.0.1:8880", "cuda", timeout=0)
        stop.assert_called_once_with(child)

    def test_wrong_device_after_startup_cleans_up_owned_child(self):
        child, _, stop = self.child_environment([None, {**HEALTH, "device": "cpu"}])
        with self.assertRaisesRegex(launcher.RunError, "cuda was requested"):
            launcher.start_kokoro("http://127.0.0.1:8880", "cuda")
        stop.assert_called_once_with(child)


class RootRunTests(unittest.TestCase):
    def main_environment(self, *, skip=False, kokoro=None):
        self.enterContext(patch.dict(os.environ, {"KOKORO_DEVICE": "cuda", "KOKORO_BASE_URL": "http://127.0.0.1:8880"}, clear=True))
        self.enterContext(patch.object(launcher, "load_env_file"))
        self.enterContext(patch.object(launcher, "parse_args", return_value=SimpleNamespace(kokoro_device="cpu", skip_kokoro=skip, backend_port=None, frontend_port=None, host="127.0.0.1", lan=False, command="serve")))
        self.enterContext(patch.object(launcher, "select_runtime", return_value=Path(sys.executable)))
        ports = self.enterContext(patch.object(launcher, "available_port", side_effect=[3001, 5173]))
        self.enterContext(patch.object(launcher.shutil, "which", return_value="npm"))
        self.enterContext(patch.object(Path, "is_dir", return_value=True))
        self.enterContext(patch.object(launcher.time, "sleep", side_effect=KeyboardInterrupt))
        backend, frontend = MagicMock(), MagicMock()
        backend.poll.return_value = frontend.poll.return_value = None
        self.enterContext(patch.object(launcher.subprocess, "Popen", side_effect=[backend, frontend]))
        start = self.enterContext(patch.object(launcher, "start_kokoro", return_value=kokoro))
        stop = self.enterContext(patch.object(launcher, "stop"))
        return start, stop, ports, backend, frontend

    def test_ctrl_c_stops_owned_services_and_cli_device_overrides_environment(self):
        kokoro = MagicMock()
        kokoro.poll.return_value = None
        start, stop, ports, backend, frontend = self.main_environment(kokoro=kokoro)
        self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("http://127.0.0.1:8880", "cpu")
        self.assertEqual(os.environ["KOKORO_DEVICE"], "cpu")
        self.assertEqual([call.args[0] for call in stop.call_args_list], [frontend, backend, kokoro])
        self.assertEqual(ports.call_args_list[0].args[1], {8880})
        self.assertEqual(ports.call_args_list[1].args[1], {3001, 8880})

    def test_reused_service_has_no_process_to_stop(self):
        _, stop, _, backend, frontend = self.main_environment(kokoro=None)
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in stop.call_args_list if call.args[0] is not None], [frontend, backend])

    def test_explicit_skip_leaves_kokoro_unmanaged(self):
        start, _, ports, _, _ = self.main_environment(skip=True)
        self.assertEqual(launcher.main(), 0)
        start.assert_not_called()
        self.assertEqual(ports.call_args_list[0].args[1], set())

    def test_skip_ignores_invalid_speech_configuration(self):
        start, _, _, _, _ = self.main_environment(skip=True)
        launcher.parse_args.return_value.kokoro_device = None
        os.environ["KOKORO_DEVICE"] = "invalid"
        os.environ["KOKORO_BASE_URL"] = "invalid"
        self.assertEqual(launcher.main(), 0)
        start.assert_not_called()

    def test_termination_signal_runs_cleanup_and_restores_handler(self):
        _, stop, _, backend, frontend = self.main_environment()
        previous = signal.getsignal(signal.SIGTERM)
        launcher.time.sleep.side_effect = lambda _: signal.raise_signal(signal.SIGTERM)
        self.assertEqual(launcher.main(), 0)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual([call.args[0] for call in stop.call_args_list if call.args[0] is not None], [frontend, backend])

    def test_kokoro_exit_stops_app_instead_of_silent_loss_of_narration(self):
        kokoro = MagicMock()
        kokoro.poll.return_value = 2
        _, stop, _, _, _ = self.main_environment(kokoro=kokoro)
        self.assertEqual(launcher.main(), 2)
        self.assertIn(kokoro, [call.args[0] for call in stop.call_args_list])

    def test_dotenv_keeps_terminal_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"KOKORO_DEVICE": "cpu"}, clear=True):
            path = Path(directory) / ".env"
            path.write_text('KOKORO_DEVICE=cuda\nKOKORO_BASE_URL="http://127.0.0.1:8890"\n', encoding="utf-8")
            launcher_config.load_env_file(path)
            self.assertEqual(launcher_config.kokoro_device(), "cpu")
            self.assertEqual(os.environ["KOKORO_BASE_URL"], "http://127.0.0.1:8890")


class LANLauncherTests(unittest.TestCase):
    def test_serving_command_accepts_lan_and_forwarded_options(self):
        with patch.object(sys, "argv", ["run.py", "serve", "--lan", "--frontend-port", "5190", "--kokoro-device", "cpu"]):
            args = launcher.parse_args()
        self.assertEqual(args.command, "serve")
        self.assertTrue(args.lan)
        self.assertEqual(args.frontend_port, 5190)
        self.assertEqual(args.kokoro_device, "cpu")
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

    def test_port_probe_checks_all_interfaces_for_lan(self):
        with patch.object(launcher.socket, "socket") as make_socket:
            self.assertEqual(launcher.available_port(5173, host="0.0.0.0"), 5173)
        make_socket.return_value.__enter__.return_value.bind.assert_called_once_with(("0.0.0.0", 5173))


class LANOrchestrationTests(unittest.TestCase):
    main_environment = RootRunTests.main_environment

    def test_lan_exposes_frontend_and_routes_api_to_local_backend(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
        launcher.parse_args.return_value.lan = True
        with patch.object(launcher, "lan_addresses", return_value=["192.168.1.20"]), patch("builtins.print") as output:
            self.assertEqual(launcher.main(), 0)
        calls = launcher.subprocess.Popen.call_args_list
        self.assertIn("127.0.0.1", calls[0].args[0])
        self.assertEqual(calls[1].args[0][-2:], ["--host", "0.0.0.0"])
        self.assertEqual(calls[1].kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:3001")
        self.assertEqual(ports.call_args_list[1].kwargs["host"], "0.0.0.0")
        self.assertTrue(any("http://192.168.1.20:5173" in str(call) for call in output.call_args_list))


if __name__ == "__main__":
    unittest.main()
