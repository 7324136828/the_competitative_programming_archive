"""Verify both built Windows profiles with isolated settings and no Python/Node PATH.

Run after build.py: python tests/smoke_portable.py
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import ARTIFACTS, checked_path
from backend.network import discover_lan_ipv4


def request(url: str, *, payload: dict | None = None, headers: dict | None = None, method: str | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    supplied = {"Content-Type": "application/json", **(headers or {})}
    query = urllib.request.Request(url, data=body, headers=supplied,
                                   method=method or ("PUT" if payload is not None else "GET"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(query, timeout=5) as response:
        content = response.read()
        return json.loads(content) if "application/json" in response.headers.get("Content-Type", "") else content


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class SpeechFixture(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x10\x00" * 2400)
        data = output.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_arguments) -> None:
        pass


def verify_profile(profile: str, fixture: Path, *, connector_url: str, toolchains: bool = False) -> None:
    built = ROOT / "dist" / profile
    if not (built / "server.exe").is_file():
        raise RuntimeError("Run build.py first")
    assert (built / "port_mapping.json").read_bytes() == (ROOT / "port_mapping.json").read_bytes()
    # Relocate the actual artifacts and customize their defaults, proving the
    # frozen runtime reads the editable file beside itself rather than source.
    package = fixture / "portable application"
    package.mkdir()
    for name in ARTIFACTS:
        source, target = built / name, package / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    defaults = {"frontend_port": 4610, "backend_port": 8460}
    (package / "port_mapping.json").write_text(json.dumps(defaults), encoding="utf-8")
    environment = os.environ.copy()
    for key in ("DATABASE_PATH", "DB_PATH", "JIRA_DB_PATH", "WORKSPACE_STORAGE_DIR", "UPLOAD_DIR",
                "HOST", "BACKEND_HOST", "PORT", "JIRA_ENV", "NODE_ENV", "AUTO_SEED",
                "MIGRATE_LEGACY_DATABASES", "SEED_DEMO", "CONNECTOR_REGISTER_TOOLS"):
        environment.pop(key, None)
    (fixture / "temporary").mkdir(parents=True)
    environment.update(APPDATA=str(fixture / "roaming"), TEMP=str(fixture / "temporary"),
                       TMP=str(fixture / "temporary"), CONNECTOR_REGISTER_TOOLS="false",
                       CONNECTOR_BASE_URL=connector_url)
    if not toolchains:
        environment["PATH"] = ""
    # Reserve the first requested backend port to exercise actual busy-port fallback.
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1" if profile == "Debug" else "0.0.0.0", 0))
        occupied.listen()
        requested_backend = occupied.getsockname()[1]
        backend_port = requested_backend + 1
        frontend_port = free_port()
        while frontend_port in (requested_backend, backend_port):
            frontend_port = free_port()
        frontend_url = f"http://127.0.0.1:{frontend_port}"
        log = fixture / "server.log"
        with log.open("wb") as output:
            process = subprocess.Popen(
                [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"),
                 "/d", "/c", str(package / "run.bat"),
                 "--frontend", str(frontend_port), "--backend", str(requested_backend)],
                cwd=fixture, env=environment, stdout=output, stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            try:
                deadline = time.monotonic() + 60
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text(errors="replace"))
                    try:
                        health = request(frontend_url + "/api/health")
                        if health["status"] == "ok":
                            break
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        if time.monotonic() > deadline:
                            raise RuntimeError("Startup timed out: " + log.read_text(errors="replace"))
                        time.sleep(0.2)

                assert b"<html" in request(frontend_url + "/").lower()
                assert b"<html" in request(frontend_url + "/client/deep/route").lower()
                actual_backend = re.search(r"^Backend:\s+(http://\S+)", log.read_text(errors="replace"), re.MULTILINE)
                assert actual_backend is not None
                backend_port = int(actual_backend[1].rsplit(":", 1)[1])
                assert backend_port > requested_backend, (requested_backend, backend_port, log.read_text(errors="replace"))
                assert backend_port != frontend_port
                assert b"swagger" in request(f"http://127.0.0.1:{backend_port}/docs").lower()
                settings = request(frontend_url + "/api/settings")
                assert settings["editable"] is True
                active = Path(settings["active_data_dir"])
                assert active == fixture / "temporary" / "the_study_platform"
                assert (active / "jira.db").is_file()
                uploads = active / "uploads"
                uploads.mkdir(exist_ok=True)
                (uploads / "smoke.txt").write_text("attachment smoke", encoding="utf-8")
                assert request(frontend_url + "/uploads/smoke.txt") == b"attachment smoke"
                selected = fixture / "selected data"
                saved = request(frontend_url + "/api/settings", payload={"data_dir": str(selected)})
                assert saved["restart_required"] is True
                assert saved["active_data_dir"] == str(active)
                persisted = json.loads(Path(settings["settings_path"]).read_text(encoding="utf-8"))
                assert persisted["data_dir"] == str(selected)
                assert persisted["frontend_port"] == defaults["frontend_port"]
                assert persisted["backend_port"] == defaults["backend_port"]
                reset = request(frontend_url + "/api/settings", payload={"data_dir": ""})
                assert reset["restart_required"] is False
                audio = request(frontend_url + "/api/audio/responses", method="POST",
                                payload={"text": "Portable native encoder smoke check"})["audio"]
                audio_deadline = time.monotonic() + 20
                while not audio["done"]:
                    assert time.monotonic() < audio_deadline, audio
                    time.sleep(0.1)
                    audio = request(frontend_url + "/api/audio/responses/" + audio["key"])["audio"]
                assert audio["status"] == "ready", audio
                mp3 = request(frontend_url + audio["url"])
                assert len(mp3) > 4 and (mp3[:3] == b"ID3" or mp3[0] == 255)
                # Probe the actual adapter rather than faking client-IP headers.
                adapters = discover_lan_ipv4()
                if adapters and profile == "Release":
                    lan_url = f"http://{adapters[0]}:{frontend_port}"
                    remote = request(lan_url + "/api/settings", headers={
                        "X-Study-Client-IP": "127.0.0.1", "X-Forwarded-For": "127.0.0.1",
                        "X-Study-Proxy-Token": "spoofed",
                    })
                    assert remote["editable"] is False
                    try:
                        request(lan_url + "/api/settings", payload={"data_dir": str(selected)})
                        raise AssertionError("LAN client unexpectedly changed host storage")
                    except urllib.error.HTTPError as error:
                        assert error.code == 403
                languages = request(frontend_url + "/api/languages")
                assert languages["success"] is True
                examples = {
                    "python": "print(7)",
                    "cpp": '#include <iostream>\nint main() { std::cout << 7 << std::endl; }',
                    "java": 'class Main { public static void main(String[] args) { System.out.println(7); } }',
                }
                if toolchains:
                    for language in languages["languages"]:
                        identifier = language["id"]
                        result = request(frontend_url + "/api/run", method="POST", payload={
                            "language": identifier, "code": examples[identifier], "input": "",
                        })
                        assert result["result"]["stdout"].strip() == "7", result
                        print(f"{profile}: external {identifier} execution passed", flush=True)
                print(f"{profile}: artifact mapping, frontend, backend, port fallback, uploads, settings, LAN and native MP3 passed", flush=True)
            finally:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
                process.wait(timeout=10)
                # Windows can release the child's SQLite handles just after the
                # bootloader exits; give filesystem cleanup a brief grace period.
                time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-toolchains", action="store_true", help="also run installed submission languages")
    arguments = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("Portable Windows smoke verification requires Windows")
    temporary_root = checked_path(ROOT / "build", ROOT)
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="portable-smoke-", dir=temporary_root) as temporary:
        fixture_root = checked_path(Path(temporary), temporary_root)
        with ThreadingHTTPServer(("127.0.0.1", 0), SpeechFixture) as connector:
            worker = threading.Thread(target=connector.serve_forever, daemon=True)
            worker.start()
            try:
                connector_url = f"http://127.0.0.1:{connector.server_port}/v1"
                for profile in ("Debug", "Release"):
                    fixture = fixture_root / profile
                    fixture.mkdir()
                    verify_profile(profile, fixture, connector_url=connector_url,
                                   toolchains=arguments.with_toolchains)
            finally:
                connector.shutdown()
                worker.join(timeout=5)


if __name__ == "__main__":
    main()
