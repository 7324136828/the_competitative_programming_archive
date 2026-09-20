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
runs `run.bat serve --lan` and forwards extra arguments, including
`--frontend-port` and `--kokoro-device`. You can also use
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
thinking step to generate a saved Kokoro MP3. The player shows generation
progress, offers playback controls and an MP3 download, and reuses the cached
file for the same response and voice settings. Chat and hint narration use an
English voice. Markdown is reduced to readable text before synthesis.

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

## Problem narration with Kokoro

Click **Read problem aloud** in a saved problem to generate narration in the background
and reveal an audio player. The backend asks the separate Kokoro service for
WAV audio, encodes a real MP3 with LAME, and saves it to disk. Playback supports
seeking and downloading the MP3. The same description and voice reuse the saved
file after reloads and backend restarts; changing the description or speech
settings produces a new file.

Install the updated backend dependencies with your project Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

The supplied `python-kokoro/server.py` requires its own Python 3.12 environment.
Its default service address is `http://127.0.0.1:8880`. Start it before requesting
new narration. The frontend reports connection or generation errors and offers
a retry; already cached MP3s remain available when Kokoro is stopped.

The root launchers now prepare and start Kokoro with the rest of CodeJudge:

```powershell
.\setup.bat
.\run.bat
```

`setup.py` always uses a separate Python 3.12 environment for speech, even when
the main app runs under another Python version or an active Conda environment.
It installs and checks the requested PyTorch device, backend, frontend, and
browser-test dependencies. `run.py` waits for Kokoro's health check before
starting the backend and frontend. It reuses a compatible service already
running at `KOKORO_BASE_URL`; it stops only services it started when you exit.

Use `python setup.py --kokoro-only` to prepare just the speech environment.
Both root scripts support `--kokoro-device cpu` and `--skip-kokoro`.
`KOKORO_DEVICE=cuda` is the default; terminal variables override `.env`, and the
command-line device overrides both. On Linux/macOS, use the `.sh` wrappers and
install `python3.12`; use CPU explicitly on a machine without CUDA.

To manage only the Windows speech service independently, the dedicated scripts
remain available:

```powershell
.\python-kokoro\setup.ps1 -Device cuda
.\python-kokoro\run.ps1 -Device cuda
```

Kokoro runs as a standalone service using Python 3.12 from
`python-kokoro/.venv/Scripts/python.exe`, independently of CodeJudge's Python
environment. Setup and launch default to **CUDA**. Setup installs the pinned
PyTorch CUDA 12.8 build from `requirements-cuda.txt`, then Kokoro, and verifies
an actual GPU computation. The wheel comes from the
[official PyTorch CUDA index](https://pytorch.org/get-started/previous-versions/).
If Python 3.12 already has these dependencies, `setup.ps1 -ReuseSystemPackages`
can reuse them. CUDA failures are reported rather than silently falling back
to CPU. To explicitly use a CPU, pass `-Device cpu` to both scripts.

If a service is already running on CPU, switch it with:

```powershell
.\python-kokoro\run.ps1 -Device cuda -Restart
```

The restart option only stops a process identified as this repository's Kokoro
server. A normal launch checks the existing service's device and refuses to
silently reuse a CPU service for a CUDA request. Inspect
`http://127.0.0.1:8880/health` to see the interpreter, CUDA runtime, GPU, and loaded
pipeline devices. The first narration may download speech-model and language data. The run
script starts a hidden process, checks its health, and writes logs and its PID
under `data/workspace/kokoro-service/`. Use `-Foreground` to run it in your
terminal and stop it with Ctrl+C. These standalone scripts are optional when
using the root setup and run commands.

Optional settings in `.env` (restart CodeJudge after changing them):

```dotenv
WORKSPACE_STORAGE_DIR=
KOKORO_BASE_URL=http://127.0.0.1:8880
KOKORO_DEVICE=cuda
KOKORO_MODEL=kokoro
KOKORO_LANGUAGE=auto
KOKORO_VOICE=
KOKORO_SPEED=1.0
KOKORO_TIMEOUT_SECONDS=180
```

Automatic voice selection follows the problem's original language. English,
Spanish, French, Hindi, Italian, Japanese, Portuguese, and Chinese are supported;
Japanese and Chinese require the service's optional `misaki[ja]` and `misaki[zh]`
dependencies. AI-generated English problems use the English voice. Set a voice
and Kokoro language code only when they match the problem language. The player
reads the original saved description, including its title.
