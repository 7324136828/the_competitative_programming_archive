"""SQLite persistence for workspace ZIP imports and study set content.

Imported learning documents live in SQLite instead of an extracted directory tree.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


KINDS: dict[str, tuple[str, ...]] = {
    "quizzes": (),
    "qandas": (),
    "mindmaps": (".md", ".mmd"),
    "flashcards": (".txt",),
    "reports": (".md", ".html"),
    "slides": (".md",),
    "datatables": (".csv",),
    "infographics": (".html", ".svg", ".md", ".wireframe.txt"),
    "podcasts": (".mp3", ".wav"),
}

VOICE_SUFFIXES = {".pt"}


class ContentStore:
    """Thread-safe SQLite repository for study set content and workspace archives."""

    def __init__(self, database: Path | str, voice_dir: Path | str) -> None:
        self.database = Path(database).resolve()
        self.voice_dir = Path(voice_dir).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
                    workspace_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    story_id TEXT,
                    UNIQUE(upload_id, workspace_key)
                );
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    filename TEXT NOT NULL,
                    body BLOB NOT NULL,
                    content_type TEXT NOT NULL,
                    UNIQUE(workspace_id, kind, subject, filename)
                );
                CREATE INDEX IF NOT EXISTS content_lookup
                    ON content(workspace_id, kind, filename);
                CREATE TABLE IF NOT EXISTS voice_assets (
                    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
                    relative_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    PRIMARY KEY(upload_id, relative_path)
                );
                """
            )

    @staticmethod
    def _workspace_rows(collection: Path, names_map: dict[str, str] | None = None) -> list[tuple[str, str, Path, str]]:
        collection = collection.resolve()
        if names_map:
            # workspace.json is authoritative. Preserve its order and select
            # the exact workspace roots it names, even when they are nested
            # several directories below the archive root.
            candidates = [
                collection if relative == "." else (collection / relative).resolve()
                for relative in names_map
            ]
        else:
            # Archives without a manifest still get one study set per output
            # directory rather than collapsing nested chapters together.
            candidates = sorted(
                {
                    output_dir.parent.resolve()
                    for output_dir in collection.rglob("*")
                    if output_dir.is_dir() and output_dir.name.casefold() == "output"
                },
                key=lambda item: item.relative_to(collection).as_posix().casefold(),
            )

        rows: list[tuple[str, str, Path, str]] = []
        for workspace in candidates:
            try:
                relative = "." if workspace == collection else workspace.relative_to(collection).as_posix()
            except ValueError as error:
                raise ValueError("A workspace path points outside the archive") from error
            if not (workspace / "output").is_dir():
                raise ValueError(f"Workspace '{relative}' does not contain an output folder")
            key = relative
            ws_name = (names_map or {}).get(relative) or (collection.name if relative == "." else workspace.name)
            rows.append((key, ws_name, workspace, relative))
        return rows

    @classmethod
    def _content_files(
        cls, output_dir: Path, requested_kinds: Iterable[str] | None = None
    ) -> Iterator[tuple[str, str, Path]]:
        allowed = set(requested_kinds) if requested_kinds is not None else set(KINDS)
        if not output_dir.is_dir():
            return
        for kind in sorted(allowed):
            flat = output_dir / kind
            if flat.is_dir():
                for path in sorted(flat.iterdir(), key=lambda p: p.name.casefold()):
                    if path.is_file():
                        yield (kind, "", path)
        for subject_dir in sorted(output_dir.iterdir(), key=lambda p: p.name.casefold()):
            if not subject_dir.is_dir() or subject_dir.name in KINDS:
                continue
            subject = subject_dir.name
            for kind in sorted(allowed):
                kind_dir = subject_dir / kind
                if not kind_dir.is_dir():
                    continue
                for path in sorted(kind_dir.iterdir(), key=lambda p: p.name.casefold()):
                    if path.is_file():
                        yield (kind, subject, path)

    def import_workspace_tree(
        self,
        collection_path: Path,
        original_filename: str,
        upload_id: str | None = None,
        name: str | None = None,
        names_map: dict[str, str] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> str:
        workspace_rows = self._workspace_rows(collection_path, names_map=names_map)
        if not workspace_rows:
            raise ValueError("The archive does not contain an 'output' folder")

        upload_id = upload_id or uuid.uuid4().hex
        display_name = name or collection_path.name
        from datetime import datetime, timezone
        uploaded_at = datetime.now(timezone.utc).isoformat()

        pending_voice_dir = Path(tempfile.mkdtemp(prefix="voices-pending-"))
        final_voice_dir = self.voice_dir / upload_id

        try:
            voice_rows: list[tuple[str, str]] = []
            for voice_path in collection_path.rglob("*"):
                if voice_path.is_file() and voice_path.suffix.casefold() in VOICE_SUFFIXES:
                    relative = voice_path.relative_to(collection_path).as_posix()
                    dest = pending_voice_dir / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(voice_path, dest)
                    voice_rows.append((relative, str(dest)))

            total_workspaces = len(workspace_rows)
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO uploads(id, name, original_filename, uploaded_at) VALUES (?, ?, ?, ?)",
                    (upload_id, display_name, original_filename, uploaded_at),
                )
                for index, (key, ws_name, ws_path, relative) in enumerate(workspace_rows):
                    if progress is not None:
                        progress(index, total_workspaces, ws_name)
                    ws_id = uuid.uuid4().hex
                    connection.execute(
                        "INSERT INTO workspaces(id, upload_id, workspace_key, name, relative_path) VALUES (?, ?, ?, ?, ?)",
                        (ws_id, upload_id, key, ws_name, relative),
                    )
                    for kind, subject, path in self._content_files(ws_path / "output"):
                        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                        connection.execute(
                            "INSERT INTO content(workspace_id, kind, subject, filename, body, content_type) VALUES (?, ?, ?, ?, ?, ?)",
                            (ws_id, kind, subject, path.name, path.read_bytes(), content_type),
                        )
                if progress is not None:
                    progress(total_workspaces, total_workspaces, workspace_rows[-1][1])
                connection.executemany(
                    "INSERT INTO voice_assets(upload_id, relative_path, file_path) VALUES (?, ?, ?)",
                    ((upload_id, rel, fp) for rel, fp in voice_rows),
                )

            if final_voice_dir.exists():
                shutil.rmtree(final_voice_dir)
            if voice_rows:
                pending_voice_dir.replace(final_voice_dir)
            else:
                shutil.rmtree(pending_voice_dir, ignore_errors=True)
            return upload_id
        except Exception:
            shutil.rmtree(pending_voice_dir, ignore_errors=True)
            raise

    def list_uploads(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT u.id, u.name, u.original_filename, u.uploaded_at,
                       COUNT(w.id) AS workspace_count
                FROM uploads AS u
                JOIN workspaces AS w ON w.upload_id = u.id
                GROUP BY u.id
                ORDER BY u.uploaded_at DESC
                """
            ).fetchall()
            workspace_rows = connection.execute(
                "SELECT id, upload_id, workspace_key, name, story_id FROM workspaces ORDER BY rowid"
            ).fetchall()
        study_sets: dict[str, list[dict[str, Any]]] = {}
        for workspace in workspace_rows:
            study_sets.setdefault(workspace["upload_id"], []).append(
                {
                    "id": workspace["id"],
                    "key": workspace["workspace_key"],
                    "name": workspace["name"],
                    "story_id": workspace["story_id"],
                }
            )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "originalFilename": row["original_filename"],
                "uploadedAt": row["uploaded_at"],
                "workspaceCount": row["workspace_count"],
                "studySets": study_sets.get(row["id"], []),
            }
            for row in rows
        ]

    def list_all_workspaces(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT w.id, w.upload_id, w.workspace_key, w.name, w.relative_path, w.story_id,
                       u.name as upload_name, u.uploaded_at
                FROM workspaces AS w
                JOIN uploads AS u ON u.id = w.upload_id
                ORDER BY u.uploaded_at DESC, w.rowid ASC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "upload_id": row["upload_id"],
                "workspace_key": row["workspace_key"],
                "name": row["name"],
                "title": row["name"],
                "relative_path": row["relative_path"],
                "story_id": row["story_id"],
                "upload_name": row["upload_name"],
                "uploaded_at": row["uploaded_at"],
            }
            for row in rows
        ]

    def list_workspaces(self, upload_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if upload_id:
                rows = connection.execute(
                    """
                    SELECT w.id, w.upload_id, w.workspace_key, w.name, w.relative_path, w.story_id,
                           u.name as upload_name, u.uploaded_at
                    FROM workspaces AS w
                    JOIN uploads AS u ON u.id = w.upload_id
                    WHERE w.upload_id = ?
                    ORDER BY w.rowid ASC
                    """,
                    (upload_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT w.id, w.upload_id, w.workspace_key, w.name, w.relative_path, w.story_id,
                           u.name as upload_name, u.uploaded_at
                    FROM workspaces AS w
                    JOIN uploads AS u ON u.id = w.upload_id
                    ORDER BY u.uploaded_at DESC, w.rowid ASC
                    """
                ).fetchall()
        return [
            {
                "id": row["id"],
                "upload_id": row["upload_id"],
                "workspace_key": row["workspace_key"],
                "name": row["name"],
                "title": row["name"],
                "relative_path": row["relative_path"],
                "story_id": row["story_id"],
                "upload_name": row["upload_name"],
                "uploaded_at": row["uploaded_at"],
            }
            for row in rows
        ]

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT w.id, w.upload_id, w.workspace_key, w.name, w.relative_path, w.story_id,
                       u.name as upload_name, u.uploaded_at
                FROM workspaces AS w
                JOIN uploads AS u ON u.id = w.upload_id
                WHERE w.id = ?
                """,
                (workspace_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "upload_id": row["upload_id"],
            "workspace_key": row["workspace_key"],
            "name": row["name"],
            "title": row["name"],
            "relative_path": row["relative_path"],
            "story_id": row["story_id"],
            "upload_name": row["upload_name"],
            "uploaded_at": row["uploaded_at"],
        }

    def set_workspace_story(self, workspace_id: str, story_id: str | None) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE workspaces SET story_id = ? WHERE id = ?",
                (story_id, workspace_id),
            )
            return cursor.rowcount > 0

    def get_workspace_by_story_id(self, story_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT w.id, w.upload_id, w.workspace_key, w.name, w.relative_path, w.story_id
                FROM workspaces AS w
                WHERE w.story_id = ?
                LIMIT 1
                """,
                (story_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def delete_workspace(self, workspace_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            workspace = connection.execute(
                "SELECT upload_id, workspace_key, name, relative_path FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            if workspace is None:
                raise ValueError("The study set no longer exists")
            upload_id = str(workspace["upload_id"])
            name = str(workspace["name"])
            connection.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            remaining = connection.execute(
                "SELECT COUNT(*) FROM workspaces WHERE upload_id = ?", (upload_id,)
            ).fetchone()[0]
            library_deleted = remaining == 0
            if library_deleted:
                connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
        return {
            "workspaceId": workspace_id,
            "id": workspace_id,
            "name": name,
            "uploadId": upload_id,
            "libraryDeleted": library_deleted,
        }

    def delete_upload(self, upload_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            upload = connection.execute("SELECT name FROM uploads WHERE id = ?", (upload_id,)).fetchone()
            if upload is None:
                raise ValueError("The study library no longer exists")
            workspace_rows = connection.execute(
                "SELECT id FROM workspaces WHERE upload_id = ?", (upload_id,)
            ).fetchall()
            workspace_ids = [str(row["id"]) for row in workspace_rows]
            connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
        return {
            "uploadId": upload_id,
            "name": str(upload["name"]),
            "workspaceIds": workspace_ids,
            "workspaceCount": len(workspace_ids),
        }

    def manifest(self, workspace_id: str, kinds: dict[str, tuple[str, ...]] = KINDS) -> dict[str, Any]:
        result: dict[str, list[dict[str, Any]]] = {}
        with self._connect() as connection:
            for kind, sidecar_suffixes in kinds.items():
                rows = connection.execute(
                    "SELECT subject, filename, body FROM content WHERE workspace_id = ? AND kind = ? ORDER BY lower(filename)",
                    (workspace_id, kind),
                ).fetchall()
                available = {(row["subject"], row["filename"]) for row in rows}
                documents: list[dict[str, Any]] = []
                for row in rows:
                    filename = row["filename"]
                    if Path(filename).suffix.casefold() != ".json":
                        continue
                    try:
                        data = json.loads(bytes(row["body"]).decode("utf-8-sig"))
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    stem = Path(filename).stem
                    title = data.get("title") or data.get("name") or data.get("episode_title") or stem
                    documents.append(
                        {
                            "file": filename,
                            "stem": stem,
                            "title": str(title),
                            "sidecars": [
                                f"{stem}{suffix}"
                                for suffix in sidecar_suffixes
                                if (row["subject"], f"{stem}{suffix}") in available
                            ],
                            "subject": row["subject"] or None,
                        }
                    )
                result[kind] = documents
        from datetime import datetime, timezone
        return {"generatedAt": datetime.now(timezone.utc).isoformat(), "kinds": result}

    def read_content(self, workspace_id: str, kind: str, filename: str) -> tuple[bytes, str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT body, content_type FROM content "
                "WHERE workspace_id = ? AND kind = ? AND filename = ? "
                "ORDER BY CASE WHEN subject = '' THEN 0 ELSE 1 END, lower(subject) LIMIT 1",
                (workspace_id, kind, filename),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(filename)
        return bytes(row["body"]), str(row["content_type"])
