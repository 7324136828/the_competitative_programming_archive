"""State and workspace management for study sets.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .content_store import ContentStore

logger = logging.getLogger("uvicorn.error")

# Global state
_store: ContentStore | None = None
_active_workspace_id: str | None = None
_upload_progress: dict[str, dict[str, Any]] = {}
_qa_sessions: dict[str, dict[str, Any]] = {}


def _manifest_workspace_root(path_value: Any) -> str:
    """Normalize a manifest path to the directory that owns its output folder."""
    raw = str(path_value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid workspace path: {path_value!r}")
    parts = [part for part in path.parts if part not in ("", ".")]
    if parts and parts[-1].casefold() == "output":
        parts.pop()
    return PurePosixPath(*parts).as_posix() if parts else "."


def get_content_store() -> ContentStore:
    global _store
    if _store is None:
        from ..jira.db import db
        db_path = Path(db.path) if db.path and db.path != ":memory:" else Path(tempfile.gettempdir()) / "study_sets.sqlite"
        voice_dir = db_path.parent / "voices"
        _store = ContentStore(db_path, voice_dir)
    return _store


def set_active_workspace_id(workspace_id: str | None) -> None:
    global _active_workspace_id
    _active_workspace_id = workspace_id


def get_active_workspace_id() -> str | None:
    global _active_workspace_id
    store = get_content_store()
    all_ws = store.list_all_workspaces()
    if not all_ws:
        _active_workspace_id = None
        return None
    if _active_workspace_id and any(w["id"] == _active_workspace_id for w in all_ws):
        return _active_workspace_id
    _active_workspace_id = all_ws[0]["id"]
    return _active_workspace_id


def set_upload_progress(upload_id: str, state: str, percent: int, message: str, current_workspace: str | None = None) -> None:
    _upload_progress[upload_id] = {
        "id": upload_id,
        "state": state,
        "percent": percent,
        "message": message,
        "currentWorkspace": current_workspace,
    }


def get_upload_progress(upload_id: str) -> dict[str, Any]:
    return _upload_progress.get(
        upload_id,
        {
            "id": upload_id,
            "state": "completed",
            "percent": 100,
            "message": "Ready",
            "currentWorkspace": None,
        }
    )


def extract_and_import_zip(zip_bytes: bytes, original_filename: str, upload_id: str | None = None) -> str:
    upload_id = upload_id or uuid.uuid4().hex
    set_upload_progress(upload_id, "uploading", 20, "Extracting study set archive")

    temp_extract_dir = Path(tempfile.mkdtemp(prefix="study-extract-"))
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            zf.extractall(temp_extract_dir)

        set_upload_progress(upload_id, "processing", 50, "Parsing manifest and workspaces")

        # Check for workspace.json manifest
        manifest_file = temp_extract_dir / "workspace.json"
        display_name = Path(original_filename).stem.replace("_", " ").title()
        manifest_names: dict[str, str] = {}

        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as e:
                raise ValueError(f"Could not parse workspace.json: {e}") from e

            if not isinstance(manifest_data, dict):
                raise ValueError("workspace.json must contain a JSON object")
            display_name = manifest_data.get("title") or display_name
            ws_entries = manifest_data.get("workspace", [])
            if ws_entries and not isinstance(ws_entries, list):
                raise ValueError("workspace.json field 'workspace' must be an array")
            for index, entry in enumerate(ws_entries):
                if not isinstance(entry, dict):
                    raise ValueError(f"workspace.json entry {index + 1} must be an object")
                relative = _manifest_workspace_root(entry.get("path"))
                workspace_root = temp_extract_dir if relative == "." else temp_extract_dir / relative
                if not (workspace_root / "output").is_dir():
                    raise ValueError(
                        f"Workspace path '{entry.get('path')}' does not contain an output folder"
                    )
                if relative in manifest_names:
                    raise ValueError(f"Duplicate workspace path in workspace.json: {entry.get('path')}")
                default_name = display_name if relative == "." else workspace_root.name
                manifest_names[relative] = str(entry.get("name") or default_name)

        # Ensure at least one output folder exists if flat
        if not manifest_names and not (temp_extract_dir / "output").is_dir():
            has_output = any(
                path.is_dir() and path.name.casefold() == "output"
                for path in temp_extract_dir.rglob("*")
            )
            if not has_output:
                # Wrap existing subdirectories into an output directory
                out_dir = temp_extract_dir / "output"
                out_dir.mkdir(parents=True, exist_ok=True)
                for item in list(temp_extract_dir.iterdir()):
                    if item != out_dir and item.name != "workspace.json":
                        shutil.move(str(item), str(out_dir / item.name))

        store = get_content_store()
        imported_id = store.import_workspace_tree(
            temp_extract_dir,
            original_filename,
            upload_id=upload_id,
            name=display_name,
            names_map=manifest_names,
            progress=lambda cur, tot, name: set_upload_progress(
                upload_id, "processing", 50 + int((cur / max(tot, 1)) * 40), f"Importing {name}", name
            )
        )
        set_upload_progress(upload_id, "completed", 100, "Import complete")
        return imported_id
    finally:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)


# QA Sessions
def create_qa_session(qa_file: str, title: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "id": session_id,
        "qaFile": qa_file,
        "title": title,
        "questions": questions,
        "answers": ["" for _ in questions],
        "currentQuestion": 0,
        "status": "in_progress",
        "createdAt": now,
        "updatedAt": now,
    }
    _qa_sessions[session_id] = session
    return session


def get_qa_session(session_id: str) -> dict[str, Any] | None:
    return _qa_sessions.get(session_id)


def update_qa_session(session_id: str, answers: list[str], current_question: int, completed: bool) -> dict[str, Any]:
    session = _qa_sessions.get(session_id)
    if not session:
        raise KeyError("QA session not found")
    session["answers"] = answers
    session["currentQuestion"] = current_question
    session["status"] = "completed" if completed else "in_progress"
    session["updatedAt"] = datetime.now(timezone.utc).isoformat()
    return session


def list_qa_sessions() -> list[dict[str, Any]]:
    return list(_qa_sessions.values())
