"""Flask API and frontend host for CodeJudge. Start with `python -m backend.app`."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException, NotFound, RequestEntityTooLarge

from .db import Database, bounded_int
from .executor import run_code, submit_code, validate_test_cases
from .jobs import SubmissionJobs, SubmissionQueueFull
from .llm import (
    LLMError,
    chat_response,
    generate_ai_problem,
    generate_problem_tags,
    generate_test_cases_by_limitations,
    get_recommendations,
    get_model_info,
    get_thinking_hints,
    translate_problem,
)
from .paths import ROOT, default_database_path, default_storage_path, legacy_archive_database_path
from .runtimes import available_languages
from .seed import seed_database
from .storage import DraftConflict, DraftProblemNotFound, DraftStore, export_submissions
from .audio import AudioError, AudioQueueFull, AudioStore

backend_logger = logging.getLogger('uvicorn.error')


def env_opt_in(name: str) -> bool:
    """Enable data-populating startup behavior only by explicit opt-in."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def json_object() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def normalize_samples(samples: Any) -> list[dict[str, str]]:
    if not isinstance(samples, list):
        raise ValueError("Sample test cases must be an array.")
    normalized = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("Each sample must contain input and output strings.")
        if any(key not in sample or not isinstance(sample[key], str) for key in ("input", "output")):
            raise ValueError("Each sample must contain input and expected output strings; empty strings are allowed.")
        item = {key: sample[key] for key in ("input", "output")}
        normalized.append(item)
    return normalized


