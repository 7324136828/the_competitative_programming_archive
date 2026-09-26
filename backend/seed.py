"""Seed a new or empty problem bank explicitly with `python -m backend.seed`."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .db import Database
from .paths import ROOT, default_database_path


def infer_difficulty(title: str, statement: str) -> str:
    text = f"{title} {statement}".lower()
    if any(word in text for word in ("a+b", "two sum", "palindrome", "reverse root", "simple", "easy")):
        return "Easy"
    if len(statement) > 2500 or any(
        word in text for word in ("graph", "tree", "dynamic programming", "отжиг", "regular expression", "регулярн")
    ):
        return "Hard"
    return "Medium"


def infer_tags(title: str, statement: str) -> list[str]:
    text = f"{title} {statement}".lower()
    keywords = {
        "Math": ("math", "чисел", "квадрат", "сложить", "number"),
        "String": ("string", "строк", "слово", "regex", "регулярн"),
        "Array": ("array", "массив", "последовательност"),
        "Graph": ("graph", "граф", "vertex", "edge"),
        "Dynamic Programming": ("dynamic programming", "динамическ"),
        "Simulation": ("simulation", "моделирован", "игра", "game"),
    }
    return [tag for tag, words in keywords.items() if any(word in text for word in words)] or ["Algorithms"]


def seed_database(database: Database, source: Path | str = ROOT / "problem.json") -> int:
    if database.count():
        return 0
    source_path = Path(source)
    if not source_path.is_file():
        return 0
    parsed = json.loads(source_path.read_text(encoding="utf-8-sig"))
    problems = parsed if isinstance(parsed, list) else parsed.get("problems", [])
    enriched = []
    for problem in problems:
        title = problem.get("title") or "Untitled"
        statement = problem.get("problem_statements") or ""
        enriched.append({
            **problem,
            "title": title,
            "problem_statements": statement,
            "language": problem.get("language") or ("ru" if re.search("[а-яА-ЯёЁ]", title) else "en"),
            "difficulty": problem.get("difficulty") or infer_difficulty(title, statement),
            "tags": problem.get("tags") or infer_tags(title, statement),
        })
    return database.bulk_insert(enriched)


if __name__ == "__main__":
    db = Database(os.environ.get("DATABASE_PATH") or os.environ.get("DB_PATH") or default_database_path())
    db.initialize()
    inserted = seed_database(db)
    print(f"Seeded {inserted} problems. Database contains {db.count()} problems.")

