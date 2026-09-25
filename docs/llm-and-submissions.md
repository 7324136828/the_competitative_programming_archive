# Models and submission status

Start The Connector backend (normally `http://127.0.0.1:8301`) and activate a
configuration in its library. CodeJudge discovers the active configuration IDs
from `GET /v1/models` before making requests to `POST /v1/chat/completions`.
Upstream provider credentials and routing belong in The Connector.

CodeJudge settings in `.env`:

```dotenv
LLM_PROVIDER=the_connector
CONNECTOR_BASE_URL=http://127.0.0.1:8301/v1
LLM_MODEL=
LLM_TIMEOUT_SECONDS=120
```

Leave `LLM_MODEL` blank to select the first discovered configuration, or set it
to an active library `model_id`. Restart the CodeJudge backend after changing
these settings. The UI fetches `/api/llm/models` and displays the selected ID.
This is a routing configuration alias; its underlying provider/model may change
when The Connector uses a fallback route.

Choose an active model from the **AI model** dropdown. The choice is shared by
the AI tools and remembered in this browser. **Refresh models** reloads the
catalog; if your saved choice is no longer available, the server's default is
selected. New requests use the new choice. Existing results retain the model ID
that produced them, and switching models starts the progressive hints over.

## Workspace layout

To access the workspace from another device on the same network, launch
`run_lan.bat` and open one of the printed LAN URLs on that device. This wrapper
runs `run.bat serve --lan` and forwards `--frontend-port` and `--backend-port`.
For example, `run_lan.bat --frontend-port 8080 --backend-port 8000` serves the
UI on port 8080 and sends its API requests to the backend on port 8000. Busy
ports advance to the next free port. The launcher prints the actual URLs. You can also use
`python run.py serve --lan` directly. The frontend listens on the network and
proxies API and audio requests to the backend. All connected devices use this
installation's shared problems, drafts, and submission history.

Drag the visible divider between the problem and editor, or between the editor
and test console. Focus a divider and use arrow keys to resize it; Shift moves
it farther, Home/End move to its limits, and double-click restores its default.
Split sizes are remembered in this browser.

The expand button in each panel header fills the window with the problem, code
editor, or test cases and results. **Restore layout** or Escape returns to the
split view without losing code, selected tests, or panel sizes. On narrow
screens the problem and editor area stack vertically.

## AI tasks

Hints, generated problems, generated test cases, translation, and chat use that
model. These endpoints require POST JSON requests from the UI. Opening their URL
directly in a browser sends GET and is not an inference request. Network,
configuration, and malformed model-response errors appear in the UI. They never
silently become successful mock output. `LLM_PROVIDER=mock` explicitly enables
offline fixtures for development.

Generated problems are previews until saved, unless `autoSave: true` is requested.
“Solve This Problem” saves an unsaved preview and opens its database ID. Already
saved problems are opened without inserting another copy.

## Asynchronous submissions

POST `/api/submit` with `problemId`, `language`, `code`, and `async: true` returns
HTTP 202 and a `jobId`. Poll GET `/api/submission-jobs/{jobId}` until `done` is true.
The response exposes queued, compiling, running, and completed phases. The final
response contains the persisted `submission` and per-case `grading` results.
Omitting `async` preserves the synchronous API.

Jobs use a bounded worker pool in a single backend process. Completed results
survive restarts; pending work interrupted by a restart is reported as
`Interrupted` and must be resubmitted. Multiple backend worker processes require
an external queue and are not supported by this local worker pool.

Compilation completes before any case runs, and compilation happens once per
submission. Each test supplies stdin and an explicit expected output. An empty
expected string is valid; a missing or null expected output is invalid. A problem
with no tests returns `Not Judged`, with zero tests, and cannot become solved.
Use Run for unchecked custom input, or provide test cases before submitting.

Solved indicators are derived from persisted, verified Accepted results and
remain green after reload. Old Accepted records containing no expected output
remain in history but do not count as solved. Solved problems can still be opened
and submitted again.

## Saved editor drafts

