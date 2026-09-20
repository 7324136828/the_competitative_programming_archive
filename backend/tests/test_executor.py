"""Real-process regression coverage for local execution and grading."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import executor, runtimes

DETECTED_RUNTIMES = runtimes.discover_runtimes()


class ExecutorTests(unittest.TestCase):
    def test_python_run_and_whitespace_normalization(self):
        result = executor.run_code(
            "python",
            "print(sum(map(int, input().split())), '  ')",
            input_text="4 5\n",
            expected_output="9\r\n",
        )
        self.assertEqual(result["status"], "Accepted")
        self.assertTrue(result["passed"])
        self.assertEqual(result["normalizedOutput"], "9")
        self.assertIn("runtimeMs", result)

    def test_run_without_expected_output(self):
        result = executor.run_code("py", "print('hello')")
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["stdout"], "hello\r\n" if executor.os.name == "nt" else "hello\n")

    def test_python_unicode_input_output(self):
        result = executor.run_code("python", "print(input())", input_text="你好", expected_output="你好")
        self.assertEqual(result["status"], "Accepted", result)

    def test_submission_continues_after_wrong_answer(self):
        result = executor.submit_code(
            "python3",
            "print(input())",
            [
                {"input": "first", "output": "incorrect"},
                {"input": "second", "output": "second"},
            ],
        )
        self.assertEqual(result["status"], "Wrong Answer")
        self.assertEqual(result["totalTests"], 2)
        self.assertEqual(result["passedTests"], 1)
        self.assertEqual(result["results"][1]["caseNumber"], 2)

    def test_runtime_error_is_reported(self):
        result = executor.run_code("python", "raise ValueError('bad input')")
        self.assertEqual(result["status"], "Runtime Error")
        self.assertIn("bad input", result["error"])

    def test_timeout_with_large_unread_input_is_bounded(self):
        result = executor.run_code("python", "while True: pass", input_text="x" * 1000000, timeout_ms=200)
        self.assertEqual(result["status"], "Time Limit Exceeded")
        self.assertFalse(result["passed"])
        self.assertLess(result["runtimeMs"], 10000)

    def test_empty_submission_runs_once(self):
        result = executor.submit_code("python", "print('ok')")
        self.assertEqual(result["status"], "Accepted")
        self.assertEqual(result["passedTests"], 1)
        self.assertEqual(result["totalTests"], 1)

    def test_unsupported_language_is_a_compile_error(self):
        result = executor.submit_code("ruby", "puts 'hello'", [{"input": "", "output": "hello"}])
        self.assertEqual(result["status"], "Compilation Error")
        self.assertEqual(result["passedTests"], 0)
        self.assertIn("Unsupported language", result["error"])

    def test_missing_java_has_actionable_error(self):
        with patch.object(executor, "discover_runtimes", return_value={}):
            result = executor.run_code("java", "public class Main {}")
        self.assertEqual(result["status"], "Compilation Error")
        self.assertIn("javac and java", result["error"])

    def test_missing_cpp_has_actionable_error(self):
        with patch.object(executor, "discover_runtimes", return_value={}):
            result = executor.run_code("cpp", "int main() {}")
        self.assertEqual(result["status"], "Compilation Error")
        self.assertIn("C++ compiler", result["error"])

    def test_java_compiler_and_runtime_use_detected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = runtimes.Runtime(str(Path(directory) / "java"), str(Path(directory) / "javac"))
            execution = {"stdout": "42", "stderr": "", "exitCode": 0, "runtimeMs": 1, "timedOut": False}
            with (
                patch.object(executor, "discover_runtimes", return_value={"java": runtime}),
                patch.object(executor, "_run_process", return_value=execution) as process,
            ):
                result = executor.run_code("java", "public class Main {}", expected_output="42")
            self.assertEqual(result["status"], "Accepted")
            self.assertEqual(process.call_args_list[0].args[0][0], runtime.compiler)
            self.assertEqual(process.call_args_list[1].args[0][0], runtime.executable)
            for call in process.call_args_list:
                self.assertEqual(call.kwargs["env"]["PATH"].split(os.pathsep)[0], directory)

    @unittest.skipUnless(os.name == "nt" and Path(runtimes.STRAWBERRY_CPP).is_file(), "Strawberry C++ is unavailable")
    def test_strawberry_compiles_and_runs_without_path_entry(self):
        with patch.dict(os.environ, {"PATH": "", "JAVA_HOME": ""}):
            result = executor.run_code(
                "cpp", '#include <iostream>\nint main() { std::cout << "42"; }', expected_output="42"
            )
        self.assertEqual(result["status"], "Accepted", result)

    def test_timeout_values_are_bounded(self):
        for value in (None, -1, "invalid", float("inf"), float("nan")):
            self.assertEqual(executor._timeout_ms(value), executor.DEFAULT_TIMEOUT_MS)
        self.assertEqual(executor._timeout_ms(1000000), executor.MAX_TIMEOUT_MS)

    @unittest.skipUnless("cpp" in DETECTED_RUNTIMES, "C++ compiler is unavailable")
    def test_cpp_compiles_once_for_multiple_cases(self):
        with patch.object(executor, "_prepare_code", wraps=executor._prepare_code) as prepare:
            result = executor.submit_code(
                "c++",
                "#include <iostream>\nint main() { int n; std::cin >> n; std::cout << n * 2; }",
                [{"input": "2", "output": "4"}, {"input": "7", "output": "14"}],
            )
        self.assertEqual(result["status"], "Accepted", result)
        self.assertEqual(result["passedTests"], 2)
        prepare.assert_called_once()

    @unittest.skipUnless("cpp" in DETECTED_RUNTIMES, "C++ compiler is unavailable")
    def test_cpp_compile_failure(self):
        result = executor.run_code("cpp", "this is not valid C++")
        self.assertEqual(result["status"], "Compilation Error")
        self.assertTrue(result["error"])

    @unittest.skipUnless("java" in DETECTED_RUNTIMES, "JDK is unavailable")
    def test_java_public_class_name(self):
        result = executor.run_code(
            "java",
            'public final class Answer { public static void main(String[] args) { System.out.println("42"); } }',
            expected_output="42",
        )
        self.assertEqual(result["status"], "Accepted", result)


if __name__ == "__main__":
    unittest.main()

