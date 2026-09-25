"""Shared application paths for the web server and seed command."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def project_temp_path() -> Path:
    """Return this checkout's stable directory beneath the system temp folder."""
    project = os.path.normcase(str(ROOT.resolve()))
    project_id = hashlib.sha256(project.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "codejudge" / project_id


def default_database_path() -> Path:
    """Return the one SQLite file used by every application feature."""
    return project_temp_path() / "jira.db"


def legacy_archive_database_path() -> Path:
    """Return the pre-unification problem archive location for migration."""
    return project_temp_path() / "leetcode.db"


def default_storage_path(database_path: str | Path) -> Path:
    """Keep file references separate for each database, in durable workspace storage."""
    database = os.path.normcase(str(Path(database_path).resolve()))
    database_id = hashlib.sha256(database.encode("utf-8")).hexdigest()[:12]
    return ROOT / "data" / "workspace" / database_id
