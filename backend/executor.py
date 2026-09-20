"""Compile and run local submissions with the existing API result format.

Submitted programs run with the backend user's permissions in isolated temporary directories.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

from .runtimes import discover_runtimes, language_id

DEFAULT_TIMEOUT_MS = 5000
MAX_TIMEOUT_MS = 30000
COMPILE_TIMEOUT_MS = 15000
MAX_OUTPUT_BYTES = 1024 * 1024


def normalize_output(value: str | None) -> str:
    """Ignore outer whitespace and trailing whitespace on individual lines."""
    if not value:
        return ""
    return "\n".join(
        line.rstrip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()


def _timeout_ms(value: int | float | str | None) -> int:
    try:
        timeout = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    if not math.isfinite(timeout) or timeout <= 0:
        return DEFAULT_TIMEOUT_MS
    return max(1, min(int(timeout), MAX_TIMEOUT_MS))


def _kill_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _read_output(stream: tempfile.TemporaryFile) -> str:  # type: ignore[type-arg]
    stream.seek(0)
    value = stream.read(MAX_OUTPUT_BYTES + 1)
    text = value[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if len(value) > MAX_OUTPUT_BYTES:
        text += "\n[Output truncated after 1 MiB]"
    return text


def _run_process(
    command: list[str],
    cwd: Path | str,
    input_text: str = "",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    env: dict[str, str] | None = None,
) -> dict:
    started = time.perf_counter()
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        stdin.write(str(input_text or "").encode("utf-8"))
        stdin.seek(0)
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                env=env,
                **options,
            )
        except OSError as exc:
            return {"stdout": "", "stderr": str(exc), "exitCode": -1, "runtimeMs": 0, "timedOut": False}

        timed_out = False
        try:
            process.wait(timeout=_timeout_ms(timeout_ms) / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(process)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        return {
            "stdout": _read_output(stdout),
            "stderr": _read_output(stderr),
            "exitCode": process.returncode,
            "runtimeMs": round((time.perf_counter() - started) * 1000, 1),
            "timedOut": timed_out,
        }


def _prepare_code(language: str, code: str, directory: Path | str) -> tuple[list[str] | None, str | None, dict[str, str] | None]:
    language_name = language_id(language)
    dir_path = Path(directory)
    if language_name not in ("python", "cpp", "java"):
        return None, f"Unsupported language: {language}. Supported languages: Python, C++, Java.", None
    runtime = discover_runtimes().get(language_name)
    if not runtime:
        errors = {
            "python": "A working Python 3 interpreter is not available on this system.",
            "cpp": r"A working C++ compiler (g++ or clang++) is required in PATH or C:\Strawberry\c\bin.",
            "java": "Java compiler/runtime (javac and java) must be installed and available in PATH or JAVA_HOME.",
        }
        return None, errors[language_name], None
    environment = runtime.environment()
    if language_name == "python":
        (dir_path / "solution.py").write_text(code, encoding="utf-8")
        return [runtime.executable, "-X", "utf8", "solution.py"], None, environment

    if language_name == "cpp":
        executable = dir_path / ("solution.exe" if os.name == "nt" else "solution")
        (dir_path / "solution.cpp").write_text(code, encoding="utf-8")
        compiled = _run_process(
            [runtime.compiler or runtime.executable, "-O2", "solution.cpp", "-o", executable.name],
            dir_path,
            timeout_ms=COMPILE_TIMEOUT_MS,
            env=environment,
        )
        if compiled["timedOut"]:
            return None, "C++ compilation timed out after 15000ms.", environment
        if compiled["exitCode"] != 0 or not executable.exists():
            return None, compiled["stderr"] or "Compilation failed with unknown error", environment
        return [str(executable)], None, environment

    match = re.search(r"public\s+(?:(?:final|abstract)\s+)*class\s+([A-Za-z_$][A-Za-z0-9_$]*)", code)
    class_name = match.group(1) if match else "Main"
    source_name = class_name + ".java"
    (dir_path / source_name).write_text(code, encoding="utf-8")
    compiled = _run_process(
        [runtime.compiler or "javac", "-encoding", "UTF-8", source_name],
        dir_path,
        timeout_ms=COMPILE_TIMEOUT_MS,
        env=environment,
    )
    if compiled["timedOut"]:
        return None, "Java compilation timed out after 15000ms.", environment
    if compiled["exitCode"] != 0:
        return None, compiled["stderr"] or "Java compilation failed.", environment
    return [runtime.executable, "-cp", str(dir_path), class_name], None, environment


def run_code(
    language: str,
    code: str,
    input_text: str = "",
    expected_output: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict:
    """Run one input, optionally compare its expected output, and clean up."""
    timeout_ms = _timeout_ms(timeout_ms)
    with tempfile.TemporaryDirectory(prefix="oj_", ignore_cleanup_errors=True) as directory:
        command, error, environment = _prepare_code(language, code, directory)
        if error or not command:
            return {
                "status": "Compilation Error",
                "error": error or "Could not prepare command",
                "stdout": "",
                "stderr": error or "",
                "runtimeMs": 0,
                "passed": False,
            }
        result = _run_process(command, directory, input_text, timeout_ms, env=environment)
        response = {
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "runtimeMs": result["runtimeMs"],
            "passed": False,
        }
        if result["timedOut"]:
            return {**response, "status": "Time Limit Exceeded", "error": f"Execution timed out after {timeout_ms}ms"}
        if result["exitCode"] != 0:
            return {
                **response,
                "status": "Runtime Error",
                "error": result["stderr"] or f"Process exited with code {result['exitCode']}",
            }
        actual = normalize_output(result["stdout"])
        compare = expected_output is not None and expected_output != ""
        passed = actual == normalize_output(expected_output) if compare else True
        return {
            **response,
            "status": ("Accepted" if passed else "Wrong Answer") if compare else "Success",
            "passed": passed,
            "normalizedOutput": actual,
            "expectedOutput": expected_output,
            "error": result["stderr"] if not passed else "",
        }


def submit_code(
    language: str,
    code: str,
    test_cases: list[dict] | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict:
    """Compile once, run each test, and preserve the first failing verdict."""
    timeout_ms = _timeout_ms(timeout_ms)
    if not test_cases:
        single = run_code(language, code, timeout_ms=timeout_ms)
        return {
            "status": "Accepted" if single["status"] == "Success" else single["status"],
            "totalTests": 1,
            "passedTests": int(single["passed"]),
            "totalRuntimeMs": single["runtimeMs"],
            "results": [single],
        }

    with tempfile.TemporaryDirectory(prefix="oj_sub_", ignore_cleanup_errors=True) as directory:
        command, error, environment = _prepare_code(language, code, directory)
        if error or not command:
            return {
                "status": "Compilation Error",
                "error": error or "Could not prepare command",
                "totalTests": len(test_cases),
                "passedTests": 0,
                "totalRuntimeMs": 0,
                "results": [
                    {
                        "status": "Compilation Error",
                        "passed": False,
                        "input": case.get("input"),
                        "expectedOutput": case.get("output"),
                        "actualOutput": "",
                        "error": error,
                        "runtimeMs": 0,
                    }
                    for case in test_cases
                ],
            }

        results = []
        status = "Accepted"
        for index, case in enumerate(test_cases, start=1):
            execution = _run_process(command, directory, case.get("input", ""), timeout_ms, env=environment)
            result = {
                "caseNumber": index,
                "input": case.get("input"),
                "expectedOutput": case.get("output"),
                "actualOutput": execution["stdout"],
                "runtimeMs": execution["runtimeMs"],
                "passed": False,
            }
            if execution["timedOut"]:
                result.update(status="Time Limit Exceeded", error=f"Time limit exceeded ({timeout_ms}ms)")
            elif execution["exitCode"] != 0:
                result.update(status="Runtime Error", error=execution["stderr"] or f"Exit code {execution['exitCode']}")
            else:
                result["passed"] = normalize_output(execution["stdout"]) == normalize_output(case.get("output", ""))
                result["status"] = "Accepted" if result["passed"] else "Wrong Answer"
            if status == "Accepted" and not result["passed"]:
                status = result["status"]
            results.append(result)
        return {
            "status": status,
            "totalTests": len(test_cases),
            "passedTests": sum(result["passed"] for result in results),
            "totalRuntimeMs": round(sum(result["runtimeMs"] for result in results), 1),
            "results": results,
        }

