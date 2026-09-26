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
from pathlib import Path, PurePosixPath
from typing import Any

from .content_store import ContentStore

logger = logging.getLogger("uvicorn.error")

# Global state
_store: ContentStore | None = None
_active_workspace_id: str | None = None
_upload_progress: dict[str, dict[str, Any]] = {}


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


def set_upload_progress(
    upload_id: str,
    state: str,
    percent: int,
    message: str,
    current_workspace: str | None = None,
    completed_workspaces: int = 0,
    total_workspaces: int = 0,
) -> None:
    _upload_progress[upload_id] = {
        "id": upload_id,
        "state": state,
        "percent": percent,
        "message": message,
        "currentWorkspace": current_workspace,
        "completedWorkspaces": completed_workspaces,
        "totalWorkspaces": total_workspaces,
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
            "completedWorkspaces": 0,
            "totalWorkspaces": 0,
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

        # workspace.json is the sole source of study-set definitions. A ZIP
        # may wrap the collection in one or more parent directories; the
        # manifest's own directory becomes the root for all relative paths.
        manifest_files = sorted(
            temp_extract_dir.rglob("workspace.json"),
            key=lambda path: (len(path.relative_to(temp_extract_dir).parts), path.as_posix().casefold()),
        )
        if not manifest_files:
            raise ValueError("The archive must contain a workspace.json file")
        if len(manifest_files) > 1:
            locations = ", ".join(path.relative_to(temp_extract_dir).as_posix() for path in manifest_files[:5])
            raise ValueError(f"The archive contains multiple workspace.json files: {locations}")
        manifest_file = manifest_files[0]
        manifest_root = manifest_file.parent
        display_name = Path(original_filename).stem.replace("_", " ").title()
        manifest_names: dict[str, str] = {}

        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            raise ValueError(f"Could not parse workspace.json: {e}") from e

        if not isinstance(manifest_data, dict):
            raise ValueError("workspace.json must contain a JSON object")
        display_name = manifest_data.get("title") or display_name
        ws_entries = manifest_data.get("workspace")
        if not isinstance(ws_entries, list) or not ws_entries:
            raise ValueError("workspace.json field 'workspace' must be a non-empty array")
        for index, entry in enumerate(ws_entries):
            if not isinstance(entry, dict):
                raise ValueError(f"workspace.json entry {index + 1} must be an object")
            workspace_name = entry.get("name")
            if not isinstance(workspace_name, str) or not workspace_name.strip():
                raise ValueError(f"workspace.json entry {index + 1} must have a non-empty name")
            relative = _manifest_workspace_root(entry.get("path"))
            workspace_root = manifest_root if relative == "." else manifest_root / relative
            if not (workspace_root / "output").is_dir():
                raise ValueError(
                    f"Workspace path '{entry.get('path')}' does not contain an output folder"
                )
            if relative in manifest_names:
                raise ValueError(f"Duplicate workspace path in workspace.json: {entry.get('path')}")
            manifest_names[relative] = workspace_name.strip()

        total_workspaces = len(manifest_names)
        set_upload_progress(
            upload_id,
            "processing",
            50,
            f"Found {total_workspaces} workspace{'s' if total_workspaces != 1 else ''}",
            completed_workspaces=0,
            total_workspaces=total_workspaces,
        )

        def report_progress(current: int, total: int, workspace_name: str) -> None:
            if current >= total:
                set_upload_progress(
                    upload_id,
                    "processing",
                    95,
                    "Finalizing import",
                    workspace_name,
                    completed_workspaces=total,
                    total_workspaces=total,
                )
                return
            set_upload_progress(
                upload_id,
                "processing",
                50 + int((current / max(total, 1)) * 45),
                f"Importing workspace {current + 1} of {total}",
                workspace_name,
                completed_workspaces=current,
                total_workspaces=total,
            )

        store = get_content_store()
        imported_id = store.import_workspace_tree(
            manifest_root,
            original_filename,
            upload_id=upload_id,
            name=display_name,
            names_map=manifest_names,
            progress=report_progress,
        )
        set_upload_progress(
            upload_id,
            "completed",
            100,
            "Import complete",
            completed_workspaces=total_workspaces,
            total_workspaces=total_workspaces,
        )
        return imported_id
    finally:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)


# Persistent QA sessions
def create_qa_session(qa_file: str, title: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    workspace_id = get_active_workspace_id()
    if not workspace_id:
        raise ValueError("No active study set")
    return get_content_store().create_qa_session(workspace_id, qa_file, title, questions)


def get_qa_session(session_id: str) -> dict[str, Any] | None:
    workspace_id = get_active_workspace_id()
    if not workspace_id:
        return None
    return get_content_store().get_qa_session(session_id, workspace_id)


def update_qa_session(session_id: str, answers: list[str], current_question: int, completed: bool) -> dict[str, Any]:
    workspace_id = get_active_workspace_id()
    if not workspace_id:
        raise KeyError("QA session not found")
    return get_content_store().update_qa_session(
        session_id, workspace_id, answers, current_question, completed
    )


def list_qa_sessions(qa_file: str | None = None) -> list[dict[str, Any]]:
    workspace_id = get_active_workspace_id()
    if not workspace_id:
        return []
    return get_content_store().list_qa_sessions(workspace_id, qa_file)
