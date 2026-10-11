"""Shared application paths for the web server and seed command."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from .settings import configured_data_dir

ROOT = Path(__file__).resolve().parent.parent


def project_temp_path() -> Path:
    """Return this checkout's stable directory beneath the system temp folder."""
    project = os.path.normcase(str(ROOT.resolve()))
    project_id = hashlib.sha256(project.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "codejudge" / project_id


def default_database_path(data_dir: str | Path | None = None) -> Path:
    """Return the one SQLite file used by every application feature."""
    return Path(data_dir or configured_data_dir()) / "jira.db"


def legacy_archive_database_path() -> Path:
    """Return the pre-unification problem archive location for migration."""
    return project_temp_path() / "leetcode.db"


def legacy_unified_database_path() -> Path:
    """Return the former checkout-specific unified database for opt-in migration."""
    return project_temp_path() / "jira.db"


def _database_id(database_path: str | Path) -> str:
    database = os.path.normcase(str(Path(database_path).resolve()))
    return hashlib.sha256(database.encode("utf-8")).hexdigest()[:12]


def legacy_storage_path(database_path: str | Path) -> Path:
    """Preserve the pre-settings repository storage location for migration."""
    return ROOT / "data" / "workspace" / _database_id(database_path)


def default_storage_path(database_path: str | Path, data_dir: str | Path | None = None) -> Path:
    """Use a root-relative database identity so an entire data folder can move."""
    root = Path(data_dir or configured_data_dir()).resolve()
    database = Path(database_path).resolve()
    try:
        identity = os.path.normcase(database.relative_to(root).as_posix())
    except ValueError:
        identity = os.path.normcase(str(database))
    database_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return root / "workspace" / database_id
