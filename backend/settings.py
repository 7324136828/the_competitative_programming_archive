"""Per-user settings and a configurable root for application data."""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
from urllib.parse import urlsplit

APP_NAME = "the_study_platform"
_settings_lock = threading.RLock()


def default_data_dir() -> Path:
    """Use TEMP explicitly rather than Python's cached temporary directory."""
    temporary = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
    return (Path(temporary) / APP_NAME).resolve()


def settings_path() -> Path:
    roaming = os.environ.get("APPDATA")
    if roaming:
        root = Path(roaming)
    elif os.name == "nt":
        root = Path.home() / "AppData" / "Roaming"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return (root / APP_NAME / "settings.json").resolve()


def port_mapping_path() -> Path:
    """Use the editable default-port file beside the executable or source launcher."""
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "port_mapping.json"


def load_port_mapping(path: str | Path | None = None) -> dict:
    location = Path(path) if path is not None else port_mapping_path()
    try:
        payload = json.loads(location.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise OSError(f"Unable to read port mapping in {location}: {error.strerror or error}") from error
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Invalid port mapping JSON in {location}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Port mapping in {location} must contain a JSON object.")
    for key in ("frontend_port", "backend_port"):
        if key not in payload:
            raise ValueError(f"Port mapping in {location} must define {key}.")
        _validate_port(payload[key], key, location)
    return payload


def _selected_path(value: object) -> Path:
    if not isinstance(value, str):
        raise ValueError("data_dir must be an absolute folder path or an empty string for the default.")
    value = value.strip()
    if not value:
        return default_data_dir()
    if "\x00" in value:
        raise ValueError("data_dir contains an invalid character.")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("data_dir must be an absolute folder path.")
    return path.resolve()


def _read_settings_payload(location: Path) -> dict:
    try:
        payload = json.loads(location.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Invalid settings JSON in {location}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Settings in {location} must contain a JSON object.")
    return payload


def _validate_port(value: object, key: str, location: Path) -> None:
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError(f"{key} in {location} must be a JSON integer between 1 and 65535.")


def _validate_port_settings(payload: dict, location: Path, defaults: dict) -> None:
    for key in ("frontend_port", "backend_port"):
        _validate_port(payload.setdefault(key, defaults[key]), key, location)


def read_settings(path: str | Path | None = None, *, defaults_path: str | Path | None = None) -> dict:
    defaults = load_port_mapping(defaults_path)
    location = Path(path) if path is not None else settings_path()
    payload = _read_settings_payload(location)
    _validate_port_settings(payload, location, defaults)
    if payload.get("schema_version", 1) != 1:
        raise ValueError(f"Unsupported settings schema in {location}.")
    payload.setdefault("schema_version", 1)
    payload.setdefault("data_dir", "")
    _selected_path(payload["data_dir"])
    return payload


def configured_data_dir(path: str | Path | None = None, *, defaults_path: str | Path | None = None) -> Path:
    return _selected_path(read_settings(path, defaults_path=defaults_path)["data_dir"])


def _ensure_writable(directory: Path) -> None:
    """Test real writes, including for folders created by this request."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"settings write check")
            probe.flush()
    except OSError as error:
        raise ValueError(f"Data folder is not writable: {directory} ({error})") from error


def _write_settings(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def initialize_settings(path: str | Path | None = None, *, defaults_path: str | Path | None = None) -> Path:
    """Create first-run settings, and return the validated startup data root."""
    location = Path(path) if path is not None else settings_path()
    with _settings_lock:
        existing = initialize_port_settings(location, defaults_path=defaults_path)
        payload = read_settings(location, defaults_path=defaults_path)
        directory = _selected_path(payload["data_dir"])
        _ensure_writable(directory)
        if payload != existing:
            _write_settings(location, payload)
        return directory


def initialize_port_settings(path: str | Path | None = None, *, defaults_path: str | Path | None = None) -> dict:
    """Prepare launcher ports without opening or creating the configured data folder."""
    defaults = load_port_mapping(defaults_path)
    location = Path(path) if path is not None else settings_path()
    with _settings_lock:
        location.parent.mkdir(parents=True, exist_ok=True)
        try:
            with location.open("x", encoding="utf-8") as stream:
                stream.write("{}")
        except FileExistsError:
            pass
        payload = _read_settings_payload(location)
        missing = "frontend_port" not in payload or "backend_port" not in payload
        _validate_port_settings(payload, location, defaults)
        if missing:
            _write_settings(location, payload)
        # Launch from the persisted configuration, including after a first-run write.
        payload = _read_settings_payload(location)
        _validate_port_settings(payload, location, defaults)
        return payload


def save_data_dir(value: object, path: str | Path | None = None, *, defaults_path: str | Path | None = None) -> Path:
    directory = _selected_path(value)
    location = Path(path) if path is not None else settings_path()
    with _settings_lock:
        payload = read_settings(location, defaults_path=defaults_path)
        _ensure_writable(directory)
        payload["data_dir"] = str(directory) if str(value).strip() else ""
        _write_settings(location, payload)
    return directory


def _is_loopback(value: str | None) -> bool:
    try:
        address = ipaddress.ip_address(value or "")
        return address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback)
    except ValueError:
        return False


def settings_editable(remote_address: str | None, headers) -> bool:
    """Only local clients can select host paths; trust our authenticated proxy."""
    if not _is_loopback(remote_address):
        return False
    forwarded = headers.get("X-Study-Client-IP")
    forwarded_token = headers.get("X-Study-Proxy-Token")
    if forwarded is not None or forwarded_token is not None:
        expected = os.environ.get("STUDY_PROXY_TOKEN", "")
        if not expected or not secrets.compare_digest(expected, forwarded_token or ""):
            return False
        if not _is_loopback(forwarded):
            return False
    elif headers.get("X-Forwarded-For") or headers.get("Forwarded"):
        # Unknown proxies must not turn every peer into a local settings client.
        return False

    origin = headers.get("Origin")
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        if parsed.scheme not in ("http", "https") or not hostname:
            return False
        local_names = {"localhost", socket.gethostname().casefold(), socket.getfqdn().casefold()}
        if hostname.casefold() in local_names or _is_loopback(hostname):
            return True
        for name in (socket.gethostname(), socket.getfqdn()):
            try:
                if hostname in socket.gethostbyname_ex(name)[2]:
                    return True
            except OSError:
                continue
    except ValueError:
        pass
    return False
