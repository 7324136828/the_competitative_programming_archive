"""FastAPI Router for Study Sets, Content, QA Sessions, Podcasts, and Jira associations.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .state import (
    get_content_store,
    get_active_workspace_id,
    set_active_workspace_id,
    get_upload_progress,
    set_upload_progress,
    extract_and_import_zip,
    create_qa_session,
    get_qa_session,
    update_qa_session,
    list_qa_sessions,
)
from .tts import synthesize_wav
from .podcast import render_podcast_script
from ..jira.db import db
from ..jira.services.issues import create_issue, get_issue_by_id, update_issue

logger = logging.getLogger("uvicorn.error")

router = APIRouter()


def _story_for_workspace(workspace: dict[str, Any]) -> dict[str, Any] | None:
    """Return the small story shape consumed by study-set cards."""
    story_id = workspace.get("story_id")
    if not story_id:
        return None
    story = get_issue_by_id(str(story_id))
    if not story:
        return None
    return {
        "id": story["id"],
        "key": story["key"],
        "summary": story["summary"],
        "status": story["status"],
        "story_type": story.get("story_type"),
        "priority": story.get("priority"),
    }


def _decorate_workspace(workspace: dict[str, Any]) -> dict[str, Any]:
    decorated = dict(workspace)
    decorated["story"] = _story_for_workspace(decorated)
    return decorated


def _workspace_response(workspaces: list[dict[str, Any]], active_id: str | None) -> dict[str, Any]:
    decorated = [_decorate_workspace(workspace) for workspace in workspaces]
    return {
        # Keep currentWorkspace for compatibility with the original API while
        # exposing the camel-case field used by the React study-set viewer.
        "currentWorkspace": active_id,
        "activeWorkspace": active_id,
        "workspaces": decorated,
        "exists": bool(decorated),
    }


def _decorate_upload(upload: dict[str, Any]) -> dict[str, Any]:
    decorated = dict(upload)
    decorated["studySets"] = [
        _decorate_workspace(study_set)
        for study_set in upload.get("studySets", [])
    ]
    return decorated


@router.get("/workspace")
def workspace_status():
    store = get_content_store()
    active_id = get_active_workspace_id()
    all_ws = store.list_all_workspaces()
    response = _workspace_response(all_ws, active_id)
    response["stats"] = {
        "totalWorkspaces": len(all_ws),
        "activeWorkspace": active_id,
    }
    return response


@router.post("/workspace/upload")
async def upload_workspace(request: Request):
    zip_bytes = await request.body()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Empty upload body")

    progress_id = request.headers.get("x-progress-id") or uuid.uuid4().hex
    filename = request.headers.get("x-filename") or "study_set.zip"

    try:
        upload_id = extract_and_import_zip(zip_bytes, filename, upload_id=progress_id)
        store = get_content_store()
        workspaces = store.list_workspaces(upload_id)
        if workspaces:
            set_active_workspace_id(workspaces[0]["id"])
        return {
            "success": True,
            "uploadId": upload_id,
            **_workspace_response(store.list_all_workspaces(), get_active_workspace_id()),
        }
    except Exception as e:
        logger.exception("Upload processing error")
        set_upload_progress(progress_id, "error", 0, str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workspace/uploads")
def list_workspace_uploads():
    store = get_content_store()
    return {"uploads": [_decorate_upload(upload) for upload in store.list_uploads()]}


@router.get("/workspace/uploads/progress/{upload_id}")
def check_upload_progress(upload_id: str):
    return get_upload_progress(upload_id)


@router.post("/workspace/load")
async def load_workspace_by_key(request: Request):
    data = await request.json()
    upload_id = data.get("uploadId")
    ws_key = data.get("workspaceKey")

    store = get_content_store()
    workspaces = store.list_workspaces(upload_id)
    target = None
    if ws_key:
        target = next((w for w in workspaces if w["workspace_key"] == ws_key), None)
    if not target and workspaces:
        target = workspaces[0]

    if not target:
        raise HTTPException(status_code=404, detail="Workspace not found")

    set_active_workspace_id(target["id"])
    return _workspace_response(store.list_all_workspaces(), target["id"])


@router.post("/workspace/activate")
async def activate_workspace_by_id(request: Request):
    data = await request.json()
    ws_id = data.get("workspace")
    if not ws_id:
        raise HTTPException(status_code=400, detail="workspace is required")

    store = get_content_store()
    ws = store.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    set_active_workspace_id(ws_id)
    return _workspace_response(store.list_all_workspaces(), ws_id)


@router.delete("/workspace/study-sets/{workspace_id}")
def delete_study_set(workspace_id: str):
    store = get_content_store()
    try:
        result = store.delete_workspace(workspace_id)
        if get_active_workspace_id() == workspace_id:
            set_active_workspace_id(None)
        return {
            "success": True,
            "deleted": result,
            **_workspace_response(store.list_all_workspaces(), get_active_workspace_id()),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/workspace/uploads/{upload_id}")
def delete_study_library(upload_id: str):
    store = get_content_store()
    try:
        result = store.delete_upload(upload_id)
        active_id = get_active_workspace_id()
        if active_id in result.get("workspaceIds", []):
            set_active_workspace_id(None)
        return {
            "success": True,
            "deleted": result,
            **_workspace_response(store.list_all_workspaces(), get_active_workspace_id()),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# --------------------------------------------------------------------------
# Jira Story Association
# --------------------------------------------------------------------------

@router.post("/workspace/associate-story")
async def associate_story(request: Request):
    data = await request.json()
    workspace_id = data.get("workspaceId")
    issue_id = data.get("issueId")
    if not workspace_id or not issue_id:
        raise HTTPException(status_code=400, detail="workspaceId and issueId are required")

    store = get_content_store()
    ws = store.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Update both sides
    store.set_workspace_story(workspace_id, issue_id)
    update_issue(issue_id, {"study_set_id": workspace_id})

    return {
        "success": True,
        "workspaceId": workspace_id,
        "storyId": issue_id,
    }


@router.post("/workspace/create-story")
async def create_story_for_workspace(request: Request):
    data = await request.json()
    workspace_id = data.get("workspaceId")
    summary = data.get("summary")
    project_id = data.get("projectId") or "proj_cp"

    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspaceId is required")

    store = get_content_store()
    ws = store.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    story_summary = summary or f"Study: {ws.get('name', 'Learning Module')}"
    user_id = request.headers.get("x-user-id", "u_alex")

    created = create_issue(
        {
            "projectId": project_id,
            "type": "Story",
            "story_type": "study",
            "study_set_id": workspace_id,
            "summary": story_summary,
            "description": f"Master the study set: {ws.get('name')}",
            "priority": "Medium",
        },
        creator_id=user_id,
    )

    store.set_workspace_story(workspace_id, created["id"])

    return {
        "success": True,
        "issue": created,
        "workspaceId": workspace_id,
    }


@router.post("/workspace/unlink-story")
async def unlink_story(request: Request):
    data = await request.json()
    workspace_id = data.get("workspaceId")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspaceId is required")

    store = get_content_store()
    ws = store.get_workspace(workspace_id)
    if ws and ws.get("story_id"):
        try:
            update_issue(ws["story_id"], {"study_set_id": None})
        except Exception:
            pass
    store.set_workspace_story(workspace_id, None)

    return {"success": True, "workspaceId": workspace_id}


# --------------------------------------------------------------------------
# Content & Manifest
# --------------------------------------------------------------------------

@router.get("/content/manifest")
@router.get("/manifest", include_in_schema=False)
def get_manifest():
    store = get_content_store()
    active_id = get_active_workspace_id()
    if not active_id:
        return {"generatedAt": "", "kinds": {}}
    return store.manifest(active_id)


@router.get("/content/{kind}/{filename:path}")
def get_content_file(kind: str, filename: str):
    store = get_content_store()
    active_id = get_active_workspace_id()
    if not active_id:
        raise HTTPException(status_code=404, detail="No active study set selected")

    try:
        body, content_type = store.read_content(active_id, kind, filename)
        return Response(content=body, media_type=content_type)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")


# --------------------------------------------------------------------------
# QA Sessions
# --------------------------------------------------------------------------

@router.post("/qa/sessions")
async def create_session(request: Request):
    data = await request.json()
    qa_file = data.get("qaFile", "")
    title = data.get("title", "Q&A Session")
    questions = data.get("questions", [])
    session = create_qa_session(qa_file, title, questions)
    return session


@router.get("/qa/sessions")
def list_sessions():
    return {"sessions": list_qa_sessions()}


@router.get("/qa/sessions/{session_id}")
def retrieve_session(session_id: str):
    session = get_qa_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.put("/qa/sessions/{session_id}")
async def update_session(session_id: str, request: Request):
    data = await request.json()
    answers = data.get("answers", [])
    current_question = data.get("currentQuestion", 0)
    completed = bool(data.get("completed", False))

    try:
        updated = update_qa_session(session_id, answers, current_question, completed)
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/qa/sessions/{session_id}/download")
def download_session(session_id: str):
    session = get_qa_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    content = json.dumps(session, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="qa_session_{session_id}.json"'},
    )


# --------------------------------------------------------------------------
# Audio & Podcasts
# --------------------------------------------------------------------------

@router.post("/flashcards/audio")
async def flashcards_audio(request: Request):
    data = await request.json()
    items = data.get("items") or data.get("cards") or []
    audios: dict[str, str] = {}

    for idx, item in enumerate(items):
        front_text = item.get("front") or item.get("text", "")
        back_text = item.get("back", "")
        if front_text:
            front_wav = synthesize_wav(front_text, voice="af_heart")
            audios[f"front_{idx}"] = "data:audio/wav;base64," + base64.b64encode(front_wav).decode("ascii")
        if back_text:
            back_wav = synthesize_wav(back_text, voice="af_heart")
            audios[f"back_{idx}"] = "data:audio/wav;base64," + base64.b64encode(back_wav).decode("ascii")

    return {"audios": audios}


@router.post("/generate_podcast")
async def generate_podcast_endpoint(request: Request):
    data = await request.json()
    podcast_file = data.get("podcast_file", "")
    voice_a = data.get("voiceA", "af_heart")
    voice_b = data.get("voiceB", "am_adam")

    store = get_content_store()
    active_id = get_active_workspace_id()

    job_id = uuid.uuid4().hex
    if active_id and podcast_file:
        try:
            body, _ = store.read_content(active_id, "podcasts", podcast_file)
            script_data = json.loads(body.decode("utf-8-sig"))
            combined_wav = render_podcast_script(script_data, voice_a, voice_b)
            # Save audio sidecar
            stem = podcast_file.rsplit(".", 1)[0]
            audio_name = f"{stem}.wav"
            with store._connect() as conn:
                conn.execute(
                    "INSERT INTO content(workspace_id, kind, subject, filename, body, content_type) "
                    "VALUES (?, 'podcasts', '', ?, ?, 'audio/wav') "
                    "ON CONFLICT(workspace_id, kind, subject, filename) DO UPDATE SET body=excluded.body",
                    (active_id, audio_name, combined_wav),
                )
        except Exception as e:
            logger.warning("Podcast generation error: %s", e)

    return {"job_id": job_id, "status": "completed"}


@router.get("/generate_podcast")
def get_podcast_job_status(job_id: str | None = None):
    return {"job_id": job_id, "status": "completed"}


@router.get("/generate_podcast/logs")
def get_podcast_logs(job_id: str | None = None):
    return {"logs": ["Rendering podcast turns...", "Concatenating audio segments...", "Complete."]}
