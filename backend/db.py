"""SQLite persistence for problems, submissions, and chat history."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator

SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    problem_statements TEXT NOT NULL,
    sample_input_output TEXT DEFAULT '[]',
    hints TEXT DEFAULT '[]',
    language TEXT DEFAULT 'en',
    difficulty TEXT DEFAULT 'Medium',
    tags TEXT DEFAULT '[]',
    source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    status TEXT NOT NULL,
    runtime_ms REAL DEFAULT 0,
    output TEXT DEFAULT '',
    error TEXT DEFAULT '',
    test_results TEXT DEFAULT '[]',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(problem_id) REFERENCES problems(id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_problems_language ON problems(language);
CREATE INDEX IF NOT EXISTS idx_problems_difficulty ON problems(difficulty);
CREATE INDEX IF NOT EXISTS idx_submissions_problem_id ON submissions(problem_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
"""


def bounded_int(value: Any, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = default
    return max(minimum, min(maximum, number) if maximum else number)


def format_row(row: sqlite3.Row | None, json_fields: tuple[str, ...]) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for field in json_fields:
        try:
            result[field] = json.loads(result.get(field) or "[]")
        except (ValueError, TypeError):
            result[field] = []
    return result


def format_problem(row: sqlite3.Row | None) -> dict | None:
    return format_row(row, ("sample_input_output", "hints", "tags"))


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> bool:
        """Return True only for a new schema, not an intentionally empty bank."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            existed = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'problems'"
            ).fetchone()
            connection.executescript(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(problems)")}
            if "source" not in columns:
                connection.execute("ALTER TABLE problems ADD COLUMN source TEXT")
        return not existed

    def count(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]

    def get_problems(
        self,
        page: int = 1,
        limit: int = 20,
        search: str = "",
        language: str = "",
        difficulty: str = "",
    ) -> dict:
        page = bounded_int(page, 1)
        limit = bounded_int(limit, 20, maximum=100)
        offset = (page - 1) * limit
        clauses = []
        parameters = []

        if search.strip():
            clauses.append("(title LIKE ? OR problem_statements LIKE ? OR tags LIKE ?)")
            term = f"%{search.strip()}%"
            parameters.extend([term, term, term])
        if language.strip():
            clauses.append("language = ?")
            parameters.append(language.strip().lower())
        if difficulty.strip():
            clauses.append("difficulty = ?")
            parameters.append(difficulty.strip().capitalize())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM problems {where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM problems {where} ORDER BY id ASC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()

        return {
            "problems": [format_problem(row) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": max(1, (total + limit - 1) // limit),
        }

    def get_problem(self, problem_id: int | str) -> dict | None:
        try:
            pid = int(problem_id)
        except (ValueError, TypeError):
            return None
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()
            return format_problem(row)

    def create_problem(self, problem: dict) -> dict:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO problems (title, problem_statements, sample_input_output,
                                      hints, language, difficulty, tags, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    problem["title"],
                    problem["problem_statements"],
                    json.dumps(problem.get("sample_input_output", [])),
                    json.dumps(problem.get("hints", [])),
                    problem.get("language", "en"),
                    problem.get("difficulty", "Medium"),
                    json.dumps(problem.get("tags", [])),
                    problem.get("source"),
                ),
            )
            created_id = cursor.lastrowid
            row = connection.execute("SELECT * FROM problems WHERE id = ?", (created_id,)).fetchone()
            return format_problem(row)  # type: ignore[return-value]

    def bulk_insert(self, problems: list[dict]) -> int:
        if not problems:
            return 0
        with self.connect() as connection:
            records = [
                (
                    problem["title"],
                    problem["problem_statements"],
                    json.dumps(problem.get("sample_input_output", [])),
                    json.dumps(problem.get("hints", [])),
                    problem.get("language", "en"),
                    problem.get("difficulty", "Medium"),
                    json.dumps(problem.get("tags", [])),
                    problem.get("source"),
                )
                for problem in problems
            ]
            connection.executemany(
                """
                INSERT INTO problems (title, problem_statements, sample_input_output,
                                      hints, language, difficulty, tags, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            return len(records)

    def save_submission(self, submission: dict) -> dict:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO submissions (problem_id, language, code, status,
                                         runtime_ms, output, error, test_results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission["problem_id"],
                    submission["language"],
                    submission["code"],
                    submission["status"],
                    submission.get("runtime_ms", 0),
                    submission.get("output", ""),
                    submission.get("error", ""),
                    json.dumps(submission.get("test_results", [])),
                ),
            )
            row = connection.execute(
                "SELECT * FROM submissions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return format_row(row, ("test_results",))  # type: ignore[return-value]

    def get_submissions(self, problem_id: int | str, limit: int = 20) -> list[dict]:
        try:
            pid = int(problem_id)
        except (ValueError, TypeError):
            return []
        limit = bounded_int(limit, 20, maximum=100)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM submissions WHERE problem_id = ? ORDER BY id DESC LIMIT ?",
                (pid, limit),
            ).fetchall()
            return [format_row(row, ("test_results",)) for row in rows]  # type: ignore[misc]

    def clear(self) -> dict:
        with self.connect() as connection:
            deleted_problems = connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
            deleted_submissions = connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            connection.executescript(
                """
                DELETE FROM submissions;
                DELETE FROM problems;
                DELETE FROM chat_messages;
                DELETE FROM sqlite_sequence WHERE name IN ('problems', 'submissions', 'chat_messages');
                """
            )
        return {
            "deletedProblems": deleted_problems,
            "deletedSubmissions": deleted_submissions,
        }

    def save_chat_message(self, role: str, content: str, session_id: str = "default") -> dict:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            row = connection.execute(
                "SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)

    def get_chat_history(self, session_id: str = "default", limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

