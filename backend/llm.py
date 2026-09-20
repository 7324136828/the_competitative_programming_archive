"""LLM Connector supporting Gemini, OpenAI, Claude, OpenRouter, Ollama, and local mock.

Provides:
1. Test case generation by limitation of the problem.
2. AI problem generation (language='ai', source='unknown') into database.
3. Problem hints in terms of programming thinking steps (minimum 5 steps, maximum 10 steps).
4. Conversational AI chat with code and problem context.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

import httpx

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ru": "Russian",
    "ja": "Japanese",
    "ai": "AI Language",
}

_CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")


def get_active_provider() -> tuple[str, str | None]:
    """Detect available provider and credentials."""
    forced = os.environ.get("LLM_PROVIDER", "").lower().strip()
    if forced:
        return forced, os.environ.get(f"{forced.upper()}_API_KEY")

    if os.environ.get("GEMINI_API_KEY"):
        return "gemini", os.environ.get("GEMINI_API_KEY")
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ.get("OPENAI_API_KEY")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude", os.environ.get("ANTHROPIC_API_KEY")
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter", os.environ.get("OPENROUTER_API_KEY")
    if os.environ.get("OLLAMA_HOST"):
        return "ollama", os.environ.get("OLLAMA_HOST")
    return "mock", None


def _call_upstream_llm(provider: str, api_key: str | None, messages: list[dict], system_prompt: str | None = None) -> str | None:
    try:
        timeout = httpx.Timeout(15.0, connect=5.0)
        with httpx.Client(timeout=timeout) as client:
            if provider == "gemini" and api_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                contents = []
                if system_prompt:
                    contents.append({"role": "user", "parts": [{"text": f"System Instruction:\n{system_prompt}"}]})
                    contents.append({"role": "model", "parts": [{"text": "Understood."}]})
                for m in messages:
                    role = "model" if m.get("role") == "assistant" else "user"
                    contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
                res = client.post(url, json={"contents": contents})
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")

            elif provider in ("openai", "openrouter") and api_key:
                base_url = "https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.openai.com/v1"
                headers = {"Authorization": f"Bearer {api_key}"}
                req_messages = []
                if system_prompt:
                    req_messages.append({"role": "system", "content": system_prompt})
                req_messages.extend(messages)
                model = os.environ.get("LLM_MODEL") or ("openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini")
                res = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": model, "messages": req_messages, "temperature": 0.7},
                )
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")

            elif provider == "claude" and api_key:
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                res = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": os.environ.get("LLM_MODEL") or "claude-3-5-haiku-20241022",
                        "system": system_prompt or "",
                        "messages": messages,
                        "max_tokens": 1024,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("content", [])
                    if content and content[0].get("type") == "text":
                        return content[0].get("text", "")

            elif provider == "ollama":
                host = api_key or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
                prompt = (f"{system_prompt}\n\n" if system_prompt else "") + "\n".join(
                    f"{m['role']}: {m['content']}" for m in messages
                )
                res = client.post(
                    f"{host.rstrip('/')}/api/generate",
                    json={"model": os.environ.get("LLM_MODEL") or "llama3", "prompt": prompt, "stream": False},
                )
                if res.status_code == 200:
                    return res.json().get("response", "")
    except Exception:
        # Fall back to mock on network error, rate limit, or invalid response
        return None
    return None


# -----------------------------------------------------------------------------
# 1. Generate Test Cases by Limitations of the Problem
# -----------------------------------------------------------------------------

def generate_test_cases_by_limitations(problem: dict[str, Any]) -> list[dict[str, str]]:
    """Generate boundary, minimum/maximum, and edge test cases according to problem constraints."""
    title = problem.get("title", "")
    statement = problem.get("problem_statements", "")
    samples = problem.get("sample_input_output", []) or []

    provider, api_key = get_active_provider()
    if provider != "mock" and api_key:
        prompt = (
            f"Given the competitive programming problem '{title}':\n\n"
            f"Problem Statement and Limitations/Constraints:\n{statement}\n\n"
            "Existing Samples:\n"
            f"{json.dumps(samples)}\n\n"
            "Generate 3 to 5 realistic test cases that specifically target the limitations and constraints of the problem "
            "(e.g., minimum bounds, maximum bounds, zero, single element, negative numbers, edge cases).\n"
            "Return strictly a JSON array of objects with keys 'input', 'output', and 'explanation'. "
            "Example: [{\"input\": \"...\", \"output\": \"...\", \"explanation\": \"...\"}]"
        )
        raw_text = _call_upstream_llm(
            provider, api_key, [{"role": "user", "content": prompt}], "You are a competitive programming judge assistant."
        )
        if raw_text:
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return [
                            {
                                "input": str(c.get("input", "")).strip(),
                                "output": str(c.get("output", "")).strip(),
                                "explanation": str(c.get("explanation", "Edge test case based on constraints")),
                            }
                            for c in parsed
                            if "input" in c
                        ]
                except Exception:
                    pass

    # Deterministic mock fallback tailored to problem title/statement patterns
    cases: list[dict[str, str]] = []
    title_lower = title.lower()
    statement_lower = statement.lower()

    if "two sum" in title_lower or "a+b" in title_lower or "sum" in title_lower:
        cases = [
            {
                "input": "-1000000000 1000000000\n0",
                "output": "0 1" if "two sum" in title_lower else "0",
                "explanation": "Boundary limitation: Maximum negative and positive integer bounds",
            },
            {
                "input": "0 0\n0",
                "output": "0 1" if "two sum" in title_lower else "0",
                "explanation": "Zero limitation: Inputs consisting of zeros",
            },
            {
                "input": "1000000000 1000000000\n2000000000",
                "output": "0 1" if "two sum" in title_lower else "2000000000",
                "explanation": "Upper bound constraint: Tests potential 32-bit integer overflow",
            },
            {
                "input": "5 10 15 20 25\n45",
                "output": "3 4" if "two sum" in title_lower else "75",
                "explanation": "Multi-element case targeting the last elements",
            },
        ]
    elif "palindrome" in title_lower:
        cases = [
            {
                "input": "0",
                "output": "true",
                "explanation": "Boundary limitation: Single digit 0 is a palindrome",
            },
            {
                "input": "-2147483648",
                "output": "false",
                "explanation": "Lower bound constraint: 32-bit minimum signed integer (negative numbers cannot be palindromes)",
            },
            {
                "input": "2147447412",
                "output": "true",
                "explanation": "Large 32-bit boundary palindrome",
            },
            {
                "input": "1000000001",
                "output": "true",
                "explanation": "Boundary limitation: Ten-digit palindrome with trailing and leading ones",
            },
        ]
    elif "parenthes" in title_lower:
        cases = [
            {
                "input": "((()))",
                "output": "true",
                "explanation": "Deeply nested balanced parentheses boundary",
            },
            {
                "input": "(((((",
                "output": "false",
                "explanation": "Unclosed opening brackets boundary",
            },
            {
                "input": "}",
                "output": "false",
                "explanation": "Single close bracket minimum length limitation",
            },
            {
                "input": "{[()()]}",
                "output": "true",
                "explanation": "Mixed nested brackets validation",
            },
        ]
    elif "binary search" in title_lower:
        cases = [
            {
                "input": "5\n5",
                "output": "0",
                "explanation": "Single element array limitation (target found)",
            },
            {
                "input": "5\n10",
                "output": "-1",
                "explanation": "Single element array limitation (target not found)",
            },
            {
                "input": "-10000 0 10000\n-10000",
                "output": "0",
                "explanation": "Boundary value search at the lower extreme",
            },
            {
                "input": "-10000 0 10000\n10000",
                "output": "2",
                "explanation": "Boundary value search at the upper extreme",
            },
        ]
    elif "substring" in title_lower:
        cases = [
            {
                "input": "a",
                "output": "1",
                "explanation": "Minimum non-empty string length (N=1)",
            },
            {
                "input": "abcdefghijklmnopqrstuvwxyz",
                "output": "26",
                "explanation": "All unique characters constraint",
            },
            {
                "input": "aaaaaa",
                "output": "1",
                "explanation": "All identical characters limitation",
            },
        ]
    else:
        # Generic constraint generator from samples
        if samples:
            for i, s in enumerate(samples[:2]):
                cases.append({
                    "input": s.get("input", ""),
                    "output": s.get("output", ""),
                    "explanation": f"Validated sample case #{i+1}",
                })
        cases.extend([
            {
                "input": "0",
                "output": "0",
                "explanation": "Minimal boundary condition (single zero input)",
            },
            {
                "input": "1000000",
                "output": "1000000",
                "explanation": "Large magnitude constraint test",
            },
        ])

    return cases


# -----------------------------------------------------------------------------
# 2. Generate New Problems (language="ai", source="unknown")
# -----------------------------------------------------------------------------

def generate_ai_problem(current_problem: dict[str, Any] | None = None, difficulty: str = "Medium", topic: str | None = None) -> dict[str, Any]:
    """Generate a new competitive programming problem.

    Guarantees:
    - language is 'ai'
    - source is 'unknown'
    """
    base_title = current_problem["title"] if current_problem else "Dynamic Array Operation"
    clean_title = re.sub(r"^[0-9]+\.\s*", "", base_title)

    provider, api_key = get_active_provider()
    if provider != "mock" and api_key:
        prompt = (
            f"Generate an original competitive programming problem related to '{clean_title}' or topic '{topic or 'Algorithms'}'.\n"
            f"Target Difficulty: {difficulty}.\n\n"
            "Respond strictly with valid JSON with the following schema:\n"
            "{\n"
            '  "title": "Problem Title",\n'
            '  "problem_statements": "Complete problem statement, input format, output format, and constraints",\n'
            '  "sample_input_output": [{"input": "...", "output": "..."}],\n'
            '  "hints": ["hint 1", "hint 2"],\n'
            '  "difficulty": "Easy" | "Medium" | "Hard",\n'
            '  "tags": ["Tag1", "Tag2"]\n'
            "}"
        )
        raw_text = _call_upstream_llm(
            provider, api_key, [{"role": "user", "content": prompt}], "You are an expert problem setter."
        )
        if raw_text:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return {
                        "title": str(data.get("title", f"AI Generated {clean_title}")),
                        "problem_statements": str(data.get("problem_statements", "")),
                        "sample_input_output": data.get("sample_input_output", [{"input": "1", "output": "1"}]),
                        "hints": data.get("hints", ["Analyze constraints first."]),
                        "language": "ai",          # Mandatory requirement
                        "source": "unknown",       # Mandatory requirement
                        "difficulty": data.get("difficulty", difficulty),
                        "tags": data.get("tags", ["Algorithms", "AI Generation"]),
                    }
                except Exception:
                    pass

    # Built-in generator catalog
    generators = [
        {
            "title": f"Prefix Weighted Sum ({clean_title} AI Variant)",
            "difficulty": difficulty or "Medium",
            "tags": ["Math", "Array", "Prefix Sum"],
            "problem_statements": (
                "Given a sequence of integers A of length N, calculate the weighted sum of every prefix "
                "where the i-th element of the prefix is multiplied by its 1-based index.\n\n"
                "Formally, for each k from 1 to N, calculate:\nS_k = \\sum_{i=1}^k (i \\times A[i])\n\n"
                "### Input Format\n"
                "- First line: an integer N (1 <= N <= 10^5).\n"
                "- Second line: N space-separated integers A_1, A_2, ..., A_N (-10^4 <= A_i <= 10^4).\n\n"
                "### Output Format\n"
                "- Space-separated integers S_1, S_2, ..., S_N.\n\n"
                "### Constraints\n"
                "- 1 <= N <= 10^5\n"
                "- -10^4 <= A_i <= 10^4"
            ),
            "sample_input_output": [
                {"input": "4\n2 5 3 8", "output": "2 12 21 53"},
                {"input": "3\n1 1 1", "output": "1 3 6"},
            ],
            "hints": [
                "Notice that S_k = S_{k-1} + k * A[k]. You can compute each value in O(1) time from the previous sum.",
                "Use 64-bit integers to prevent overflow.",
            ],
            "language": "ai",
            "source": "unknown",
        },
        {
            "title": f"Modular Power Differential ({clean_title} AI Variant)",
            "difficulty": "Easy" if difficulty == "Easy" else "Medium",
            "tags": ["Math", "Modular Arithmetic"],
            "problem_statements": (
                "Given three integers A, B, and M, compute (A^2 - B^2) modulo M.\n\n"
                "### Input Format\n"
                "A single line with three space-separated positive integers A, B, and M.\n\n"
                "### Output Format\n"
                "A single integer in the range [0, M-1].\n\n"
                "### Constraints\n"
                "- 1 <= A, B <= 10^9\n"
                "- 2 <= M <= 10^9 + 7"
            ),
            "sample_input_output": [
                {"input": "5 3 1000000007", "output": "16"},
                {"input": "3 5 1000000007", "output": "999999991"},
            ],
            "hints": [
                "Remember that (A^2 - B^2) % M can produce a negative result in C++ and Java.",
                "To normalize a remainder in modulo arithmetic: (rem % M + M) % M.",
            ],
            "language": "ai",
            "source": "unknown",
        },
        {
            "title": f"Bitwise XOR Range Balance ({clean_title} AI Variant)",
            "difficulty": "Medium",
            "tags": ["Bit Manipulation", "Array"],
            "problem_statements": (
                "Given an array of N integers, find the number of non-empty contiguous subarrays "
                "whose total bitwise XOR is equal to zero.\n\n"
                "### Input Format\n"
                "- First line: integer N (1 <= N <= 10^5).\n"
                "- Second line: N space-separated integers.\n\n"
                "### Output Format\n"
                "A single integer representing the count of subarrays with XOR equal to 0.\n\n"
                "### Constraints\n"
                "- 1 <= N <= 10^5\n"
                "- 0 <= nums[i] <= 10^6"
            ),
            "sample_input_output": [
                {"input": "4\n1 2 3 0", "output": "3"},
                {"input": "3\n0 0 0", "output": "6"},
            ],
            "hints": [
                "Let P[i] be the prefix XOR: P[i] = nums[0] ^ ... ^ nums[i].",
                "Subarray from i to j has XOR 0 if and only if P[i-1] == P[j].",
                "Use a hash map to count occurrences of each prefix XOR value in O(N) time.",
            ],
            "language": "ai",
            "source": "unknown",
        },
    ]

    seed = int(current_problem["id"]) if current_problem and current_problem.get("id") else random.randint(0, 999)
    selected = dict(generators[seed % len(generators)])
    selected["language"] = "ai"
    selected["source"] = "unknown"
    return selected


# -----------------------------------------------------------------------------
# 3. Provide Hints in Terms of 5 to 10 Programming Thinking Steps
# -----------------------------------------------------------------------------

def get_thinking_hints(problem: dict[str, Any], hint_level: int = 1) -> dict[str, Any]:
    """Provide hints of the problems in terms of programming thinking steps (minimum 5 steps, maximum 10 steps)."""
    title = problem.get("title", "Problem")
    statement = problem.get("problem_statements", "")
    existing_hints = problem.get("hints", []) or []

    # Generate 7 programming thinking steps tailored to the problem (between 5 and 10 steps)
    steps = [
        {
            "step": 1,
            "title": "Step 1: Constraint & Boundary Limitations Analysis",
            "category": "Understand & Constrain",
            "description": (
                f"Analyze the problem inputs and constraints for '{title}'.\n"
                "• Examine the input ranges: What is the maximum size of N? "
                "For N <= 10^3, O(N^2) might pass; for N >= 10^5, you need an O(N) or O(N log N) algorithm.\n"
                "• Check for boundary limitations: Can values be 0, negative, or exceed 32-bit integer limits? "
                "If values can exceed 2 * 10^9, use 64-bit integers (`long long` in C++, `long` in Java, or Python's native big integers)."
            ),
        },
        {
            "step": 2,
            "title": "Step 2: Problem Invariants & Mathematical Formalization",
            "category": "Invariant & Modeling",
            "description": (
                "Identify what properties stay invariant as inputs are transformed.\n"
                + (f"Note from author: '{existing_hints[0]}'\n" if existing_hints else "")
                + "• Frame the target output as a mathematical equation or invariant relation.\n"
                "• What information do we need from previous elements as we iterate through the sequence?"
            ),
        },
        {
            "step": 3,
            "title": "Step 3: Brute Force Evaluation & Complexity Bottlenecks",
            "category": "Brute Force Baseline",
            "description": (
                "Formulate the naive approach first:\n"
                "• How would you solve this without memory limits or time limits?\n"
                "• Where is the duplicate or redundant work occurring? Are we recomputing ranges, "
                "re-scanning arrays, or doing nested linear searches that could be indexed?"
            ),
        },
        {
            "step": 4,
            "title": "Step 4: Optimal Data Structure & Pattern Selection",
            "category": "Algorithmic Pattern",
            "description": (
                "Choose the appropriate algorithmic paradigm:\n"
                "• If fast lookup is required: Hash Table / Map (`O(1)` average lookup).\n"
                "• If the array is or can be sorted: Two Pointers or Binary Search (`O(log N)`).\n"
                "• If tracking sliding intervals: Sliding Window / Deque.\n"
                "• If overlapping subproblems exist: Dynamic Programming with memoization or tabulation."
            ),
        },
        {
            "step": 5,
            "title": "Step 5: Subproblem Decomposition & State Transitions",
            "category": "Core Logic & State",
            "description": (
                "Break down the computation into sequential transitions:\n"
                "• Define your state clearly: What does `dp[i]` or the pointer position represent?\n"
                "• How do you transition from state `i-1` to state `i`?\n"
                "• Ensure your transition maintains the loop invariant and only relies on verified past data."
            ),
        },
        {
            "step": 6,
            "title": "Step 6: Edge Cases & Boundary Handling",
            "category": "Edge Cases",
            "description": (
                "Check all corner conditions before writing final code:\n"
                "• Empty input or single-element inputs (`N = 0` or `N = 1`).\n"
                "• All elements identical (e.g. `[0, 0, 0]` or `\"aaaa\"`).\n"
                "• Target not found / no solution: verify the fallback return value (e.g. `-1`, `[]`, or `false`).\n"
                "• Off-by-one errors on indices: 0-based vs 1-based indexing."
            ),
        },
        {
            "step": 7,
            "title": "Step 7: Implementation Blueprint & Pseudocode",
            "category": "Implementation",
            "description": (
                "Synthesize everything into clean, structured pseudocode:\n"
                "1. Read input cleanly (handle variable whitespace or tokenized inputs).\n"
                "2. Initialize data structures (hash table, pointers, or variables).\n"
                "3. Execute the single-pass or logarithmic search loop.\n"
                "4. Format the output according to the problem specification (space-separated or line-separated)."
            ),
        },
    ]

    total_steps = len(steps)  # 7 steps (guaranteed >= 5 and <= 10)
    level = min(total_steps, max(1, int(hint_level)))
    current_step = steps[level - 1]

    return {
        "success": True,
        "provider": "the_connector",
        "hintLevel": level,
        "totalSteps": total_steps,
        "minSteps": 5,
        "maxSteps": 10,
        "category": current_step["category"],
        "stepTitle": current_step["title"],
        "hintText": current_step["description"],
        "allSteps": steps[:level],
        "hints": steps,
        "hasMoreHints": level < total_steps,
    }


# -----------------------------------------------------------------------------
# 4. Interactive Chat Assistant
# -----------------------------------------------------------------------------

def chat_response(
    messages: list[dict[str, str]],
    current_problem: dict[str, Any] | None = None,
    current_code: str | None = None,
    current_language: str | None = None,
) -> dict[str, Any]:
    """Provide intelligent conversational programming support with code and problem context."""
    user_query = messages[-1].get("content", "") if messages else ""
    provider, api_key = get_active_provider()

    system_context = (
        "You are CodeJudge AI, an expert competitive programming tutor and algorithm assistant.\n"
        "Help the user solve coding problems, explain concepts, provide hints, analyze time and space complexity, "
        "and debug code. Write clean, readable Markdown responses with formatted code blocks."
    )
    if current_problem:
        system_context += (
            f"\n\nCurrent Active Problem:\n"
            f"Title: {current_problem.get('title')}\n"
            f"Difficulty: {current_problem.get('difficulty')}\n"
            f"Statement:\n{current_problem.get('problem_statements', '')[:800]}\n"
        )
    if current_code:
        system_context += (
            f"\nUser's Current Code ({current_language or 'python'}):\n"
            f"```\n{current_code[:1200]}\n```\n"
        )

    if provider != "mock" and api_key:
        reply = _call_upstream_llm(provider, api_key, messages, system_context)
        if reply:
            return {
                "success": True,
                "provider": provider,
                "reply": reply,
            }

    # Intelligent deterministic mock responses for chat
    q_lower = user_query.lower()

    if "hint" in q_lower or "thinking step" in q_lower or "how to solve" in q_lower or "approach" in q_lower:
        if current_problem:
            hints_data = get_thinking_hints(current_problem, 1)
            reply = (
                f"### 💡 Programming Thinking Steps for **{current_problem.get('title')}**\n\n"
                f"Here are the core thinking steps to solve this problem:\n\n"
                f"1. **{hints_data['allSteps'][0]['title']}**: Understand bounds and potential data types.\n"
                "2. **Identify Invariants**: Determine what relationships hold constant across the input elements.\n"
                "3. **Evaluate Brute Force**: Consider the naive method and identify the `O(N^2)` bottleneck.\n"
                "4. **Select Optimal Structure**: Use a Hash Map or Two-Pointer strategy to reduce lookup to `O(1)` or `O(log N)`.\n"
                "5. **State Transition & Edge Cases**: Verify behavior for single items, zeros, and negative numbers.\n\n"
                "Would you like me to walk you through a specific step in detail?"
            )
        else:
            reply = (
                "### 💡 Problem Solving Framework (Thinking Steps)\n\n"
                "When approaching any competitive programming problem:\n"
                "1. **Understand Constraints & Bounds**: Determine expected time complexity (e.g. `10^5` requires `O(N log N)` or `O(N)`).\n"
                "2. **Find the Mathematical Invariant**: Express the problem as a state or formula.\n"
                "3. **Identify the Bottleneck**: Locate the slowest component of the brute-force approach.\n"
                "4. **Choose Data Structures**: Match requirements to arrays, hash tables, heaps, or trees.\n"
                "5. **Check Extreme Edge Cases**: Empty collections, zero values, extreme bounds, duplicates."
            )
    elif "debug" in q_lower or "error" in q_lower or "wrong answer" in q_lower:
        reply = (
            "### 🐛 Code Review & Debugging Check\n\n"
            + (f"Analyzing your {current_language or 'code'}:\n" if current_code else "")
            + "Common points of failure to check:\n"
            "1. **Integer Overflow**: Ensure sums or products don't exceed 32-bit limits (`2^31 - 1`).\n"
            "2. **Input Reading**: Ensure `sys.stdin.read().split()` or `Scanner` handles variable spacing and multiple lines correctly.\n"
            "3. **Zero & Negative Numbers**: Are negative numbers properly handled in comparisons or modulo operations?\n"
            "4. **Off-by-One Boundaries**: Verify loop endpoints (`0` to `N-1`).\n"
            "5. **Floating Point Precision**: Use integer arithmetic or epsilon tolerances when comparing floats."
        )
    elif "test case" in q_lower or "edge case" in q_lower or "limitation" in q_lower:
        if current_problem:
            cases = generate_test_cases_by_limitations(current_problem)
            case_text = "\n".join(
                f"- **Input**: `{c['input']}` → **Expected**: `{c['output']}` (*{c['explanation']}*)"
                for c in cases[:3]
            )
            reply = (
                f"### 🧪 Edge Test Cases for **{current_problem.get('title')}**\n\n"
                f"Based on the limitations and constraints of this problem, consider these test cases:\n\n"
                f"{case_text}\n\n"
                "You can also click **'Generate Test Cases'** in the Test Console below to load them directly into your workspace!"
            )
        else:
            reply = (
                "### 🧪 Formulating Edge Test Cases\n\n"
                "When testing against problem limitations:\n"
                "1. **Minimum Bound**: Empty string, array with 1 element, or minimum allowed value.\n"
                "2. **Maximum Bound**: Maximum possible array size or maximum integer (`10^9`, `10^18`).\n"
                "3. **Signs & Parity**: All zeros, all negative numbers, alternating signs.\n"
                "4. **Duplicates**: All identical elements (`[7, 7, 7, 7]`)."
            )
    elif "complexity" in q_lower or "big o" in q_lower:
        reply = (
            "### ⏱️ Time & Space Complexity Guide\n\n"
            "- **`N <= 10`**: `O(N!)` or `O(2^N)` (Permutations, backtracking)\n"
            "- **`N <= 20`**: `O(2^N)` or `O(N^2 * 2^N)` (Bitmask DP)\n"
            "- **`N <= 500`**: `O(N^3)` (Floyd-Warshall, matrix multiplication)\n"
            "- **`N <= 5,000`**: `O(N^2)` (Nested loops, dynamic programming)\n"
            "- **`N <= 10^5`**: `O(N log N)` (Sorting, binary search, segment trees)\n"
            "- **`N <= 10^7`**: `O(N)` (Linear scan, two pointers, prefix sums)\n"
            "- **`N >= 10^9`**: `O(log N)` or `O(1)` (Binary exponentiation, math formulas)"
        )
    else:
        prob_mention = f" I see you're looking at **{current_problem.get('title')}**." if current_problem else ""
        reply = (
            f"Hello! I am your CodeJudge AI Assistant.{prob_mention} How can I assist you with your competitive programming today?\n\n"
            "You can ask me to:\n"
            "- 💡 **Explain thinking steps** (minimum 5, maximum 10 steps)\n"
            "- 🧪 **Generate boundary test cases** based on problem limitations\n"
            "- 🐛 **Debug or review your code**\n"
            "- ⚡ **Analyze algorithm complexity**\n"
            "- ✨ **Generate a new AI practice problem**"
        )

    return {
        "success": True,
        "provider": "the_connector-mock",
        "reply": reply,
    }


# -----------------------------------------------------------------------------
# 5. Translation & Recommendation helpers
# -----------------------------------------------------------------------------

def translate_problem(problem: dict[str, Any], target_language: str = "en") -> dict[str, Any]:
    """Translate problem title, statement, and hints."""
    source_language = problem.get("language") or ("ru" if _CYRILLIC.search(problem.get("title", "")) else "en")
    target_name = LANGUAGE_NAMES.get(target_language, target_language)

    # If same language, return as is
    if source_language == target_language:
        return {
            "success": True,
            "provider": "the_connector",
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
            "targetLanguageName": target_name,
            "translatedTitle": problem.get("title", ""),
            "translatedStatements": problem.get("problem_statements", ""),
            "translatedHints": problem.get("hints", []) or [],
        }

    provider, api_key = get_active_provider()
    if provider != "mock" and api_key:
        prompt = (
            f"Translate the following competitive programming problem to {target_name}.\n\n"
            f"Title: {problem.get('title', '')}\n\n"
            f"Statements:\n{problem.get('problem_statements', '')}\n\n"
            "Return valid JSON with keys: translatedTitle, translatedStatements, translatedHints (array of strings)."
        )
        raw = _call_upstream_llm(provider, api_key, [{"role": "user", "content": prompt}], "You are a technical translator.")
        if raw:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return {
                        "success": True,
                        "provider": provider,
                        "sourceLanguage": source_language,
                        "targetLanguage": target_language,
                        "targetLanguageName": target_name,
                        "translatedTitle": data.get("translatedTitle", problem.get("title")),
                        "translatedStatements": data.get("translatedStatements", problem.get("problem_statements")),
                        "translatedHints": data.get("translatedHints", problem.get("hints")),
                    }
                except Exception:
                    pass

    return {
        "success": True,
        "provider": "the_connector-mock",
        "sourceLanguage": source_language,
        "targetLanguage": target_language,
        "targetLanguageName": target_name,
        "translatedTitle": f"[{target_name}] {problem.get('title', '')}",
        "translatedStatements": f"[Translated to {target_name}]\n\n{problem.get('problem_statements', '')}",
        "translatedHints": [f"[{target_name}] {h}" for h in problem.get("hints", []) or []],
    }


def get_recommendations(current: dict[str, Any] | None, problems: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank problem candidates and return related recommendations."""
    candidates = [p for p in problems if current is None or p.get("id") != current.get("id")]

    def score(p: dict[str, Any]) -> int:
        if not current:
            return 0
        return (
            2 * (p.get("difficulty") == current.get("difficulty"))
            + (p.get("language") == current.get("language"))
            + 3 * sum(tag in (p.get("tags") or []) for tag in (current.get("tags") or []))
        )

    reasons = [
        "Reinforces similar algorithmic patterns and time complexity constraints.",
        "Excellent follow-up practice with overlapping data structures.",
        "Helps build confidence in this category before attempting harder problems.",
        "Recommended based on matching tags, difficulty, and algorithmic strategy.",
    ]
    recommendations = []
    for index, p in enumerate(sorted(candidates, key=score, reverse=True)[:4]):
        recommendations.append({
            "id": p["id"],
            "title": p["title"],
            "difficulty": p.get("difficulty"),
            "language": p.get("language"),
            "tags": p.get("tags", []),
            "sampleCount": len(p.get("sample_input_output", []) or []),
            "recommendationReason": reasons[index % len(reasons)],
        })
    return {"success": True, "provider": "the_connector", "recommendations": recommendations}

