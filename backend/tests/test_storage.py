"""Persistence regressions for draft revisions and complete submission archives."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
import zipfile

from backend.db import Database
from backend.storage import DraftConflict, DraftProblemNotFound, DraftStore, MAX_DRAFT_BYTES, export_submissions


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="archive_storage_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = Database(self.root / "test.sqlite")
        self.database.initialize()
        self.problem = self.database.create_problem({"title": "A + B", "problem_statements": "Add two numbers."})
        self.problem_id = self.problem["id"]
        self.store = DraftStore(self.database, self.root / "drafts")

    def reference(self, problem_id=None, language="python"):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM editor_drafts WHERE problem_id = ? AND language = ?",
                (problem_id or self.problem_id, language),
            ).fetchone()["file_path"]

    def test_no_reference_defaults_then_disk_reference_survives_restart(self):
        absent = self.store.get(self.problem_id, "python")
        self.assertIsNone(absent["code"])
        self.assertFalse(absent["saved"])
        self.assertEqual(absent["revision"], 0)
        code = "# café and 数字\nprint('hello')\r\n"
        saved = self.store.save(self.problem_id, "python", code, 0)
        self.assertEqual(saved["revision"], 1)
        reference = self.reference()
        self.assertFalse(Path(reference).is_absolute())
        self.assertEqual((self.store.directory / reference).read_bytes(), code.encode("utf-8"))
        reopened = DraftStore(Database(self.database.path), self.store.directory)
        self.assertEqual(reopened.get(self.problem_id, "py"), saved)

    def test_legacy_default_algorithm_tags_are_cleared_only_once(self):
        legacy_path = self.root / "legacy-tags.sqlite"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """CREATE TABLE problems (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, problem_statements TEXT NOT NULL,
                    sample_input_output TEXT DEFAULT '[]', hints TEXT DEFAULT '[]',
                    language TEXT DEFAULT 'en', difficulty TEXT DEFAULT 'Medium',
                    tags TEXT DEFAULT '[]', source TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                "INSERT INTO problems (title, problem_statements, tags) VALUES (?, ?, ?)",
                ("Legacy", "Needs classification", json.dumps(["Algorithm"])),
            )
            connection.commit()
        finally:
            connection.close()
        migrated = Database(legacy_path)
        migrated.initialize()
        self.assertEqual(migrated.get_problem(1)["tags"], [])

        explicit = migrated.create_problem({
            "title": "Explicit", "problem_statements": "Already classified", "tags": ["Algorithm"],
        })
        Database(legacy_path).initialize()
        self.assertEqual(migrated.get_problem(explicit["id"])["tags"], ["Algorithm"])

    def test_empty_code_is_saved_and_languages_and_problems_are_independent(self):
        other = self.database.create_problem({"title": "Other", "problem_statements": "Something else"})
        self.store.save(self.problem_id, "python", "", 0)
        self.store.save(self.problem_id, "cpp", "int main() {}", 0)
        self.store.save(other["id"], "python", "pass", 0)
        self.assertTrue(self.store.get(self.problem_id, "python")["saved"])
        self.assertEqual(self.store.get(self.problem_id, "python")["code"], "")
        self.assertEqual(self.store.get(self.problem_id, "cpp")["code"], "int main() {}")
        self.assertEqual(self.store.get(other["id"], "python")["code"], "pass")
        self.assertIsNone(self.store.get(self.problem_id, "java")["code"])

    def test_missing_file_defaults_but_retains_revision_for_recovery(self):
        self.store.save(self.problem_id, "python", "lost", 0)
        (self.store.directory / self.reference()).unlink()
        missing = self.store.get(self.problem_id, "python")
        self.assertIsNone(missing["code"])
        self.assertFalse(missing["saved"])
        self.assertEqual(missing["revision"], 1)
        self.assertEqual(self.store.save(self.problem_id, "python", "recovered", 1)["revision"], 2)

    def test_stale_save_does_not_change_disk_or_database(self):
        self.store.save(self.problem_id, "python", "first", 0)
        original = self.store.directory / self.reference()
        latest = self.store.save(self.problem_id, "python", "new", 1)
        self.assertFalse(original.exists())
        with self.assertRaises(DraftConflict) as caught:
            self.store.save(self.problem_id, "python", "stale", 1)
        self.assertEqual(caught.exception.current, latest)
        self.assertEqual(self.store.get(self.problem_id, "python"), latest)
        self.assertEqual(len(list(self.store.directory.rglob("*.py"))), 1)

    def test_parallel_saves_from_separate_stores_compare_revisions_atomically(self):
        barrier = Barrier(2)

        def save(code):
            store = DraftStore(Database(self.database.path), self.store.directory)
            barrier.wait(timeout=5)
            try:
                return store.save(self.problem_id, "python", code, 0)
            except DraftConflict as conflict:
                return conflict

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ["tab one", "tab two"]))
        successful = [result for result in results if isinstance(result, dict)]
        self.assertEqual(len(successful), 1)
        self.assertEqual(sum(isinstance(result, DraftConflict) for result in results), 1)
        self.assertEqual(self.store.get(self.problem_id, "python"), successful[0])

    def test_transaction_failure_preserves_previous_file_and_removes_failed_write(self):
        original = self.store.save(self.problem_id, "python", "original", 0)
        with self.database.connect() as connection:
            connection.execute("""CREATE TRIGGER reject_draft BEFORE UPDATE ON editor_drafts
                                  BEGIN SELECT RAISE(ABORT, 'simulated disk reference failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save(self.problem_id, "python", "rejected", 1)
        self.assertEqual(self.store.get(self.problem_id, "python"), original)
        self.assertEqual(len(list(self.store.directory.rglob("*.py"))), 1)
        self.assertEqual(list(self.store.directory.rglob(".draft-*")), [])

    def test_modified_db_reference_cannot_read_or_delete_unrelated_file(self):
        outside = self.root / "private.txt"
        outside.write_text("must stay private", encoding="utf-8")
        self.store.save(self.problem_id, "python", "old", 0)
        for malicious in ("../private.txt", str(outside), "1/python/../../private.txt"):
            with self.subTest(reference=malicious):
                with self.database.connect() as connection:
                    connection.execute(
                        "UPDATE editor_drafts SET file_path = ? WHERE problem_id = ?", (malicious, self.problem_id)
                    )
                self.assertIsNone(self.store.get(self.problem_id, "python")["code"])
                current = self.store.get(self.problem_id, "python")["revision"]
                self.store.save(self.problem_id, "python", "fixed", current)
                self.assertEqual(outside.read_text(encoding="utf-8"), "must stay private")

    def test_invalid_language_revision_and_oversized_utf8_are_rejected(self):
        for revision in (None, "0", -1, False, 1.5):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.store.save(self.problem_id, "python", "pass", revision)
        for language in ("../python", "unknown", "python/../../other"):
            with self.subTest(language=language), self.assertRaises(ValueError):
                self.store.save(self.problem_id, language, "pass", 0)
        with self.assertRaises(ValueError):
            self.store.save(self.problem_id, "python", "é" * (MAX_DRAFT_BYTES // 2 + 1), 0)
        with self.assertRaises(DraftProblemNotFound):
            self.store.save(99999, "python", "pass", 0)
        with self.assertRaises(ValueError):
            self.store.save(self.problem_id, "python", None, 0)

    def test_clear_cascades_database_references_without_deleting_unrelated_files(self):
        self.store.save(self.problem_id, "python", "code", 0)
        unrelated = self.store.directory / "keep.txt"
        unrelated.write_text("keep", encoding="utf-8")
        self.database.clear()
        with self.database.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM editor_drafts").fetchone()[0], 0)
        self.assertTrue(unrelated.exists())
        with self.assertRaises(DraftProblemNotFound):
            self.store.get(self.problem_id, "python")

    def test_initialize_migrates_existing_database_without_changing_submissions(self):
        submission = self.database.save_submission({
            "problem_id": self.problem_id, "language": "python", "code": "pass", "status": "Not Judged",
        })
        with self.database.connect() as connection:
            connection.execute("DROP TABLE editor_drafts")
        self.assertFalse(self.database.initialize())
        self.assertIsNone(self.store.get(self.problem_id, "python")["code"])
        self.assertEqual(self.database.get_submission(submission["id"])["code"], "pass")

    def test_history_and_zip_include_all_pages_statuses_metadata_and_safe_paths(self):
        other = self.database.create_problem({"title": "../../危险\\problem", "problem_statements": "Unicode"})
        statuses = ["Queued", "Compiling", "Running", "Wrong Answer", "Compilation Error", "Accepted", "Not Judged"]
        for index in range(107):
            status = statuses[index % len(statuses)]
            self.database.save_submission({
                "problem_id": other["id"] if index % 2 else self.problem_id,
                "language": "cpp" if index % 2 else "python",
                "code": f"// 数字 {index}\n",
                "status": status,
                "phase": status.lower() if status in ("Queued", "Compiling", "Running") else "completed",
                "test_results": [{"passed": True, "expectedOutput": "5", "actualOutput": "5"}] if status == "Accepted" else [],
            })
        first = self.database.list_submissions(limit=100)
        last = self.database.list_submissions(page=2, limit=100)
        self.assertEqual(first["total"], 107)
        self.assertEqual(first["totalPages"], 2)
        self.assertEqual(len(first["submissions"]), 100)
        self.assertEqual(len(last["submissions"]), 7)
        self.assertEqual(first["submissions"][0]["id"], 107)
        self.assertEqual(self.database.list_submissions(problem_id=other["id"])["total"], 53)
        self.assertEqual(self.database.get_submission(2)["problem_title"], other["title"])
        self.assertIsNone(self.database.get_submission("missing"))
        with zipfile.ZipFile(export_submissions(self.database)) as archive:
            self.assertEqual(len(archive.namelist()), 215)
            self.assertEqual(json.loads(archive.read("manifest.json"))["totalSubmissions"], 107)
            self.assertEqual(archive.read("submissions/000107/source.py").decode("utf-8"), "// 数字 106\n")
            exported_statuses = set()
            for filename in archive.namelist():
                self.assertNotIn("..", Path(filename).parts)
                self.assertFalse(filename.startswith(("/", "\\")))
                if filename.endswith("/metadata.json"):
                    metadata = json.loads(archive.read(filename))
                    exported_statuses.add(metadata["status"])
                    self.assertEqual(bool(metadata["verified"]), metadata["status"] == "Accepted")
                    self.assertIn("code", metadata)
                    self.assertIn("test_results", metadata)
            self.assertEqual(exported_statuses, set(statuses))

    def test_empty_archive_is_a_valid_zip(self):
        with zipfile.ZipFile(export_submissions(self.database)) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json"])
            self.assertEqual(json.loads(archive.read("manifest.json"))["totalSubmissions"], 0)


if __name__ == "__main__":
    unittest.main()