Use **Upload code** in the editor toolbar, or drag a source file onto the editor,
to load its contents. Supported files are `.py`, `.cpp`, `.cc`, `.cxx`, `.java`,
and `.txt`, encoded as UTF-8 and no larger than 2 MiB. The file extension selects
the matching installed programming language; `.txt` uses the current language.
The imported source replaces that language's editor draft and saves through
the normal autosave flow. Empty files stay empty. Click **Run Code** or
**Submit** when ready to execute it.

Code changes save automatically after a short pause, separately for each problem
and language. The editor shows **Saving**, **Saved to disk**, or a retryable error.
Opening a problem loads its saved file through the `editor_drafts` database
reference. Without a reference, or if its file is missing, the language's default
template loads. A saved empty file stays empty.

Concurrent tabs use revision checks. When a draft changes elsewhere, choose
whether to load the saved version or keep your version. Switching problems,
languages, or screens flushes pending changes. Wait for the saved indicator
before closing the browser; closing with pending changes prompts you to stay.

Draft source files and narration files live under
`data/workspace/<database-id>/` by default. Set `WORKSPACE_STORAGE_DIR` to use a
different directory. Back up this directory together with the SQLite database;
draft paths in the database are relative to the storage directory. Keep that
setting unchanged when moving a database to preserve its file references.
Clearing the database deletes its draft references, problems, and submissions;
it does not recursively remove stored files.

## Submission history and export

Open **Submissions** in the navigation bar to browse submissions across
all problems. Each record includes its original code, verdict, output, and test
results. **Open problem** returns to that problem's current editor draft.

**Export all submissions (ZIP)** includes every submission, regardless of the
current page or verdict. The ZIP contains a manifest, source files with their
language extensions, and JSON metadata with the recorded test results. Drafts
are separate from submitted solutions and are not part of this export.

## AI response formatting and read aloud

AI chat replies and thinking steps render Markdown headings, lists, tables,
code blocks, and LaTeX formulas. Inline `$...$` and display `$$...$$` math are
supported, together with `\(...\)` and `\[...\]`. JSON responses and JSON code
blocks are indented for reading. Code samples retain their literal contents.

Click **Read response aloud** below an AI reply or **Read hint aloud** below a
thinking step to generate a saved MP3 through The Connector. The player shows
generation progress, offers playback controls and an MP3 download, and reuses
the cached file for the same response and Connector endpoint. Markdown is
reduced to readable text before synthesis.

Open **Settings → Clear saved audio** to remove cached problem and AI-response
MP3s and see how much disk space they use. Clearing stops open players and
invalidates unfinished audio jobs; another click on a read-aloud button can
regenerate the audio. Drafts, submissions, and problem records are preserved.

Audio API endpoints:

```text
POST   /api/audio/responses                 {"text": "AI reply", "language": "en"}
GET    /api/audio/responses/<key>           generation status / saved MP3 URL
GET    /api/audio/cache                     saved file count and size
DELETE /api/audio/cache                     clear saved audio
```

## Problem narration through The Connector

Click **Read problem aloud** in a saved problem to generate narration in the background
and reveal an audio player. The backend calls The Connector's `POST /api/speech`
skill for WAV audio, encodes a real MP3 with LAME, and saves it to disk. Playback
supports seeking and downloading the MP3. The same description and Connector
endpoint reuse the saved file after reloads and backend restarts.

Install the updated backend dependencies with your project Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Start The Connector before requesting new narration. It owns the private Kokoro
service and exposes readiness at `GET /api/speech/health`. CodeJudge never calls
Kokoro directly. The frontend reports Connector validation, availability, and
generation errors and offers a retry; cached MP3s remain available while The
Connector is stopped.

CodeJudge settings in `.env` (restart its backend after changing them):

```dotenv
WORKSPACE_STORAGE_DIR=
CONNECTOR_BASE_URL=http://127.0.0.1:8301/v1
CONNECTOR_SPEECH_TIMEOUT_SECONDS=180
```

Configure voice, language, speed, model dependencies, and CPU/CUDA selection in
The Connector, then restart The Connector. Its public speech contract accepts
only `{ "content": "..." }`, so CodeJudge does not override those settings per
request. Clear CodeJudge's saved audio after changing Connector speech settings
if you want existing narration regenerated. The player reads the saved problem
description, including its title.
