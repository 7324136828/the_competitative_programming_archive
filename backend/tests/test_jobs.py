"""Background judging, persistence, and solved-state regression tests."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.db import Database
from backend.jobs import SubmissionJobs, SubmissionQueueFull


CASES = [{"input": "2 3", "output": "5"}, {"input": "-7 4", "output": "-3"}]
SUM_CODE = "print(sum(map(int, input().split())))"


class SubmissionJobsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="judge_jobs_test_")
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(Path(self.temporary.name) / "test.sqlite")
        self.database.initialize()
        self.problem = self.database.create_problem({
            "title": "Add integers", "problem_statements": "Print their sum.", "sample_input_output": CASES,
        })
        self.jobs = SubmissionJobs(self.database, max_workers=1, max_pending=1)
        self.addCleanup(self.jobs.shutdown)

    def start(self, **overrides):
        values = dict(problem_id=self.problem["id"], language="python", code=SUM_CODE, test_cases=CASES)
        values.update(overrides)
        return self.jobs.start(**values)

    def test_real_job_returns_before_execution_and_persists_final_output(self):
        entered, release = threading.Event(), threading.Event()
        from backend.executor import submit_code as real_submit

        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return real_submit(*args, **kwargs)

        self.addCleanup(release.set)
        with patch("backend.jobs.submit_code", side_effect=delayed):
            pending = self.start()
            self.assertFalse(pending["done"])
            self.assertEqual(pending["phase"], "queued")
            self.assertTrue(entered.wait(5))
            self.assertFalse(self.jobs.get(pending["jobId"])["done"])
            self.assertFalse(self.database.get_problem(self.problem["id"])["is_solved"])
            release.set()
            self.jobs.shutdown()
        result = self.jobs.get(pending["jobId"])
        self.assertTrue(result["done"])
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(result["status"], "Accepted")
        self.assertEqual(result["grading"]["passedTests"], 2)
        self.assertEqual(result["submission"]["output"].strip(), "5")
        self.assertTrue(self.database.get_problem(self.problem["id"])["is_solved"])
        restarted = SubmissionJobs(self.database)
        self.addCleanup(restarted.shutdown)
        self.assertEqual(restarted.get(pending["jobId"])["grading"], result["grading"])

    def test_pending_queue_is_bounded_and_second_manager_does_not_interrupt(self):
        entered, release = threading.Event(), threading.Event()
        from backend.executor import submit_code as real_submit

        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return real_submit(*args, **kwargs)

        self.addCleanup(release.set)
        with patch("backend.jobs.submit_code", side_effect=delayed):
            pending = self.start()
            self.assertTrue(entered.wait(5))
            with self.assertRaises(SubmissionQueueFull):
                self.start()
            other = SubmissionJobs(self.database)
            self.addCleanup(other.shutdown)
            self.assertFalse(other.get(pending["jobId"])["done"])
            release.set()
            self.jobs.shutdown()
        self.assertEqual(len(self.database.get_submissions(self.problem["id"])), 1)

    def test_deleted_job_does_not_attach_to_a_new_problem(self):
        entered, release = threading.Event(), threading.Event()
        from backend.executor import submit_code as real_submit

        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return real_submit(*args, **kwargs)

        self.addCleanup(release.set)
        with patch("backend.jobs.submit_code", side_effect=delayed):
            pending = self.start()
            self.assertTrue(entered.wait(5))
            self.database.clear()
            new_problem = self.database.create_problem({"title": "New", "problem_statements": "New problem"})
            self.assertNotEqual(new_problem["id"], self.problem["id"])
            release.set()
            self.jobs.shutdown()
        self.assertIsNone(self.jobs.get(pending["jobId"]))
        self.assertFalse(self.database.get_problem(new_problem["id"])["is_solved"])
        self.assertEqual(self.database.get_submissions(new_problem["id"]), [])

    def test_orphaned_job_is_reported_as_interrupted(self):
        self.database.save_submission({
            "problem_id": self.problem["id"], "language": "python", "code": SUM_CODE,
            "status": "Running", "phase": "running", "job_id": "old-process-job",
        })
        result = self.jobs.get("old-process-job")
        self.assertTrue(result["done"])
        self.assertEqual(result["status"], "Interrupted")
        self.assertIn("submit again", result["grading"]["error"])
        self.assertFalse(self.database.get_problem(self.problem["id"])["is_solved"])

    def test_invalid_cases_are_rejected_without_persisting_a_job(self):
        with self.assertRaises(ValueError):
            self.start(test_cases=[{"input": "2 3", "output": None}])
        self.assertEqual(self.database.get_submissions(self.problem["id"]), [])

    def test_no_tests_cannot_mark_problem_solved(self):
        pending = self.start(test_cases=[])
        self.jobs.shutdown()
        result = self.jobs.get(pending["jobId"])
        self.assertTrue(result["done"])
        self.assertEqual(result["status"], "Not Judged")
        self.assertFalse(self.database.get_problem(self.problem["id"])["is_solved"])

    def test_fake_legacy_acceptance_does_not_mark_problem_solved(self):
        self.database.save_submission({
            "problem_id": self.problem["id"], "language": "python", "code": "pass", "status": "Accepted",
            "test_results": [{"expectedOutput": None, "stdout": "", "passed": True, "status": "Success"}],
        })
        self.assertFalse(self.database.get_problem(self.problem["id"])["is_solved"])
        self.assertFalse(self.database.get_problems()["problems"][0]["is_solved"])
        self.database.save_submission({
            "problem_id": self.problem["id"], "language": "python", "code": "pass", "status": "Accepted",
            "test_results": [{"expectedOutput": "", "actualOutput": "", "passed": True, "status": "Accepted"}],
        })
        self.assertTrue(self.database.get_problem(self.problem["id"])["is_solved"])


class MigrationTests(unittest.TestCase):
    def test_existing_schema_is_migrated_without_trusting_ungraded_acceptances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript("""
                    CREATE TABLE problems (id INTEGER PRIMARY KEY, title TEXT, problem_statements TEXT,
                        sample_input_output TEXT, hints TEXT, language TEXT, difficulty TEXT, tags TEXT);
                    CREATE TABLE submissions (id INTEGER PRIMARY KEY, problem_id INTEGER, language TEXT,
                        code TEXT, status TEXT, runtime_ms REAL, output TEXT, error TEXT, test_results TEXT,
                        created_at DATETIME);
                    INSERT INTO problems VALUES (1, 'Legacy', 'Sum', '[]', '[]', 'en', 'Easy', '[]');
                    INSERT INTO problems VALUES (2, 'Verified', 'Sum', '[]', '[]', 'en', 'Easy', '[]');
                """)
                for pid, expected in ((1, None), (2, "5")):
                    connection.execute(
                        "INSERT INTO submissions (problem_id, status, test_results) VALUES (?, 'Accepted', ?)",
                        (pid, json.dumps([{"expectedOutput": expected, "actualOutput": "5", "passed": True}])),
                    )
                connection.commit()
            database = Database(path)
            self.assertFalse(database.initialize())
            self.assertFalse(database.get_problem(1)["is_solved"])
            self.assertTrue(database.get_problem(2)["is_solved"])


if __name__ == "__main__":
    unittest.main()
