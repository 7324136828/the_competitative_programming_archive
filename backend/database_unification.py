"""Merge legacy application stores into the shared SQLite database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
import shutil


ARCHIVE_TABLES = (
    'problems',
    'submissions',
    'chat_messages',
    'editor_drafts',
    'problem_translations',
    'problem_solution_traces',
    'problem_audio_assets',
)

JIRA_TABLES = (
    'users',
    'projects',
    'sprints',
    'versions',
    'workflows',
    'workflow_statuses',
    'workflow_transitions',
    'issues',
    'issue_status_history',
    'sprint_issue_events',
    'issue_links',
    'comments',
    'attachments',
    'worklogs',
    'watchers',
    'custom_fields',
    'custom_field_values',
    'automation_rules',
    'automation_logs',
    'pull_requests',
    'saved_filters',
    'notifications',
    'sprint_snapshots',
    'app_settings',
    'ai_requests',
    'ai_ticket_links',
    'activity_log',
)


def _table_exists(connection: sqlite3.Connection, schema: str, table: str) -> bool:
    return connection.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA {schema}.table_info("{table}")')]


def _copy_empty_domain(connection: sqlite3.Connection, source: Path,
                       root_table: str, tables: tuple[str, ...]) -> dict[str, int]:
    if not source.is_file() or not _table_exists(connection, 'main', root_table):
        return {}
    if connection.execute(f'SELECT 1 FROM "{root_table}" LIMIT 1').fetchone():
        return {}

    connection.execute('ATTACH DATABASE ? AS legacy', (str(source),))
    copied: dict[str, int] = {}
    try:
        if not _table_exists(connection, 'legacy', root_table):
            return {}
        for table in tables:
            if not (_table_exists(connection, 'main', table)
                    and _table_exists(connection, 'legacy', table)):
                continue
            target_columns = _columns(connection, 'main', table)
            source_columns = set(_columns(connection, 'legacy', table))
            common = [column for column in target_columns if column in source_columns]
            if not common:
                continue
            quoted = ', '.join(f'"{column}"' for column in common)
            before = connection.total_changes
            connection.execute(
                f'INSERT OR IGNORE INTO main."{table}" ({quoted}) '
                f'SELECT {quoted} FROM legacy."{table}"'
            )
            copied[table] = connection.total_changes - before
        connection.commit()
        return copied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute('DETACH DATABASE legacy')


def merge_legacy_databases(target: str | Path, sources: list[str | Path]) -> dict[str, dict[str, int]]:
    """Copy each legacy domain only when that domain is empty in the target."""
    target = Path(target).resolve()
    results: dict[str, dict[str, int]] = {}
    seen: set[Path] = set()
    for raw_source in sources:
        source = Path(raw_source).resolve()
        if source == target or source in seen or not source.is_file():
            continue
        seen.add(source)
        with closing(sqlite3.connect(target, timeout=30)) as connection:
            connection.execute('PRAGMA foreign_keys = ON')
            archive = _copy_empty_domain(connection, source, 'problems', ARCHIVE_TABLES)
            jira = _copy_empty_domain(connection, source, 'users', JIRA_TABLES)
            if archive or jira:
                results[str(source)] = {**archive, **jira}
    return results


def copy_legacy_workspace(source: str | Path, target: str | Path) -> int:
    """Copy missing app-owned draft/audio files without replacing newer files."""
    source = Path(source).resolve()
    target = Path(target).resolve()
    if source == target or not source.is_dir():
        return 0
    copied = 0
    for item in source.rglob('*'):
        if item.is_symlink() or not item.is_file():
            continue
        destination = target / item.relative_to(source)
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied += 1
    return copied
