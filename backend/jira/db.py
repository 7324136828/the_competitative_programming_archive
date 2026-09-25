import os
import sqlite3
import threading
from pathlib import Path

from .config import resolve_db_path

SQL_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

_SCHEMA_PATH = Path(__file__).resolve().parent / 'schema.sql'


class _DB:
    """Single shared sqlite3 connection (check_same_thread=False) guarded by an
    RLock. Mirrors node:sqlite autocommit semantics; with_transaction handles
    BEGIN/COMMIT with nested SAVEPOINTs."""

    def __init__(self):
        self._lock = threading.RLock()
        self._tx_depth = threading.local()
        self._conn: sqlite3.Connection | None = None
        self.path = ''
        self.open(resolve_db_path())

    # ----- connection lifecycle -----

    def open(self, path: str):
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self.path = path
            if path != ':memory:':
                os.makedirs(os.path.dirname(path), exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            conn.row_factory = sqlite3.Row
            if path != ':memory:':
                conn.execute('PRAGMA journal_mode = WAL;')
                conn.execute('PRAGMA busy_timeout = 5000;')
                conn.execute('PRAGMA synchronous = NORMAL;')
            conn.execute('PRAGMA foreign_keys = ON;')
            self._conn = conn
            self._tx_depth.v = 0
            self._init_schema()

    def reopen(self, path: str | None = None):
        """Used by tests to get a fresh database in the same process."""
        self.open(path or resolve_db_path())

    # ----- schema -----

    def _init_schema(self):
        self._conn.executescript(_SCHEMA_PATH.read_text(encoding='utf-8'))
        self._ensure_column('sprints', 'started_at', 'started_at TEXT')
        self._ensure_column('sprints', 'completed_at', 'completed_at TEXT')
        self._ensure_column('sprints', 'committed_points', 'committed_points REAL')
        self._ensure_column('sprints', 'committed_issue_count', 'committed_issue_count INTEGER')
        self._ensure_column('sprints', 'completed_points', 'completed_points REAL')
        self._ensure_column('sprints', 'completed_issue_count', 'completed_issue_count INTEGER')
        self._ensure_column('issues', 'story_type', "story_type TEXT DEFAULT 'coding'")
        self._ensure_column('issues', 'difficulty', "difficulty TEXT DEFAULT 'Medium'")
        self._ensure_column('issues', 'problem_id', 'problem_id INTEGER')
        self._ensure_column('issues', 'sample_io_json', "sample_io_json TEXT DEFAULT '[]'")
        self._ensure_column('issues', 'hints_json', "hints_json TEXT DEFAULT '[]'")
        self._ensure_column('issues', 'tags_json', "tags_json TEXT DEFAULT '[]'")
        self._ensure_column('issues', 'submission_status', "submission_status TEXT DEFAULT 'Unsolved'")
        self._ensure_unique_problem_links()
        self._ensure_fts_consistency()

    def _ensure_column(self, table: str, column: str, ddl: str):
        cols = self._conn.execute(f'PRAGMA table_info({table})').fetchall()
        if not any(c['name'] == column for c in cols):
            self._conn.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')

    def _ensure_unique_problem_links(self):
        duplicates = self._conn.execute(
            """SELECT problem_id FROM issues WHERE problem_id IS NOT NULL
               GROUP BY problem_id HAVING COUNT(*) > 1"""
        ).fetchall()
        for duplicate in duplicates:
            rows = self._conn.execute(
                "SELECT id FROM issues WHERE problem_id = ? ORDER BY created_at, rowid",
                (duplicate['problem_id'],),
            ).fetchall()
            for row in rows[1:]:
                self._conn.execute('UPDATE issues SET problem_id = NULL WHERE id = ?', (row['id'],))
        self._conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_problem_id_unique
               ON issues(problem_id) WHERE problem_id IS NOT NULL"""
        )

    def _ensure_fts_consistency(self):
        fts = self._conn.execute('SELECT COUNT(*) c FROM issues_fts').fetchone()['c']
        issues = self._conn.execute('SELECT COUNT(*) c FROM issues').fetchone()['c']
        if fts != issues:
            self._conn.execute('DELETE FROM issues_fts')
            self._conn.execute(
                """INSERT INTO issues_fts (issue_id, key, summary, description, comments)
                   SELECT i.id, i.key, i.summary, COALESCE(i.description, ''),
                     COALESCE((SELECT group_concat(c.body, ' ') FROM comments c WHERE c.issue_id = i.id), '')
                   FROM issues i"""
            )

    # ----- query helpers -----

    def q(self, sql: str, *params) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def q1(self, sql: str, *params) -> dict | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def run(self, sql: str, *params) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def exec(self, sql: str):
        with self._lock:
            self._conn.execute(sql)

    # ----- transactions -----

    def _depth(self) -> int:
        return getattr(self._tx_depth, 'v', 0)

    def with_transaction(self, fn):
        with self._lock:
            if self._depth() == 0:
                self._conn.execute('BEGIN')
                self._tx_depth.v = 1
                try:
                    result = fn()
                    self._conn.execute('COMMIT')
                    return result
                except Exception:
                    self._conn.execute('ROLLBACK')
                    raise
                finally:
                    self._tx_depth.v = 0
            sp = f'sp_{self._depth()}'
            self._conn.execute(f'SAVEPOINT {sp}')
            self._tx_depth.v = self._depth() + 1
            try:
                result = fn()
                self._conn.execute(f'RELEASE {sp}')
                return result
            except Exception:
                self._conn.execute(f'ROLLBACK TO {sp}')
                self._conn.execute(f'RELEASE {sp}')
                raise
            finally:
                self._tx_depth.v = self._depth() - 1


db = _DB()
