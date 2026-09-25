"""Bounded background judging with persisted status and final submission results.

Workers belong to one threaded backend process. Completed jobs survive a restart;
orphaned jobs are reported as interrupted and can be resubmitted. Multiple app
instances within the same process share the active registry; multiple backend
worker processes require an external queue and are not supported by this manager.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import logging
import threading
from uuid import uuid4

from .db import Database
from .executor import submit_code, validate_test_cases

logger = logging.getLogger(__name__)
_active_jobs: set[str] = set()
_active_lock = threading.Lock()


class SubmissionQueueFull(RuntimeError):
    """The bounded judge queue has no available capacity."""


class _RemovedJob(Exception):
    pass


class SubmissionJobs:
    def __init__(self, database: Database, max_workers: int = 2, max_pending: int = 16):
        self.database = database
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="judge")
        self._slots = threading.BoundedSemaphore(max(1, max_pending))
        self._lifecycle = threading.Lock()
        self._closed = False

    @staticmethod
    def _payload(submission: dict) -> dict:
        payload = {
            "jobId": submission["job_id"],
            "status": submission["status"],
            "phase": submission["phase"],
            "done": submission["phase"] == "completed",
            "submission": submission,
        }
        if submission.get("grading"):
            payload["grading"] = submission["grading"]
        return payload

    def get(self, job_id: str) -> dict | None:
        # Read under the registry lock so a just-completed worker cannot have its
        # final verdict overwritten by an interruption based on an older read.
        with _active_lock:
            submission = self.database.get_submission_job(job_id)
            if submission and submission["phase"] != "completed" and job_id not in _active_jobs:
                grading = self._failed_grading("The backend restarted before judging finished. Please submit again.")
                grading["status"] = "Interrupted"
                submission = self.database.finish_submission_job(job_id, grading)
        return self._payload(submission) if submission else None

    def start(
        self,
        problem_id: int,
        language: str,
        code: str,
        test_cases: list[dict] | None,
        timeout_ms: int = 5000,
    ) -> dict:
        validate_test_cases(test_cases)
        with self._lifecycle:
            if self._closed:
                raise SubmissionQueueFull("The judge is shutting down. Please try again shortly.")
            if not self._slots.acquire(blocking=False):
                raise SubmissionQueueFull("The judge queue is full. Please try again shortly.")
            job_id = str(uuid4())
            with _active_lock:
                _active_jobs.add(job_id)
            try:
                submission = self.database.save_submission({
                    "problem_id": problem_id,
                    "language": language,
                    "code": code,
                    "status": "Queued",
                    "job_id": job_id,
                    "phase": "queued",
                })
                self._pool.submit(self._execute, job_id, language, code, deepcopy(test_cases), timeout_ms)
            except Exception:
                self._slots.release()
                self.database.finish_submission_job(job_id, self._failed_grading("Unable to enqueue submission."))
                with _active_lock:
                    _active_jobs.discard(job_id)
                raise
        return self._payload(submission)

    @staticmethod
    def _failed_grading(error: str) -> dict:
        return {
            "status": "Judge Error",
            "error": error,
            "totalTests": 0,
            "passedTests": 0,
            "totalRuntimeMs": 0,
            "results": [],
        }

    def _execute(self, job_id: str, language: str, code: str, test_cases: list[dict] | None, timeout_ms: int):
        def progress(phase: str):
            if not self.database.update_submission_phase(job_id, phase):
                raise _RemovedJob()

        try:
            grading = submit_code(language, code, test_cases, timeout_ms, progress=progress)
            submission = self.database.finish_submission_job(job_id, grading)
            if submission and submission.get("problem_id"):
                try:
                    from .jira.services.issues import update_coding_story_submission
                    update_coding_story_submission(submission["problem_id"], grading["status"], grading.get("results"))
                except Exception:
                    pass
        except _RemovedJob:

            # Clearing the database cancels pending work without recreating deleted rows.
            pass
        except Exception:
            logger.exception("Submission job %s failed", job_id)
            self.database.finish_submission_job(
                job_id,
                self._failed_grading("The judge could not complete this submission. Please try again."),
            )
        finally:
            with _active_lock:
                _active_jobs.discard(job_id)
            self._slots.release()

    def shutdown(self, wait: bool = True):
        with self._lifecycle:
            self._closed = True
        self._pool.shutdown(wait=wait)
