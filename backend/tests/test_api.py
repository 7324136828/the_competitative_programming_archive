"""API tests using isolated databases and the Flask API."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app import create_app

SUM_CODE = "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n"


def problem(title="Add integers", **overrides):
    return {
        "title": title,
        "problem_statements": "Read two integers and print their sum.",
        "sample_input_output": [
            {"input": "2 3", "output": "5"},
            {"input": "-7 4", "output": "-3"},
        ],
        "hints": ["Add the two values."],
        "language": "en",
        "difficulty": "Easy",
        "tags": ["Math"],
        **overrides,
    }


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="judge_api_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.seed_path = self.root / "seed.json"
        self.seed_path.write_text(json.dumps([problem("Seed fixture")]), encoding="utf-8")
        self.config = {
            "TESTING": True,
            "DATABASE_PATH": str(self.root / "test.sqlite"),
            "AUTO_SEED": False,
            "SEED_PATH": str(self.seed_path),
            "CLIENT_DIST": str(self.root / "dist"),
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.database = self.app.extensions["database"]

    def assert_success(self, response):
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(response.is_json)
        body = response.get_json()
        self.assertTrue(body["success"], body)
        return body

    def create_problem(self, **overrides):
        return self.assert_success(self.client.post("/api/problems", json=problem(**overrides)))["problem"]

    def submit(self, problem_id, **overrides):
        return self.assert_success(
            self.client.post(
                "/api/submit",
                json={
                    "problemId": problem_id,
                    "language": "python",
                    "code": SUM_CODE,
                    **overrides,
                },
            )
        )

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("totalProblems", body)

    def test_language_list_reflects_detected_runtimes(self):
        python = {"id": "python", "label": "Python 3", "editorLanguage": "python"}
        cpp = {"id": "cpp", "label": "C++", "editorLanguage": "cpp"}
        for available in ([python], [python, cpp], []):
            with self.subTest(available=available), patch("backend.app.available_languages", return_value=available):
                body = self.assert_success(self.client.get("/api/languages"))
                self.assertEqual(body["languages"], available)

    def test_json_import_accepts_array_envelope_and_single_problem(self):
        for payload in ([problem("Array")], {"problems": [problem("Envelope")]}, problem("Single")):
            with self.subTest(payload=payload):
                body = self.assert_success(self.client.post("/api/problems/upload", json=payload))
                self.assertEqual(body["insertedCount"], 1)
        self.assertEqual(self.database.count(), 3)
        restarted = create_app(self.config).test_client()
        body = self.assert_success(restarted.get("/api/problems"))
        self.assertEqual([entry["title"] for entry in body["problems"]], ["Array", "Envelope", "Single"])

    def test_multipart_import_preserves_unicode_and_decodes_legacy_arrays(self):
        record = problem("Сумма", language="ru")
        record["hints"] = json.dumps(record["hints"])
        record["tags"] = json.dumps(record["tags"])
        record["sample_input_output"] = json.dumps(record["sample_input_output"])
        content = json.dumps({"problems": [record]}, ensure_ascii=False).encode("utf-8-sig")
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            body = self.assert_success(
                self.client.post(
                    "/api/problems/upload",
                    data={"file": (BytesIO(content), "problems.json")},
                    content_type="multipart/form-data",
                )
            )
        output = "\n".join(logs.output)
        self.assertIn("Problem archive processing entry 1/1:", output)
        self.assertIn("Problem archive import complete", output)
        self.assertEqual(body["totalNow"], 1)
        imported = self.assert_success(self.client.get("/api/problems/1"))["problem"]
        self.assertEqual(imported["title"], record["title"])
        self.assertEqual(imported["sample_input_output"], problem()["sample_input_output"])
        self.assertEqual(imported["hints"], problem()["hints"])

    def test_clear_database_removes_problems_and_submissions(self):
        created = self.create_problem()
        self.submit(created["id"])
        self.assertEqual(self.database.count(), 1)
        body = self.assert_success(self.client.delete("/api/database"))
        self.assertEqual(body["deletedProblems"], 1)
        self.assertEqual(body["deletedSubmissions"], 1)
        self.assertEqual(self.database.count(), 0)

    def test_run_code_accepted(self):
        res = self.client.post(
            "/api/run",
            json={"language": "python", "code": "print(int(input()) * 2)", "input": "21", "expectedOutput": "42"},
        )
        body = self.assert_success(res)
        self.assertEqual(body["result"]["status"], "Accepted")
        self.assertTrue(body["result"]["passed"])

    def test_problem_list_can_exclude_or_select_solved_problems(self):
        solved = self.create_problem(title="Solved")
        unsolved = self.create_problem(title="Unsolved")
        self.submit(solved["id"])

        unsolved_body = self.assert_success(self.client.get("/api/problems?solved=unsolved"))
        self.assertEqual(unsolved_body["total"], 1)
        self.assertEqual(unsolved_body["problems"][0]["id"], unsolved["id"])
        solved_body = self.assert_success(self.client.get("/api/problems?solved=solved"))
        self.assertEqual(solved_body["total"], 1)
        self.assertEqual(solved_body["problems"][0]["id"], solved["id"])
        self.assertEqual(self.client.get("/api/problems?solved=maybe").status_code, 400)

    def test_tag_batches_generate_only_for_untagged_problems_and_persist_once(self):
        tagged = self.create_problem(title="Already tagged")
        untagged = self.create_problem(title="Needs a tag", tags=[])
        generated = {
            "success": True,
            "provider": "mock",
            "model": "mock-assistant",
            "tags": [{"problemId": untagged["id"], "tag": "Math"}],
        }
        with patch("backend.app.generate_problem_tags", return_value=generated) as generator:
            body = self.assert_success(self.client.post(
                "/api/llm/generate-tags",
                json={"problemIds": [tagged["id"], untagged["id"]]},
            ))
        generator.assert_called_once()
        self.assertEqual([item["problemId"] for item in body["tags"]], [tagged["id"], untagged["id"]])
        self.assertEqual(self.database.get_problem(untagged["id"])["tags"], ["Math"])

        with patch("backend.app.generate_problem_tags") as generator:
            again = self.assert_success(self.client.post(
                "/api/llm/generate-tags", json={"problemIds": [untagged["id"]]},
            ))
        generator.assert_not_called()
        self.assertEqual(again["tags"][0]["tags"], ["Math"])

    def test_tag_batch_rejects_more_than_six_or_duplicate_problem_ids(self):
        for problem_ids in ([1, 2, 3, 4, 5, 6, 7], [1, 1], [], [True]):
            with self.subTest(problem_ids=problem_ids):
                response = self.client.post("/api/llm/generate-tags", json={"problemIds": problem_ids})
                self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

