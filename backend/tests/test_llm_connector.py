"""Unit tests for the LLM connector features:
1. Generate test cases by limitation of the problem.
2. Generate new problems (language='ai', source='unknown') into database.
3. Provide hints in terms of programming thinking steps (minimum 5 steps, maximum 10 steps).
4. Chat functionality.
"""

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from backend.app import create_app
from backend.llm import (
    chat_response,
    generate_ai_problem,
    generate_test_cases_by_limitations,
    get_thinking_hints,
    get_model_info,
    LLMError,
)


class LLMConnectorTests(unittest.TestCase):
    def setUp(self):
        offline = patch.dict(os.environ, {"LLM_PROVIDER": "mock", "LLM_MODEL": ""})
        offline.start()
        self.addCleanup(offline.stop)
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


class GatewayConnectorTests(unittest.TestCase):
    """Exercise real request/response parsing without reaching an upstream provider."""

    def setUp(self):
        environment = patch.dict(os.environ, {
            "LLM_PROVIDER": "the_connector", "LLM_MODEL": "",
            "CONNECTOR_BASE_URL": "http://connector.test/v1", "LLM_TIMEOUT_SECONDS": "120",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.problem = {
            "title": "A + B", "problem_statements": "Read two integers and print their sum.",
            "sample_input_output": [{"input": "1 2\n", "output": "3\n"}],
        }
        self.calls = []
        self.models = [{"id": "z-assistant"}, {"id": "a-assistant", "owned_by": "the_connector"}]
        self.reply = "A response from the selected model."
        self.replies = []
        self.discovery_status = 200
        self.completion_status = 200
        self.failure = None
        original_client = httpx.Client
        transport = httpx.MockTransport(self.handle_request)
        client_patch = patch("backend.llm.httpx.Client", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs))
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def handle_request(self, request):
        self.calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if self.failure:
            raise self.failure
        if request.url.path == "/v1/models":
            return httpx.Response(self.discovery_status, json={"object": "list", "data": self.models})
        self.assertEqual(request.url.path, "/v1/chat/completions")
        reply = self.replies.pop(0) if self.replies else self.reply
        return httpx.Response(self.completion_status, json={
            "choices": [{"message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            "error": {"message": "upstream-token-should-never-be-exposed"},
        })

    def test_discovery_precedes_completion_and_selected_alias_is_sent(self):
        result = chat_response([{"role": "user", "content": "Explain addition."}])
        self.assertEqual(result["model"], "a-assistant")
        self.assertEqual(result["provider"], "the_connector")
        self.assertEqual([call[:2] for call in self.calls], [("GET", "/v1/models"), ("POST", "/v1/chat/completions")])
        self.assertEqual(self.calls[1][2]["model"], "a-assistant")
        self.assertFalse(self.calls[1][2]["stream"])
        # Leave provider-dependent temperature and response_format to gateway routes.
        self.assertNotIn("temperature", self.calls[1][2])
        self.assertNotIn("response_format", self.calls[1][2])

    def test_environment_and_request_models_are_validated(self):
        with patch.dict(os.environ, {"LLM_MODEL": "z-assistant"}):
            self.assertEqual(get_model_info()["model"], "z-assistant")
            self.assertEqual(get_model_info("a-assistant")["model"], "a-assistant")
        with self.assertRaises(LLMError) as caught:
            get_model_info("missing-model")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertTrue(all(call[0] == "GET" for call in self.calls))
        with self.assertRaises(LLMError) as caught:
            get_model_info({"id": "a-assistant"})
        self.assertEqual(caught.exception.status_code, 400)

    def test_no_active_models_has_actionable_error(self):
        self.models = []
        with self.assertRaisesRegex(LLMError, "Save and activate") as caught:
            generate_ai_problem()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(len(self.calls), 1)

    def test_network_failure_never_falls_back_to_mock(self):
        self.failure = httpx.ConnectError("sensitive upstream details")
        with self.assertRaisesRegex(LLMError, "Cannot reach The Connector") as caught:
            generate_test_cases_by_limitations(self.problem)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("sensitive", str(caught.exception))

    def test_http_failure_does_not_leak_gateway_error_body(self):
        self.completion_status = 502
        with self.assertRaisesRegex(LLMError, "HTTP 502") as caught:
            generate_ai_problem()
        self.assertNotIn("upstream-token", str(caught.exception))

    def test_empty_completion_and_invalid_json_are_errors(self):
        for response in ("", "Here is an invalid partial response: {", "{\"title\": \"Only a title\"}"):
            with self.subTest(response=response):
                self.reply = response
                with self.assertRaises(LLMError):
                    generate_ai_problem()

    def test_generated_problem_schema_and_provenance(self):
        self.reply = json.dumps({
            "title": "Add three integers", "problem_statements": "Read a, b, c and print a+b+c.",
            "sample_input_output": [{"input": "1 2 3\n", "output": "6\n"}],
            "hints": ["Add the numbers."], "tags": ["Math"], "difficulty": "Easy",
            "source": "untrusted", "language": "en",
        })
        generated = generate_ai_problem(self.problem, difficulty="Easy", model="z-assistant")
        self.assertEqual(generated["language"], "ai")
        self.assertEqual(generated["source"], "unknown")
        self.assertEqual(generated["model"], "z-assistant")
        self.assertEqual(generated["sample_input_output"][0]["output"], "6\n")
        data = json.loads(self.reply)
        data["sample_input_output"] = [{"input": "1 2 3"}]
        self.reply = json.dumps(data)
        with self.assertRaises(LLMError):
            generate_ai_problem(self.problem)

    def test_invalid_json_gets_one_portable_repair_request(self):
        cases = [{"input": "1 2\n", "output": "3\n", "explanation": "Small inputs"}] * 3
        self.replies = ['[{"input":"1 2", "output": "3",}]', json.dumps(cases)]
        self.assertEqual(generate_test_cases_by_limitations(self.problem), cases)
        completions = [call[2] for call in self.calls if call[0] == "POST"]
        self.assertEqual(len(completions), 2)
        self.assertEqual(completions[1]["messages"][-2]["role"], "assistant")
        self.assertIn("not valid JSON", completions[1]["messages"][-1]["content"])
        self.assertNotIn("response_format", completions[1])
        self.assertEqual(completions[1]["model"], "a-assistant")

    def test_invalid_json_repair_is_bounded_and_never_returns_mock_data(self):
        self.reply = 'Invalid JSON with unescaped \\sum'
        with self.assertRaisesRegex(LLMError, "invalid JSON"):
            generate_ai_problem(self.problem)
        self.assertEqual(sum(call[0] == "POST" for call in self.calls), 2)

    def test_hints_use_real_completion_and_enforce_step_bounds(self):
        steps = [{"title": f"Reason {index}", "category": "Thinking", "description": f"Description {index}"} for index in range(6)]
        self.reply = "```json\n" + json.dumps(steps) + "\n```"
        hints = get_thinking_hints(self.problem, hint_level=2)
        self.assertEqual(hints["model"], "a-assistant")
        self.assertEqual(hints["totalSteps"], 6)
        self.assertEqual(len(hints["allSteps"]), 2)
        self.assertEqual(hints["stepTitle"], "Step 2: Reason 1")
        self.assertEqual(hints["hintText"], "Description 1")
        for count in (4, 11):
            self.reply = json.dumps([steps[0]] * count)
            with self.assertRaisesRegex(LLMError, "between 5 and 10"):
                get_thinking_hints(self.problem)

    def test_generated_test_cases_preserve_whitespace_and_reject_null_outputs(self):
        cases = [{"input": " 1 2\n", "output": "3\n", "explanation": "Small positive values"}] * 3
        self.reply = json.dumps(cases)
        self.assertEqual(generate_test_cases_by_limitations(self.problem), cases)
        cases[0] = {"input": "1 2", "output": None, "explanation": "Missing output"}
        self.reply = json.dumps(cases)
        with self.assertRaises(LLMError):
            generate_test_cases_by_limitations(self.problem)

    def test_mock_provider_is_explicit_and_makes_no_network_calls(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
            self.assertEqual(get_model_info()["model"], "mock-assistant")
            self.assertEqual(generate_ai_problem()["provider"], "mock")
            self.assertTrue(get_thinking_hints(self.problem)["success"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
