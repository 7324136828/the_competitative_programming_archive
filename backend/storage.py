"""Disk-backed editor drafts and portable exports of the submission archive."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import uuid
import zipfile

from .db import Database
from .runtimes import language_id


MAX_DRAFT_BYTES = 2 * 1024 * 1024
SOURCE_EXTENSIONS = {"python": "py", "cpp": "cpp", "java": "java"}


class DraftProblemNotFound(LookupError):
    """The draft's owning problem no longer exists."""


class DraftConflict(Exception):
    """A save based on an older revision must not overwrite a newer draft."""

    def __init__(self, current: dict) -> None:
        super().__init__("This draft changed in another editor. Reload the saved draft before saving again.")
        self.current = current


class DraftStore:
    def __init__(self, database: Database, directory: str | Path) -> None:
        self.database = database
        self.directory = Path(directory).resolve()

    @staticmethod
    def _key(problem_id: int | str, language: str) -> tuple[int, str]:
        if isinstance(problem_id, bool):
            raise ValueError("problemId must be a positive integer.")
        try:
            identifier = int(problem_id)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("problemId must be a positive integer.") from exc
        if identifier < 1 or str(identifier) != str(problem_id):
            raise ValueError("problemId must be a positive integer.")
        normalized = language_id(language)
        if normalized not in SOURCE_EXTENSIONS:
            raise ValueError("Unsupported draft language. Choose python, cpp, or java.")
        return identifier, normalized

    def _path(self, reference: str, problem_id: int, language: str) -> Path:
        """Accept only paths minted by this store, even if a DB reference was modified."""
        extension = SOURCE_EXTENSIONS[language]
        if not re.fullmatch(rf"{problem_id}/{language}/[0-9a-f]{{32}}\.{extension}", reference):
            raise ValueError("Invalid draft file reference.")
        candidate = self.directory.joinpath(*PurePosixPath(reference).parts).resolve()
        if not candidate.is_relative_to(self.directory):
            raise ValueError("Draft file reference is outside the draft directory.")
        return candidate

    def _metadata(self, problem_id: int, language: str, row, code: str | None = None) -> dict:
        return {
            "problemId": problem_id,
            "language": language,
            "code": code,
            "revision": row["revision"] if row else 0,
            "saved": code is not None,
            "updatedAt": row["updated_at"] if row else None,
        }

    def _read(self, problem_id: int, language: str, row) -> dict:
        code = None
        if row:
            try:
                path = self._path(row["file_path"], problem_id, language)
                # Bounded reads avoid loading an unexpectedly replaced file into memory.
                with path.open("rb") as stream:
                    payload = stream.read(MAX_DRAFT_BYTES + 1)
                if len(payload) <= MAX_DRAFT_BYTES:
                    code = payload.decode("utf-8")
            except (OSError, UnicodeError, ValueError):
                pass
        return self._metadata(problem_id, language, row, code)

    def get(self, problem_id: int | str, language: str) -> dict:
        identifier, language = self._key(problem_id, language)
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            if not connection.execute("SELECT 1 FROM problems WHERE id = ?", (identifier,)).fetchone():
                raise DraftProblemNotFound("Problem not found.")
            row = connection.execute(
                "SELECT * FROM editor_drafts WHERE problem_id = ? AND language = ?", (identifier, language)
            ).fetchone()
            return self._read(identifier, language, row)

    def save(self, problem_id: int | str, language: str, code: str, revision: int) -> dict:
        identifier, language = self._key(problem_id, language)
        if not isinstance(code, str):
            raise ValueError("Draft code must be a string.")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("A nonnegative integer base revision is required to save a draft.")
        try:
            payload = code.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("Draft code must contain valid UTF-8 text.") from exc
        if len(payload) > MAX_DRAFT_BYTES:
            raise ValueError("Draft code exceeds the 2 MiB limit.")

        final_path = None
        temporary_path = None
        previous_path = None
        try:
            with self.database.connect() as connection:
                # The database serializes saves across processes and browser tabs before disk writes.
                connection.execute("BEGIN IMMEDIATE")
                if not connection.execute("SELECT 1 FROM problems WHERE id = ?", (identifier,)).fetchone():
                    raise DraftProblemNotFound("Problem not found.")
                row = connection.execute(
                    "SELECT * FROM editor_drafts WHERE problem_id = ? AND language = ?", (identifier, language)
                ).fetchone()
                if revision != (row["revision"] if row else 0):
                    raise DraftConflict(self._read(identifier, language, row))

                reference = f"{identifier}/{language}/{uuid.uuid4().hex}.{SOURCE_EXTENSIONS[language]}"
                final_path = self._path(reference, identifier, language)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="wb", dir=final_path.parent, prefix=".draft-", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, final_path)
                temporary_path = None
                updated_at = datetime.now(timezone.utc).isoformat()
                next_revision = revision + 1
                connection.execute(
                    """INSERT INTO editor_drafts (problem_id, language, file_path, revision, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(problem_id, language) DO UPDATE SET
                         file_path = excluded.file_path, revision = excluded.revision,
                         updated_at = excluded.updated_at""",
                    (identifier, language, reference, next_revision, updated_at),
                )
                if row:
                    try:
                        previous_path = self._path(row["file_path"], identifier, language)
                    except ValueError:
                        pass
            # Remove only the previous app-owned file, after the new reference commits.
            if previous_path is not None:
                try:
                    previous_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return self._metadata(identifier, language, {"revision": next_revision, "updated_at": updated_at}, code)
        except BaseException:
            for path in (temporary_path, final_path):
                if path is not None:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
            raise


def export_submissions(database: Database) -> BytesIO:
    """Export every persisted attempt with its source and complete grading metadata."""
    archive = BytesIO()
    exported_at = datetime.now(timezone.utc).isoformat()
    count = 0
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for submission in database.iter_submissions():
            # IDs come from SQLite and extensions from a fixed mapping; titles never form paths.
            folder = f"submissions/{submission['id']:06d}"
            extension = SOURCE_EXTENSIONS.get(language_id(submission["language"]), "txt")
            bundle.writestr(f"{folder}/source.{extension}", submission["code"].encode("utf-8"))
            bundle.writestr(
                f"{folder}/metadata.json",
                json.dumps(submission, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            count += 1
        bundle.writestr(
            "manifest.json",
            json.dumps({"formatVersion": 1, "exportedAt": exported_at, "totalSubmissions": count}, indent=2),
        )
    archive.seek(0)
    return archive
