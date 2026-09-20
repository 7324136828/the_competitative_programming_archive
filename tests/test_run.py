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

    def test_custom_port_is_used_for_binding_startup_and_health_checks(self):
        child, spawn, stop = self.child_environment([None, HEALTH])
        self.assertIs(launcher.start_kokoro("http://localhost:8899/v1", "cuda"), child)
        arguments = spawn.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--port") + 1], "8899")
        launcher.socket.socket.return_value.__enter__.return_value.bind.assert_called_once_with(("127.0.0.1", 8899))
        self.assertEqual(
            [call.args[0] for call in launcher.read_kokoro_health.call_args_list],
            ["http://localhost:8899/health", "http://localhost:8899/health"],
        )
        stop.assert_not_called()

    def test_custom_port_reuses_compatible_service(self):
        with patch.object(launcher, "read_kokoro_health", return_value=HEALTH) as health, patch.object(launcher.subprocess, "Popen") as spawn:
            self.assertIsNone(launcher.start_kokoro("http://localhost:8899/v1", "cuda"))
        health.assert_called_once_with("http://localhost:8899/health")
        spawn.assert_not_called()

    def test_occupied_custom_port_fails_without_starting_or_falling_back(self):
        _, spawn, _ = self.child_environment([None])
        bind = launcher.socket.socket.return_value.__enter__.return_value.bind
        bind.side_effect = OSError("address already in use")
        with self.assertRaisesRegex(launcher.RunError, "Kokoro port 8899 is occupied"):
            launcher.start_kokoro("http://127.0.0.1:8899", "cuda")
        bind.assert_called_once_with(("127.0.0.1", 8899))
        spawn.assert_not_called()

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
        self.enterContext(patch.object(launcher, "parse_args", return_value=SimpleNamespace(kokoro_device="cpu", kokoro_backend_port=None, skip_kokoro=skip, backend_port=None, frontend_port=None, host="127.0.0.1", lan=False, command="serve")))
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


