"""Unit tests for the LLM connector features:
1. Generate test cases by limitation of the problem.
2. Generate new problems (language='ai', source='unknown') into database.
3. Provide hints in terms of programming thinking steps (minimum 5 steps, maximum 10 steps).
4. Chat functionality.
"""

from pathlib import Path
import tempfile
import unittest

from backend.app import create_app
from backend.llm import (
    chat_response,
    generate_ai_problem,
    generate_test_cases_by_limitations,
    get_thinking_hints,
)


class LLMConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="judge_llm_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = {
            "TESTING": True,
            "DATABASE_PATH": str(self.root / "test.sqlite"),
            "AUTO_SEED": False,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.database = self.app.extensions["database"]

        # Insert a sample problem for testing
        self.problem = self.database.create_problem({
            "title": "Two Sum",
            "problem_statements": (
                "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.\n"
                "Constraints: 2 <= nums.length <= 10^4, -10^9 <= nums[i] <= 10^9, -10^9 <= target <= 10^9"
            ),
            "sample_input_output": [{"input": "2 7 11 15\n9", "output": "0 1"}],
            "hints": ["Consider using a hash map for O(1) lookups."],
            "language": "en",
            "difficulty": "Easy",
            "tags": ["Array", "Hash Table"],
            "source": "https://leetcode.com/problems/two-sum",
        })

    def test_generate_test_cases_by_limitations(self):
        """Requirement (1): generate test cases by the limitation of the problem."""
        cases = generate_test_cases_by_limitations(self.problem)
        self.assertIsInstance(cases, list)
        self.assertGreaterEqual(len(cases), 3)

        for case in cases:
            self.assertIn("input", case)
            self.assertIn("output", case)
            self.assertIn("explanation", case)
            self.assertTrue(len(case["input"]) > 0)

        # Test via API endpoint
        res = self.client.post("/api/llm/generate-testcases", json={"problemId": self.problem["id"]})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["problemId"], self.problem["id"])
        self.assertGreaterEqual(len(body["testCases"]), 3)

    def test_generate_new_problem_ai_language_and_unknown_source(self):
        """Requirement (2): generate new problems into database with language='ai' and source='unknown'."""
        gen = generate_ai_problem(self.problem, difficulty="Medium")
        self.assertEqual(gen["language"], "ai")
        self.assertEqual(gen["source"], "unknown")
        self.assertTrue(gen["title"])
        self.assertTrue(gen["problem_statements"])

        # Test via API endpoint and verify persistence into database
        initial_count = self.database.count()
        res = self.client.post(
            "/api/llm/generate-problem",
            json={"problemId": self.problem["id"], "difficulty": "Medium", "autoSave": True},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])

        saved = body["savedProblem"]
        self.assertEqual(saved["language"], "ai")
        self.assertEqual(saved["source"], "unknown")
        self.assertIn("id", saved)

        # Verify problem is persisted in SQLite
        persisted = self.database.get_problem(saved["id"])
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["language"], "ai")
        self.assertEqual(persisted["source"], "unknown")
        self.assertEqual(self.database.count(), initial_count + 1)

    def test_thinking_steps_hints_bounds(self):
        """Requirement (3): provide hints in terms of programming thinking steps (minimum 5 steps, maximum 10 steps)."""
        hint_data = get_thinking_hints(self.problem, hint_level=1)
        self.assertTrue(hint_data["success"])
        total_steps = hint_data["totalSteps"]

        # Verify minimum 5 steps, maximum 10 steps constraint
        self.assertGreaterEqual(total_steps, 5, "Thinking steps must be at least 5")
        self.assertLessEqual(total_steps, 10, "Thinking steps must be at most 10")
        self.assertEqual(hint_data["minSteps"], 5)
        self.assertEqual(hint_data["maxSteps"], 10)
        self.assertTrue(hint_data["stepTitle"].startswith("Step 1"))
        self.assertTrue(hint_data["hintText"])

        # Test progressive steps via API endpoint
        for level in range(1, total_steps + 1):
            res = self.client.post(
                "/api/llm/hint",
                json={"problemId": self.problem["id"], "hintLevel": level},
            )
            self.assertEqual(res.status_code, 200)
            body = res.get_json()
            self.assertEqual(body["hintLevel"], level)
            self.assertEqual(len(body["allSteps"]), level)
            self.assertIn("Step", body["stepTitle"])

    def test_chat_functionality(self):
        """Verify interactive chat functionality and persistence."""
        res = self.client.post(
            "/api/chat",
            json={
                "message": "Can you give me thinking steps for this problem?",
                "problemId": self.problem["id"],
                "code": "def twoSum(nums, target):\n    pass",
                "language": "python",
                "sessionId": "test-session-1",
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertTrue(body["reply"])

        # Verify message was saved to database
        history_res = self.client.get("/api/chat/history?sessionId=test-session-1")
        self.assertEqual(history_res.status_code, 200)
        history_body = history_res.get_json()
        self.assertTrue(history_body["success"])
        messages = history_body["history"]
        self.assertGreaterEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()