def normalize_problem(value: Any, require_content: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Each problem must be a JSON object.")
    title = value.get("title") or ("Untitled Problem" if not require_content else "")
    statement = value.get("problem_statements") or value.get("description") or ""
    if not isinstance(title, str) or not isinstance(statement, str):
        raise ValueError("Title and problem_statements must be strings.")
    if require_content and (not title.strip() or not statement.strip()):
        raise ValueError("Title and problem_statements are required.")

    result: dict[str, Any] = dict(title=title, problem_statements=statement)
    source = value.get("source")
    if source is not None and not isinstance(source, str):
        raise ValueError("source must be a string or null.")
    result["source"] = (source.strip() or None) if source is not None else None

    for field, default in (
        ("sample_input_output", value.get("samples", [])),
        ("hints", []),
        ("tags", []),
    ):
        items = value.get(field, default)
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = [items]
        if field == "sample_input_output":
            items = normalize_samples(items)
        elif not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise ValueError(f"{field} must be an array of strings.")
        result[field] = items

    for field, default in (("language", "en"), ("difficulty", "Medium")):
        result[field] = value.get(field) or default
        if not isinstance(result[field], str):
            raise ValueError(f"{field} must be a string.")
    return result


def validate_code(data: dict) -> None:
    if data.get("language") not in ("python", "cpp", "java"):
        raise ValueError("Language must be python, cpp, or java.")
    if not isinstance(data.get("code"), str) or not data["code"].strip():
        raise ValueError("Code is required.")


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    try:
        max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", "256"))
        if max_upload_mb <= 0:
            raise ValueError
    except ValueError as error:
        raise ValueError("MAX_UPLOAD_MB must be a positive integer (in MiB).") from error

    app.config.from_mapping(
        DATABASE_PATH=os.environ.get("DATABASE_PATH") or os.environ.get("DB_PATH") or str(default_database_path()),
        AUTO_SEED=env_opt_in("AUTO_SEED"),
        SEED_PATH=str(ROOT / "problem.json"),
        CLIENT_DIST=str(ROOT / "frontend" / "dist"),
        MAX_CONTENT_LENGTH=max_upload_mb * 1024 * 1024,
        SUBMISSION_WORKERS=2,
        SUBMISSION_MAX_PENDING=16,
        WORKSPACE_STORAGE_DIR=os.environ.get("WORKSPACE_STORAGE_DIR") or None,
        CONNECTOR_BASE_URL=os.environ.get("CONNECTOR_BASE_URL", "http://127.0.0.1:8301/v1"),
        CONNECTOR_SPEECH_TIMEOUT_SECONDS=os.environ.get("CONNECTOR_SPEECH_TIMEOUT_SECONDS", "180"),
    )
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False

    database = Database(app.config["DATABASE_PATH"])
    is_new_database = database.initialize()
    if is_new_database and app.config["AUTO_SEED"]:
        seed_database(database, app.config["SEED_PATH"])
    app.extensions["database"] = database
    jobs = SubmissionJobs(
        database,
        max_workers=app.config["SUBMISSION_WORKERS"],
        max_pending=app.config["SUBMISSION_MAX_PENDING"],
    )
    app.extensions["submission_jobs"] = jobs
    storage_root = Path(app.config["WORKSPACE_STORAGE_DIR"] or default_storage_path(app.config["DATABASE_PATH"]))
    app.config["WORKSPACE_STORAGE_DIR"] = str(storage_root)
    drafts = DraftStore(database, storage_root / "drafts")
    audio = AudioStore(
        storage_root / "audio",
        base_url=app.config["CONNECTOR_BASE_URL"],
        timeout_seconds=float(app.config["CONNECTOR_SPEECH_TIMEOUT_SECONDS"]),
    )
    app.extensions["draft_store"] = drafts
    app.extensions["audio_store"] = audio

    mutation_lock = threading.RLock()
    app.extensions["mutation_lock"] = mutation_lock
    tag_generation_lock = threading.Lock()

    def find_problem(problem_id: Any) -> dict:
        if not isinstance(problem_id, (int, str)) or isinstance(problem_id, bool):
            raise ValueError("A valid problemId is required.")
        problem = database.get_problem(problem_id)
        if problem is None:
            raise NotFound("Problem not found.")
        return problem

    def ensure_problem_story(problem: dict) -> dict | None:
        """Keep archive creation and story creation linked in the unified app."""
        try:
            from .jira.db import db as jira_database
            from .jira.services.issues import ensure_story_for_problem
            if (
                jira_database.path == ':memory:'
                or Path(jira_database.path).resolve() != database.path.resolve()
            ):
                return None
            return ensure_story_for_problem(problem["id"])
        except Exception as error:
            # Standalone Flask tests intentionally do not initialize the Jira
            # schema. In the unified server a missing link is an actual error.
            if "no such table" in str(error).lower() or "project is required" in str(error).lower():
                return None
            raise

    def backfill_problem_stories() -> int:
        """Link imported problems only when this Flask app shares Jira's database."""
        try:
            from .jira.db import db as jira_database
            from .jira.services.issues import backfill_archive_story_links
            if (
                jira_database.path == ':memory:'
                or Path(jira_database.path).resolve() != database.path.resolve()
            ):
                return 0
            return backfill_archive_story_links()
        except Exception as error:
            if "no such table" in str(error).lower() or "project is required" in str(error).lower():
                return 0
            raise

    # CORS support
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.route("/api/<path:_path>", methods=["OPTIONS"])
    def cors_options(_path):
        return "", 204

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(success=False, error=error.description), error.code

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(error):
        limit = app.config["MAX_CONTENT_LENGTH"]
        message = (
            f"Request too large. Maximum request size is {limit / (1024 * 1024):g} MiB "
            "(including upload overhead)."
        ) if limit else error.description
        return jsonify(success=False, error=message), 413

    @app.errorhandler(ValueError)
    def invalid_request(error):
        return jsonify(success=False, error=str(error)), 400

    @app.errorhandler(DraftConflict)
    def draft_conflict(error):
        return jsonify(success=False, error=str(error), draft=error.current), 409

    @app.errorhandler(DraftProblemNotFound)
    def draft_problem_missing(error):
        return jsonify(success=False, error="Problem not found."), 404

    @app.errorhandler(LLMError)
    def llm_error(error):
        return jsonify(success=False, error=str(error)), error.status_code

    @app.errorhandler(SubmissionQueueFull)
    def judge_busy(error):
        return jsonify(success=False, error=str(error)), 503, {"Retry-After": "2"}

    @app.errorhandler(AudioQueueFull)
    def audio_busy(error):
        return jsonify(success=False, error=str(error)), 429, {"Retry-After": "2"}

    @app.errorhandler(AudioError)
    def audio_error(error):
        return jsonify(success=False, error=str(error)), 503

    @app.errorhandler(Exception)
    def server_error(error):
        app.logger.exception("Request failed")
        return jsonify(success=False, error="Internal server error."), 500

    @app.get("/api/health")
    def health():
        return jsonify(
            status="ok",
            timestamp=datetime.now(timezone.utc).isoformat(),
            totalProblems=database.count(),
        )

    @app.get("/api/languages")
    def languages():
        return jsonify(success=True, languages=available_languages())

    @app.get("/api/llm/models")
    def llm_models():
        return jsonify(get_model_info(request.args.get("model")))

    @app.get("/api/problems")
    def list_problems():
        arguments = {
            key: request.args[key]
            for key in ("page", "limit", "search", "language", "difficulty", "solved")
            if key in request.args
        }
        return jsonify(success=True, **database.get_problems(**arguments))

    @app.get("/api/problems/stats")
    def statistics():
        return jsonify(success=True, totalProblems=database.count())

    @app.get("/api/problems/<int:problem_id>")
    def problem_detail(problem_id: int):
        return jsonify(success=True, problem=find_problem(problem_id))

    @app.get("/api/problems/<int:problem_id>/drafts/<string:language>")
    def read_draft(problem_id: int, language: str):
        return jsonify(success=True, draft=drafts.get(problem_id, language))

    @app.put("/api/problems/<int:problem_id>/drafts/<string:language>")
    def save_draft(problem_id: int, language: str):
        data = json_object()
        with mutation_lock:
            draft = drafts.save(problem_id, language, data.get("code"), data.get("revision"))
        return jsonify(success=True, draft=draft)

    def audio_response(result: dict, problem_id: int | None = None):
        if problem_id is not None:
            database.save_audio_asset(problem_id, result)
        if result["status"] == "ready":
            result = {**result, "url": f'/api/audio/{result["key"]}.mp3'}
        return jsonify(success=True, audio=result)

    @app.get("/api/problems/<int:problem_id>/audio")
    def read_problem_audio(problem_id: int):
        return audio_response(audio.get(find_problem(problem_id)), problem_id)

    @app.post("/api/problems/<int:problem_id>/audio")
    def generate_problem_audio(problem_id: int):
        result = audio.start(find_problem(problem_id))
        return audio_response(result, problem_id), (200 if result["status"] == "ready" else 202)

    @app.post("/api/audio/responses")
    def generate_response_audio():
        data = json_object()
        result = audio.start_text(data.get("text"), language=data.get("language", "en"))
        return audio_response(result), (200 if result["status"] == "ready" else 202)

    @app.get("/api/audio/responses/<string:key>")
    def read_response_audio(key: str):
        return audio_response(audio.get_by_key(key))

    @app.get("/api/audio/cache")
    def audio_cache_info():
        return jsonify(success=True, cache=audio.cache_info())

    @app.delete("/api/audio/cache")
    def clear_audio_cache():
        return jsonify(success=True, cache=audio.clear_cache())

    @app.get("/api/audio/<string:key>.mp3")
    def audio_file(key: str):
        path = audio.path_for(key)
        if path is None:
            raise NotFound("Audio file not found.")
        # Revalidate the file so clearing saved narration also invalidates old
        # player URLs while preserving range requests and conditional responses.
        try:
            return send_file(path, mimetype="audio/mpeg", conditional=True, max_age=0)
        except FileNotFoundError as error:
            # Cleanup may remove the file after path_for checks it.
            raise NotFound("Audio file not found.") from error

    @app.post("/api/problems")
    def create_problem():
        problem = normalize_problem(json_object(), require_content=True)
        with mutation_lock:
            created = database.create_problem(problem)
            story = ensure_problem_story(created)
        return jsonify(success=True, problem=database.get_problem(created["id"]), story=story,
                       message="Problem and linked story successfully saved to database!")

    @app.post("/api/problems/upload")
    def upload_problems():
        backend_logger.info('Problem archive import request received; parsing JSON upload')
        if "file" in request.files:
            try:
                parsed = json.loads(request.files["file"].read().decode("utf-8-sig"))
            except (UnicodeError, ValueError) as error:
                raise ValueError("Upload must be a valid UTF-8 JSON file.") from error
        else:
            parsed = request.get_json(silent=True)
        if isinstance(parsed, list):
            raw_problems = parsed
        elif isinstance(parsed, dict):
            raw_problems = parsed.get("problems", [parsed] if parsed.get("title") else [])
        else:
            raw_problems = None
        if not isinstance(raw_problems, list) or not raw_problems:
            raise ValueError("Expected a non-empty array of problems or an object with a problems array.")
        backend_logger.info('Problem archive JSON parsed: %d entries', len(raw_problems))
        problems = []
        for index, raw_problem in enumerate(raw_problems, start=1):
            title = raw_problem.get('title') if isinstance(raw_problem, dict) else '<non-object entry>'
            log_title = ' '.join(str(title or 'Untitled Problem').split())[:160]
            backend_logger.info(
                'Problem archive processing entry %d/%d: %s',
                index,
                len(raw_problems),
                log_title,
            )
            problems.append(normalize_problem(raw_problem))
        with mutation_lock:
            backend_logger.info('Problem archive writing %d entries to SQLite', len(problems))
            inserted = database.bulk_insert(problems)
            backend_logger.info('Problem archive linking imported problems to stories')
            linked_stories = backfill_problem_stories()
            total = database.count()
        backend_logger.info(
            'Problem archive import complete: %d inserted, %d stories linked',
            inserted,
            linked_stories,
        )
        return jsonify(
            success=True,
            insertedCount=inserted,
            linkedStories=linked_stories,
            totalNow=total,
            message=f"Successfully imported and persisted {inserted} problems to the database!",
        )

    @app.delete("/api/database")
    def clear_database():
        with mutation_lock:
            counts = database.clear()
        return jsonify(
            success=True,
            **counts,
            message="All problems, draft references, and submission history have been deleted.",
        )

    @app.post("/api/run")
    def run():
        data = json_object()
        validate_code(data)
        input_text, expected = data.get("input", ""), data.get("expectedOutput")
        if not isinstance(input_text, str) or (expected is not None and not isinstance(expected, str)):
            raise ValueError("Input and expectedOutput must be strings.")
        result = run_code(
            data["language"],
            data["code"],
            input_text,
            expected,
            bounded_int(data.get("timeoutMs"), 5000, minimum=500, maximum=10000),
        )
        return jsonify(success=True, result=result)

    @app.post("/api/submit")
    def submit():
        data = json_object()
        validate_code(data)
        custom_cases = data.get("customTestCases")
        if custom_cases is not None:
            custom_cases = normalize_samples(custom_cases)
        asynchronous = data.get("async", False)
        if not isinstance(asynchronous, bool):
            raise ValueError("async must be a boolean.")
        with mutation_lock:
            problem = find_problem(data.get("problemId"))
            test_cases = custom_cases if custom_cases is not None else problem["sample_input_output"]
            validate_test_cases(test_cases)
            if asynchronous:
                job = jobs.start(problem["id"], data["language"], data["code"], test_cases, 5000)
                return jsonify(success=True, **job), 202
            grading = submit_code(
                data["language"],
                data["code"],
                test_cases,
                5000,
            )
            results = grading.get("results", [])
            first = results[0] if results else {}
            submission = database.save_submission(
                dict(
                    problem_id=problem["id"],
                    language=data["language"],
                    code=data["code"],
                    status=grading["status"],
                    runtime_ms=grading["totalRuntimeMs"],
                    output=first.get("actualOutput", first.get("stdout", "")),
                    error=grading.get("error") or next((r["error"] for r in results if r.get("error")), ""),
                    test_results=results,
                )
            )
            try:
                from .jira.services.issues import update_coding_story_submission
                update_coding_story_submission(problem["id"], grading["status"], results)
            except Exception:
                pass
        return jsonify(success=True, submission=submission, grading=grading)


    @app.get("/api/submission-jobs/<string:job_id>")
    def submission_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise NotFound("Submission job not found.")
        return jsonify(success=True, **job)

    @app.get("/api/submissions/<int:problem_id>")
    def submission_history(problem_id: int):
        return jsonify(
            success=True,
            submissions=database.get_submissions(problem_id, request.args.get("limit", 20)),
        )

    @app.get("/api/submissions")
    def all_submissions():
        return jsonify(success=True, **database.list_submissions(
            page=request.args.get("page", 1),
            limit=request.args.get("limit", 20),
            problem_id=request.args.get("problemId"),
        ))

    @app.get("/api/submission-records/<int:submission_id>")
    def submission_detail(submission_id: int):
        submission = database.get_submission(submission_id)
        if submission is None:
            raise NotFound("Submission not found.")
        return jsonify(success=True, submission=submission)

    @app.get("/api/submissions/export.zip")
    def download_submissions():
        archive = export_submissions(database)
        return send_file(
            archive, mimetype="application/zip", as_attachment=True,
            download_name=f'codejudge-submissions-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip',
            max_age=0,
        )

    @app.post("/api/translate-problem")
    @app.post("/api/llm/translate-problem")
    def translate():
        data = json_object()
        problem = database.get_problem(data["problemId"]) if isinstance(data.get("problemId"), (int, str)) else None
        if problem is None:
            if data.get("title") and data.get("problem_statements"):
                problem = normalize_problem(data, require_content=True)
            else:
                problem = find_problem(data.get("problemId"))
        target = data.get("targetLanguage") or "en"
        if not isinstance(target, str):
            raise ValueError("targetLanguage must be a string.")
        result = translate_problem(problem, target, model=data.get("model"))
        if problem.get("id") is not None:
            database.save_translation(problem["id"], target, result)
        return jsonify(result)

    # Requirement (3): Provide hints in terms of 5-10 programming thinking steps
    @app.post("/api/llm/hint")
    @app.post("/api/hint")
    def hint():
        data = json_object()
        problem = find_problem(data.get("problemId"))
        hint_level = data.get("hintLevel", 1)
        result = get_thinking_hints(problem, hint_level, model=data.get("model"))
        database.save_solution_trace(problem["id"], result)
        return jsonify(result)

    @app.post("/api/llm/recommendations")
    @app.post("/api/recommendations")
    def recommendations():
        data = json_object()
        current = find_problem(data["problemId"]) if data.get("problemId") else None
        return jsonify(get_recommendations(current, database.get_problems(limit=100)["problems"]))

    @app.post("/api/llm/generate-tags")
    def generate_tags():
        data = json_object()
        problem_ids = data.get("problemIds")
        if (
            not isinstance(problem_ids, list)
            or not 1 <= len(problem_ids) <= 6
            or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in problem_ids)
            or len(set(problem_ids)) != len(problem_ids)
        ):
            raise ValueError("problemIds must contain 1 to 6 unique positive integers.")

        # Serialize tag batches so two overlapping screen loads cannot send the
        # same untagged problem to the AI before its first tag is persisted.
        with tag_generation_lock:
            problems = [find_problem(problem_id) for problem_id in problem_ids]
            untagged = [problem for problem in problems if not problem.get("tags")]
            generated_by_id = {}
            provider, used_model = "local", None
            if untagged:
                generated = generate_problem_tags(untagged, model=data.get("model"))
                generated_by_id = {item["problemId"]: item["tag"] for item in generated["tags"]}
                provider, used_model = generated["provider"], generated["model"]
                with mutation_lock:
                    for problem in untagged:
                        database.set_problem_tags_if_empty(
                            problem["id"], [generated_by_id[problem["id"]]],
                        )

            tagged = []
            for problem_id in problem_ids:
                current = find_problem(problem_id)
                tagged.append({"problemId": problem_id, "tags": current.get("tags") or []})
            return jsonify(success=True, provider=provider, model=used_model, tags=tagged)

    # Requirement (1): Generate test cases by the limitation of the problem
    @app.post("/api/llm/generate-testcases")
    def generate_testcases():
        data = json_object()
        problem = find_problem(data.get("problemId"))
        model_info = get_model_info(data.get("model"))
        cases = generate_test_cases_by_limitations(problem, model=model_info["model"])
        return jsonify(success=True, problemId=problem["id"], testCases=cases,
                       provider=model_info["provider"], model=model_info["model"])

    # Requirement (2): Generate new problems (language="ai", source="unknown") into database
    @app.post("/api/llm/generate-problem")
    @app.post("/api/llm/generate-similar")
    @app.post("/api/generate-similar")
    def generate_problem_endpoint():
        data = json_object()
        current = find_problem(data["problemId"]) if data.get("problemId") else None
        difficulty = data.get("difficulty") or (current.get("difficulty") if current else "Medium")
        auto_save = data.get("autoSave", True)
        if not isinstance(auto_save, bool):
            raise ValueError("autoSave must be a boolean.")
        model_info = get_model_info(data.get("model"))
        generated = generate_ai_problem(current, difficulty=difficulty, topic=data.get("topic"), model=model_info["model"])
        generated["language"] = "ai"
        generated["source"] = "unknown"
        saved = None
        if auto_save:
            with mutation_lock:
                saved = database.create_problem(normalize_problem(generated))
                ensure_problem_story(saved)
                saved = database.get_problem(saved["id"])
        return jsonify(
            success=True,
            provider=model_info["provider"],
            model=model_info["model"],
            generatedProblem=generated,
            savedProblem=saved,
        )

    # Chat functionality
    @app.post("/api/chat")
    def chat_endpoint():
        data = json_object()
        messages = data.get("messages", [])
        if not isinstance(messages, list) or not messages:
            message_text = data.get("message")
            if not message_text:
                raise ValueError("Message content is required.")
            messages = [{"role": "user", "content": message_text}]

        session_id = data.get("sessionId", "default")
        current_prob = database.get_problem(data["problemId"]) if data.get("problemId") else None
        code = data.get("code")
        language_selected = data.get("language")

        result = chat_response(messages, current_prob, code, language_selected, model=data.get("model"))
        # Persist messages in database
        database.save_chat_message("user", messages[-1]["content"], session_id)
        database.save_chat_message("assistant", result["reply"], session_id)

        return jsonify(result)

    @app.get("/api/chat/history")
    def chat_history_endpoint():
        session_id = request.args.get("sessionId", "default")
        history = database.get_chat_history(session_id)
        return jsonify(success=True, history=history)

    # Static frontend hosting for production
    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path == "api" or path.startswith("api/"):
            raise NotFound("API endpoint not found.")
        dist = Path(app.config["CLIENT_DIST"]).resolve()
        target = (dist / path).resolve()
        if not target.is_relative_to(dist):
            raise NotFound()
        if path and target.is_file():
            return send_from_directory(dist, path)
        if (dist / "index.html").is_file():
            return send_from_directory(dist, "index.html")
        raise NotFound("Frontend not built. Run npm run build or use the Vite development server.")

    return app


