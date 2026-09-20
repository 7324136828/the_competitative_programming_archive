"""API regressions for asynchronous judging and persisted verdicts."""

from pathlib import Path
import tempfile
import time
import unittest

from backend.app import create_app


class SubmissionAPITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="judge_async_api_")
        self.addCleanup(temporary.cleanup)
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": str(Path(temporary.name) / "test.sqlite"),
            "AUTO_SEED": False,
        })
        self.addCleanup(self.app.extensions["submission_jobs"].shutdown)
        self.client = self.app.test_client()
        self.database = self.app.extensions["database"]

    def problem(self, cases):
        return self.database.create_problem({
            "title": "A + B",
            "problem_statements": "Read two integers and print their sum.",
            "sample_input_output": cases,
        })

    def wait_for_job(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/submission-jobs/{job_id}")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            if data["done"]:
                return data
            self.assertIn(data["phase"], ("queued", "compiling", "running"))
            time.sleep(0.01)
        self.fail("Submission did not finish")

    def test_async_submission_preserves_stdin_stdout_and_solved_status(self):
        problem = self.problem([{"input": "2 3", "output": "5"}, {"input": "-1 4", "output": "3"}])
        response = self.client.post("/api/submit", json={
            "problemId": problem["id"], "language": "python",
            "code": "a,b=map(int,input().split());print(a+b)", "async": True,
        })
        self.assertEqual(response.status_code, 202)
        completed = self.wait_for_job(response.get_json()["jobId"])
        self.assertEqual(completed["phase"], "completed")
        self.assertEqual(completed["submission"]["status"], "Accepted")
        self.assertEqual(completed["submission"]["output"].strip(), "5")
        self.assertEqual(completed["grading"]["passedTests"], 2)
        self.assertEqual(completed["grading"]["results"][1]["actualOutput"].strip(), "3")
        self.assertTrue(self.client.get(f"/api/problems/{problem['id']}").get_json()["problem"]["is_solved"])
        self.assertTrue(self.client.get("/api/problems").get_json()["problems"][0]["is_solved"])
        history = self.client.get(f"/api/submissions/{problem['id']}").get_json()["submissions"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "Accepted")

    def test_no_tests_is_not_judged_in_both_api_modes(self):
        problem = self.problem([])
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                response = self.client.post("/api/submit", json={
                    "problemId": problem["id"], "language": "python",
                    "code": "raise RuntimeError('must not execute')", "async": asynchronous,
                })
                self.assertEqual(response.status_code, 202 if asynchronous else 200)
                data = response.get_json()
                if asynchronous:
                    data = self.wait_for_job(data["jobId"])
                self.assertEqual(data["submission"]["status"], "Not Judged")
                self.assertEqual(data["grading"]["totalTests"], 0)
                self.assertFalse(self.client.get(f"/api/problems/{problem['id']}").get_json()["problem"]["is_solved"])

    def test_custom_cases_require_expected_output(self):
        problem = self.problem([])
        for invalid in ({"input": "2 3"}, {"input": "2 3", "output": None}):
            response = self.client.post("/api/submit", json={
                "problemId": problem["id"], "language": "python", "code": "print(5)",
                "customTestCases": [invalid], "async": True,
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("expected output", response.get_json()["error"])
        self.assertEqual(self.database.get_submissions(problem["id"]), [])

    def test_unknown_job_and_invalid_async_are_actionable(self):
        response = self.client.get("/api/submission-jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)
        problem = self.problem([])
        response = self.client.post("/api/submit", json={
            "problemId": problem["id"], "language": "python", "code": "pass", "async": "true",
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