class PortLauncherTests(unittest.TestCase):
    main_environment = RootRunTests.main_environment

    def test_both_port_flags_are_forwarded_with_or_without_serve(self):
        for command in ([], ["serve"]):
            with self.subTest(command=command), patch.object(
                sys, "argv", ["run.py", *command, "--frontend-port", "5200", "--backend-port", "3100"]
            ):
                args = launcher.parse_args()
                self.assertEqual(args.frontend_port, 5200)
                self.assertEqual(args.backend_port, 3100)

    def test_cli_ports_override_environment_and_reach_both_services(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
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
        self.assertEqual(frontend.kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:3100")

    def test_default_ports_when_no_overrides_are_configured(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [3001, 5173])

    def test_dotenv_ports_are_defaults_and_terminal_port_takes_precedence(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
        os.environ["PORT"] = "3400"
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("PORT=3500\nBACKEND_PORT=3600\nFRONTEND_PORT=5400\n", encoding="utf-8")
            launcher.load_env_file.side_effect = lambda: launcher_config.load_env_file(env_file)
            self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [3400, 5400])

    def test_backend_port_environment_used_without_port_alias(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
        os.environ.update(BACKEND_PORT="3500", FRONTEND_PORT="5500")
        self.assertEqual(launcher.main(), 0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [3500, 5500])

    def test_invalid_explicit_ports_fail_before_runtime_setup(self):
        with patch.object(sys, "argv", ["run.py", "--frontend-port", "0", "--backend-port", "0"]):
            parsed = launcher.parse_args()
            self.assertEqual((parsed.frontend_port, parsed.backend_port), (0, 0))
        self.main_environment(skip=True)
        # Zero is a valid integer to argparse, but must not silently select an
        # environment/default port or bootstrap an environment before failing.
        for flag in ("backend_port", "frontend_port"):
            for value in (0, -1, 65536):
                with self.subTest(flag=flag, value=value):
                    args = launcher.parse_args.return_value
                    args.backend_port = args.frontend_port = None
                    setattr(args, flag, value)
                    with self.assertRaisesRegex(launcher.RunError, "between 1 and 65535"):
                        launcher.main()
        launcher.select_runtime.assert_not_called()
        launcher.subprocess.Popen.assert_not_called()

    def test_fallback_ports_are_reserved_and_proxy_tracks_selected_backend(self):
        _, _, ports, _, _ = self.main_environment(skip=True)
        args = launcher.parse_args.return_value
        args.backend_port = args.frontend_port = 5200
        args.host = "0.0.0.0"
        args.lan = True
        ports.side_effect = [5201, 5202]
        with patch.object(launcher, "lan_addresses", return_value=["192.168.1.20"]), patch("builtins.print") as output:
            self.assertEqual(launcher.main(), 0)

        self.assertEqual(ports.call_args_list[0].args, (5200, set()))
        self.assertEqual(ports.call_args_list[0].kwargs["host"], "0.0.0.0")
        self.assertEqual(ports.call_args_list[1].args, (5200, {5201}))
        self.assertEqual(ports.call_args_list[1].kwargs["host"], "0.0.0.0")
        backend, frontend = launcher.subprocess.Popen.call_args_list
        self.assertEqual(backend.args[0][-4:], ["--host", "0.0.0.0", "--port", "5201"])
        self.assertEqual(backend.kwargs["env"]["PORT"], "5201")
        self.assertEqual(frontend.args[0][-5:], ["--port", "5202", "--strictPort", "--host", "0.0.0.0"])
        self.assertEqual(frontend.kwargs["env"]["VITE_BACKEND_URL"], "http://127.0.0.1:5201")
        self.assertTrue(any("http://192.168.1.20:5202" in str(call) for call in output.call_args_list))

    def test_port_search_skips_busy_and_reserved_ports(self):
        with patch.object(launcher.socket, "socket") as make_socket:
            bind = make_socket.return_value.__enter__.return_value.bind
            bind.side_effect = [OSError("busy"), None]
            self.assertEqual(launcher.available_port(5200, {5201}, host="0.0.0.0"), 5202)
        self.assertEqual([call.args[0] for call in bind.call_args_list], [("0.0.0.0", 5200), ("0.0.0.0", 5202)])

    def test_ipv6_backend_port_probe_uses_ipv6_socket(self):
        with patch.object(launcher.socket, "socket") as make_socket:
            self.assertEqual(launcher.available_port(3100, host="::"), 3100)
        make_socket.assert_called_once_with(launcher.socket.AF_INET6, launcher.socket.SOCK_STREAM)
        make_socket.return_value.__enter__.return_value.bind.assert_called_once_with(("::", 3100))


class KokoroPortLauncherTests(unittest.TestCase):
    main_environment = RootRunTests.main_environment

    def test_all_three_port_flags_are_accepted_with_or_without_serve(self):
        for command in ([], ["serve", "--lan"]):
            with self.subTest(command=command), patch.object(
                sys, "argv", ["run.py", *command, "--frontend-port", "5200", "--backend-port", "3100", "--kokoro-backend-port", "8899"]
            ):
                args = launcher.parse_args()
                self.assertEqual((args.frontend_port, args.backend_port, args.kokoro_backend_port), (5200, 3100, 8899))
        with patch.object(sys, "argv", ["run.py"]):
            self.assertIsNone(launcher.parse_args().kokoro_backend_port)

    def test_invalid_explicit_port_fails_before_setup_even_when_kokoro_is_skipped(self):
        self.main_environment()
        args = launcher.parse_args.return_value
        for skip in (False, True):
            args.skip_kokoro = skip
            for value in (0, -1, 65536):
                with self.subTest(skip=skip, value=value):
                    args.kokoro_backend_port = value
                    with self.assertRaisesRegex(launcher.RunError, "between 1 and 65535"):
                        launcher.main()
        launcher.select_runtime.assert_not_called()
        launcher.subprocess.Popen.assert_not_called()

    def test_override_updates_service_and_backend_and_reserves_local_port(self):
        start, _, ports, _, _ = self.main_environment()
        args = launcher.parse_args.return_value
        args.kokoro_backend_port = 8899
        args.backend_port = args.frontend_port = 8899
        os.environ["KOKORO_BASE_URL"] = "http://localhost:8881/v1/"
        ports.side_effect = [8900, 8901]

        self.assertEqual(launcher.main(), 0)

        expected = "http://localhost:8899/v1/"
        start.assert_called_once_with(expected, "cpu")
        self.assertEqual(os.environ["KOKORO_BASE_URL"], expected)
        backend = launcher.subprocess.Popen.call_args_list[0]
        self.assertEqual(backend.kwargs["env"]["KOKORO_BASE_URL"], expected)
        self.assertEqual(ports.call_args_list[0].args, (8899, {8899}))
        self.assertEqual(ports.call_args_list[1].args, (8899, {8899, 8900}))

    def test_override_uses_default_url_when_no_base_is_configured(self):
        start, _, _, _, _ = self.main_environment()
        launcher.parse_args.return_value.kokoro_backend_port = 8899
        del os.environ["KOKORO_BASE_URL"]
        self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("http://127.0.0.1:8899", "cpu")
        self.assertEqual(launcher.subprocess.Popen.call_args_list[0].kwargs["env"]["KOKORO_BASE_URL"], "http://127.0.0.1:8899")

    def test_without_override_configured_service_port_is_preserved(self):
        start, _, ports, _, _ = self.main_environment()
        os.environ["KOKORO_BASE_URL"] = "http://localhost:8891/v1"
        self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("http://localhost:8891/v1", "cpu")
        self.assertEqual(ports.call_args_list[0].args[1], {8891})
        self.assertEqual(launcher.subprocess.Popen.call_args_list[0].kwargs["env"]["KOKORO_BASE_URL"], "http://localhost:8891/v1")

    def test_external_scheme_host_and_path_are_preserved_without_local_reservation(self):
        start, _, ports, _, _ = self.main_environment()
        launcher.parse_args.return_value.kokoro_backend_port = 9443
        os.environ["KOKORO_BASE_URL"] = "https://speech.example.com/services/kokoro/v1"
        self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("https://speech.example.com:9443/services/kokoro/v1", "cpu")
        self.assertEqual(ports.call_args_list[0].args[1], set())
        self.assertEqual(launcher.subprocess.Popen.call_args_list[0].kwargs["env"]["KOKORO_BASE_URL"], "https://speech.example.com:9443/services/kokoro/v1")

    def test_ipv6_brackets_and_local_reservation_survive_override(self):
        start, _, ports, _, _ = self.main_environment()
        launcher.parse_args.return_value.kokoro_backend_port = 8899
        os.environ["KOKORO_BASE_URL"] = "http://[::1]:8881/v1"
        self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("http://[::1]:8899/v1", "cpu")
        self.assertEqual(ports.call_args_list[0].args[1], {8899})
        self.assertEqual(launcher.subprocess.Popen.call_args_list[0].kwargs["env"]["KOKORO_BASE_URL"], "http://[::1]:8899/v1")

    def test_explicit_port_with_skip_configures_backend_without_starting_service(self):
        start, _, ports, _, _ = self.main_environment(skip=True)
        launcher.parse_args.return_value.kokoro_backend_port = 8899
        self.assertEqual(launcher.main(), 0)
        start.assert_not_called()
        self.assertEqual(ports.call_args_list[0].args[1], {8899})
        self.assertEqual(launcher.subprocess.Popen.call_args_list[0].kwargs["env"]["KOKORO_BASE_URL"], "http://127.0.0.1:8899")

    def test_cli_override_applies_after_dotenv_loading(self):
        start, _, _, _, _ = self.main_environment()
        launcher.parse_args.return_value.kokoro_backend_port = 8899
        del os.environ["KOKORO_BASE_URL"]
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("KOKORO_BASE_URL=http://localhost:8891/v1\n", encoding="utf-8")
            launcher.load_env_file.side_effect = lambda: launcher_config.load_env_file(env_file)
            self.assertEqual(launcher.main(), 0)
        start.assert_called_once_with("http://localhost:8899/v1", "cpu")

    def test_effective_url_is_available_to_bootstrap_and_runtime_handoff(self):
        start, _, _, _, _ = self.main_environment()
        launcher.parse_args.return_value.kokoro_backend_port = 8899
        runtime = launcher.ROOT / "runtime-for-test" / "python.exe"
        expected = "http://127.0.0.1:8899"

        def select_runtime(**kwargs):
            self.assertEqual(os.environ["KOKORO_BASE_URL"], expected)
            return runtime

        def handoff(command):
            self.assertEqual(os.environ["KOKORO_BASE_URL"], expected)
            self.assertEqual(command, [str(runtime), str(Path(launcher.__file__).resolve()), "serve", "--kokoro-backend-port", "8899"])
            return 7

        launcher.select_runtime.side_effect = select_runtime
        with patch.object(sys, "argv", ["run.py", "serve", "--kokoro-backend-port", "8899"]), patch.object(launcher.subprocess, "call", side_effect=handoff) as call:
            self.assertEqual(launcher.main(), 7)
        call.assert_called_once()
        start.assert_not_called()
        launcher.subprocess.Popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