def create_unified_app(flask_config: dict | None = None):
    from .database_unification import copy_legacy_workspace, merge_legacy_databases
    from .jira.config import resolve_db_path
    from .jira.db import db as jira_database
    from .jira.main import app as jira_app, initialize_jira_data
    from a2wsgi import WSGIMiddleware

    requested_config = dict(flask_config or {})
    unified_path = Path(
        requested_config.get("DATABASE_PATH")
        or os.environ.get("DATABASE_PATH")
        or os.environ.get("DB_PATH")
        or default_database_path()
    ).resolve()
    auto_seed = requested_config.get(
        "AUTO_SEED",
        env_opt_in("AUTO_SEED"),
    )
    requested_config.update({"DATABASE_PATH": str(unified_path), "AUTO_SEED": False})
    flask_app = create_app(requested_config)
    if jira_database.path == ':memory:' or Path(jira_database.path).resolve() != unified_path:
        jira_database.reopen(str(unified_path))

    legacy_jira_path = Path(__file__).resolve().parent / 'data' / 'jira.db'
    should_migrate = requested_config.get(
        "MIGRATE_LEGACY_DATABASES",
        env_opt_in("MIGRATE_LEGACY_DATABASES"),
    )
    migrations = merge_legacy_databases(
        unified_path,
        [legacy_archive_database_path(), legacy_jira_path, resolve_db_path()],
    ) if should_migrate else {}
    if migrations:
        print(f"Unified database imported legacy data from: {', '.join(migrations)}")
        if not requested_config.get("WORKSPACE_STORAGE_DIR") and not os.environ.get("WORKSPACE_STORAGE_DIR"):
            target_workspace = Path(flask_app.config["WORKSPACE_STORAGE_DIR"])
            for source, copied_tables in migrations.items():
                if copied_tables.get('problems', 0):
                    copied_files = copy_legacy_workspace(
                        default_storage_path(source),
                        target_workspace,
                    )
                    if copied_files:
                        print(f"Unified workspace imported {copied_files} file(s) from legacy storage.")
    if auto_seed and flask_app.extensions["database"].count() == 0:
        seed_database(flask_app.extensions["database"], flask_app.config["SEED_PATH"])
    flask_app.config["AUTO_SEED"] = auto_seed
    initialize_jira_data()
    if requested_config.get("BACKFILL_PROBLEM_STORIES", True):
        from .jira.services.issues import (
            backfill_archive_story_links,
            backfill_coding_story_problem_links,
        )
        linked_problems = backfill_coding_story_problem_links()
        linked_stories = backfill_archive_story_links()
        if linked_problems or linked_stories:
            print(
                "Unified database repaired missing links: "
                f"{linked_problems} coding story problem(s), "
                f"{linked_stories} archive problem story/stories."
            )

    jira_app.state.archive_database = flask_app.extensions["database"]
    jira_app.state.archive_mutation_lock = flask_app.extensions["mutation_lock"]
    jira_app.state.archive_app = flask_app
    previous_mount = getattr(jira_app.state, "archive_mount", None)
    if previous_mount in jira_app.router.routes:
        jira_app.router.routes.remove(previous_mount)
    jira_app.mount("/", WSGIMiddleware(flask_app), name="archive")
    jira_app.state.archive_mount = jira_app.router.routes[-1]
    return jira_app


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Unified Competitive Programming & Jira Server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host to listen on")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "3001")), help="Port to listen on")
    args = parser.parse_args()

    unified_app = create_unified_app()
    uvicorn.run(unified_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
