"""SQLite persistence for problems, submissions, and chat history."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator

from .executor import normalize_output

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
    verified INTEGER NOT NULL DEFAULT 0,
    job_id TEXT,
    phase TEXT NOT NULL DEFAULT 'completed',
    grading TEXT,
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
CREATE TABLE IF NOT EXISTS editor_drafts (
    problem_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    file_path TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (problem_id, language),
    FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS problem_translations (
    problem_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    title TEXT NOT NULL,
    problem_statements TEXT NOT NULL,
    hints TEXT NOT NULL DEFAULT '[]',
    provider TEXT,
    model TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (problem_id, language),
    FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS problem_solution_traces (
    problem_id INTEGER NOT NULL,
    hint_level INTEGER NOT NULL,
    trace_json TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (problem_id, hint_level),
    FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS problem_audio_assets (
    problem_id INTEGER PRIMARY KEY,
    cache_key TEXT,
    url TEXT,
    status TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
    problem = format_row(row, ("sample_input_output", "hints", "tags"))
    if problem is not None:
        problem["is_solved"] = bool(problem.get("is_solved", False))
    return problem


def verified_acceptance(submission: dict) -> bool:
    """Only real, successful expected-output comparisons establish a solved problem."""
    cases = submission.get("test_results")
    return (
        submission.get("status") == "Accepted"
        and isinstance(cases, list)
        and bool(cases)
        and all(
            isinstance(case, dict)
            and case.get("passed") is True
            and isinstance(case.get("expectedOutput"), str)
            and isinstance(case.get("actualOutput", case.get("stdout")), str)
            and normalize_output(case.get("actualOutput", case.get("stdout"))) == normalize_output(case["expectedOutput"])
            for case in cases
        )
    )


SOLVED_EXISTS = """EXISTS (
    SELECT 1 FROM submissions
    WHERE submissions.problem_id = problems.id
      AND submissions.status = 'Accepted' AND submissions.verified = 1
)"""

PROBLEM_SELECT = f"SELECT problems.*, {SOLVED_EXISTS} AS is_solved FROM problems"


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
            legacy_tag_migration = "remove_legacy_algorithm_tag_default_v1"
            if connection.execute(
                "SELECT 1 FROM schema_migrations WHERE name = ?", (legacy_tag_migration,)
            ).fetchone() is None:
                # Older imports assigned this generic placeholder whenever no
                # tag was supplied. It is not a user- or AI-selected tag, and
                # otherwise prevents the visible-page tag generator from ever
                # asking The Connector to classify those problems.
                connection.execute(
                    "UPDATE problems SET tags = '[]' WHERE tags = ?",
                    (json.dumps(["Algorithm"]),),
                )
                connection.execute(
                    "INSERT INTO schema_migrations (name) VALUES (?)", (legacy_tag_migration,)
                )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(problems)")}
            if "source" not in columns:
                connection.execute("ALTER TABLE problems ADD COLUMN source TEXT")
            submission_columns = {row["name"] for row in connection.execute("PRAGMA table_info(submissions)")}
            for name, declaration in (
                ("verified", "INTEGER NOT NULL DEFAULT 0"),
                ("job_id", "TEXT"),
                ("phase", "TEXT NOT NULL DEFAULT 'completed'"),
                ("grading", "TEXT"),
            ):
                if name not in submission_columns:
                    connection.execute(f"ALTER TABLE submissions ADD COLUMN {name} {declaration}")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_job_id ON submissions(job_id)")
            if "verified" not in submission_columns:
                for row in connection.execute("SELECT * FROM submissions WHERE status = 'Accepted'").fetchall():
                    submission = format_row(row, ("test_results",))
                    connection.execute(
                        "UPDATE submissions SET verified = ? WHERE id = ?",
                        (int(verified_acceptance(submission)), row["id"]),
                    )
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
        solved: str = "",
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
        solved_filter = solved.strip().lower()
        if solved_filter not in ("", "all", "solved", "unsolved"):
            raise ValueError("solved must be 'solved', 'unsolved', or 'all'.")
        if solved_filter == "solved":
            clauses.append(SOLVED_EXISTS)
        elif solved_filter == "unsolved":
            clauses.append(f"NOT {SOLVED_EXISTS}")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM problems {where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"{PROBLEM_SELECT} {where} ORDER BY id ASC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
            problems = [format_problem(row) for row in rows]
            self._attach_story_links(connection, problems)
        return {
            "problems": problems,
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
            row = connection.execute(f"{PROBLEM_SELECT} WHERE id = ?", (pid,)).fetchone()
            problem = format_problem(row)
            if problem is None:
                return None
            self._attach_story_links(connection, [problem])
            problem["translations"] = [
                format_row(item, ("hints",))
                for item in connection.execute(
                    "SELECT * FROM problem_translations WHERE problem_id = ? ORDER BY language",
                    (pid,),
                ).fetchall()
            ]
            problem["solution_traces"] = [
                format_row(item, ("trace_json",))
                for item in connection.execute(
                    "SELECT * FROM problem_solution_traces WHERE problem_id = ? ORDER BY hint_level",
                    (pid,),
                ).fetchall()
            ]
            audio = connection.execute(
                "SELECT cache_key, url, status, updated_at FROM problem_audio_assets WHERE problem_id = ?",
                (pid,),
            ).fetchone()
            problem["audio_asset"] = dict(audio) if audio else None
            return problem

    @staticmethod
    def _attach_story_links(connection: sqlite3.Connection, problems: list[dict | None]) -> None:
        valid = [problem for problem in problems if problem is not None]
        if not valid or connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'issues'"
        ).fetchone() is None:
            return
        ids = [int(problem["id"]) for problem in valid]
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""SELECT id, key, summary, status, problem_id
                FROM issues WHERE problem_id IN ({placeholders})""",
            ids,
        ).fetchall()
        links = {int(row["problem_id"]): dict(row) for row in rows}
        for problem in valid:
            story = links.get(int(problem["id"]))
            problem["story"] = story
            problem["story_id"] = story["id"] if story else None
            problem["story_key"] = story["key"] if story else None

    def save_translation(self, problem_id: int, language: str, result: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO problem_translations
                     (problem_id, language, title, problem_statements, hints, provider, model, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(problem_id, language) DO UPDATE SET
                     title=excluded.title, problem_statements=excluded.problem_statements,
                     hints=excluded.hints, provider=excluded.provider, model=excluded.model,
                     updated_at=CURRENT_TIMESTAMP""",
                (problem_id, language, result.get("translatedTitle", ""),
                 result.get("translatedStatements", ""),
                 json.dumps(result.get("translatedHints", [])),
                 result.get("provider"), result.get("model")),
            )

    def save_solution_trace(self, problem_id: int, result: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO problem_solution_traces
                     (problem_id, hint_level, trace_json, provider, model, updated_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(problem_id, hint_level) DO UPDATE SET
                     trace_json=excluded.trace_json, provider=excluded.provider,
                     model=excluded.model, updated_at=CURRENT_TIMESTAMP""",
                (problem_id, int(result.get("hintLevel", 1)), json.dumps(result),
                 result.get("provider"), result.get("model")),
            )

    def save_audio_asset(self, problem_id: int, result: dict) -> None:
        url = f'/api/audio/{result["key"]}.mp3' if result.get("status") == "ready" and result.get("key") else None
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO problem_audio_assets (problem_id, cache_key, url, status, updated_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(problem_id) DO UPDATE SET cache_key=excluded.cache_key,
                     url=excluded.url, status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
                (problem_id, result.get("key"), url, result.get("status", "missing")),
            )

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

    def set_problem_tags_if_empty(self, problem_id: int, tags: list[str]) -> dict | None:
        """Persist tags once, without replacing tags saved by another request."""
        if not tags or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ValueError("tags must contain at least one non-empty string.")
        normalized = [tag.strip() for tag in tags]
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()
            if row is None:
                return None
            current = format_problem(row)
            if current and current["tags"]:
                return current
            # Compare against the raw value read above so a concurrent writer wins
            # instead of having its generated tag overwritten.
            connection.execute(
                "UPDATE problems SET tags = ? WHERE id = ? AND tags IS ?",
                (json.dumps(normalized), problem_id, row["tags"]),
            )
            updated = connection.execute(f"{PROBLEM_SELECT} WHERE problems.id = ?", (problem_id,)).fetchone()
            return format_problem(updated)

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
                                         runtime_ms, output, error, test_results, verified, job_id, phase, grading)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(verified_acceptance(submission)),
                    submission.get("job_id"),
                    submission.get("phase", "completed"),
                    json.dumps(submission["grading"]) if submission.get("grading") is not None else None,
                ),
            )
            row = connection.execute(
                "SELECT * FROM submissions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return format_row(row, ("test_results", "grading"))  # type: ignore[return-value]

    def get_submission_job(self, job_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM submissions WHERE job_id = ?", (job_id,)).fetchone()
            return format_row(row, ("test_results", "grading"))

    def update_submission_phase(self, job_id: str, phase: str) -> bool:
        if phase not in ("compiling", "running"):
            raise ValueError("Invalid submission phase.")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE submissions SET phase = ?, status = ? WHERE job_id = ? AND phase != 'completed'",
                (phase, phase.capitalize(), job_id),
            )
            return cursor.rowcount > 0

    def finish_submission_job(self, job_id: str, grading: dict) -> dict | None:
        results = grading.get("results", [])
        first = results[0] if results else {}
        verified = verified_acceptance({"status": grading["status"], "test_results": results})
        with self.connect() as connection:
            # UUID matching also makes an in-flight completion harmless after database.clear().
            connection.execute(
                """UPDATE submissions SET phase = 'completed', status = ?, runtime_ms = ?, output = ?,
                    error = ?, test_results = ?, verified = ?, grading = ? WHERE job_id = ?""",
                (
                    grading["status"],
                    grading.get("totalRuntimeMs", 0),
                    first.get("actualOutput", first.get("stdout", "")),
                    grading.get("error") or next((case["error"] for case in results if case.get("error")), ""),
                    json.dumps(results),
                    int(verified),
                    json.dumps(grading),
                    job_id,
                ),
            )
            row = connection.execute("SELECT * FROM submissions WHERE job_id = ?", (job_id,)).fetchone()
            return format_row(row, ("test_results", "grading"))

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
            return [format_row(row, ("test_results", "grading")) for row in rows]  # type: ignore[misc]

    def get_submission(self, submission_id: int | str) -> dict | None:
        try:
            identifier = int(submission_id)
        except (ValueError, TypeError):
            return None
        with self.connect() as connection:
            row = connection.execute(
                """SELECT submissions.*, problems.title AS problem_title
                   FROM submissions JOIN problems ON problems.id = submissions.problem_id
                   WHERE submissions.id = ?""",
                (identifier,),
            ).fetchone()
            return format_row(row, ("test_results", "grading"))

    def list_submissions(self, page: int = 1, limit: int = 20, problem_id: int | None = None) -> dict:
        """Paginate all verdicts, including in-flight and unsuccessful submissions."""
        page = bounded_int(page, 1)
        limit = bounded_int(limit, 20, maximum=100)
        where = "WHERE submissions.problem_id = ?" if problem_id is not None else ""
        parameters = [problem_id] if problem_id is not None else []
        with self.connect() as connection:
            # A read transaction keeps the count and page from disagreeing during a new submission.
            connection.execute("BEGIN")
            total = connection.execute(f"SELECT COUNT(*) FROM submissions {where}", parameters).fetchone()[0]
            rows = connection.execute(
                f"""SELECT submissions.*, problems.title AS problem_title
                    FROM submissions JOIN problems ON problems.id = submissions.problem_id
                    {where} ORDER BY submissions.id DESC LIMIT ? OFFSET ?""",
                [*parameters, limit, (page - 1) * limit],
            ).fetchall()
        return {
            "submissions": [format_row(row, ("test_results", "grading")) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": max(1, (total + limit - 1) // limit),
        }

    def iter_submissions(self) -> Generator[dict, None, None]:
        """Read every submission from a single snapshot without the UI pagination cap."""
        with self.connect() as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                """SELECT submissions.*, problems.title AS problem_title
                   FROM submissions JOIN problems ON problems.id = submissions.problem_id
                   ORDER BY submissions.id ASC"""
            )
            for row in rows:
                yield format_row(row, ("test_results", "grading"))  # type: ignore[misc]

    def clear(self) -> dict:
        with self.connect() as connection:
            deleted_problems = connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
            deleted_submissions = connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'issues'"
            ).fetchone():
                connection.execute(
                    """UPDATE issues SET parent_id = NULL WHERE parent_id IN
                       (SELECT id FROM issues WHERE problem_id IS NOT NULL)"""
                )
                connection.execute("DELETE FROM issues WHERE problem_id IS NOT NULL")
            connection.execute("DELETE FROM submissions")
            connection.execute("DELETE FROM problems")
            connection.execute("DELETE FROM chat_messages")
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
