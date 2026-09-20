"""Shared application paths for the web server and seed command."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def default_database_path() -> Path:
    """Keep data stable across restarts and separate between project copies."""
    project = os.path.normcase(str(ROOT.resolve()))
    project_id = hashlib.sha256(project.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "codejudge" / project_id / "leetcode.db"


def default_storage_path(database_path: str | Path) -> Path:
    """Keep file references separate for each database, in durable workspace storage."""
    database = os.path.normcase(str(Path(database_path).resolve()))
    database_id = hashlib.sha256(database.encode("utf-8")).hexdigest()[:12]
    return ROOT / "data" / "workspace" / database_id
