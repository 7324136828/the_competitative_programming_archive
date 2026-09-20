# Sample React + Python Project

For the current CodeJudge model connection, generated problems, and asynchronous
submission API, see [Models and submission status](docs/llm-and-submissions.md).

A reusable full-stack template with a React/Vite frontend and FastAPI backend.
The example application is a persistent click counter:

- **Click** sends a request to Python, which increments the count atomically.
- The count is stored in SQLite, so closing the browser or stopping the server
  does not erase it.
- **Clear count** resets the stored value to zero.
- The frontend reloads the current value whenever it starts.

## Quick start

Windows:

```powershell
.\setup.bat
.\run.bat
```

Linux/macOS:

```bash
./setup.sh
./run.sh
```

If a Python virtual environment or Conda environment is already active, setup
installs into that environment and run uses the same interpreter. Otherwise,
the scripts create and reuse `.venv` in this project.

The root setup also prepares Kokoro in a separate Python 3.12 environment at
`python-kokoro/.venv`, with CUDA acceleration by default. Install Python 3.12
alongside your application Python. The root runner starts Kokoro and waits for
it to be ready before launching CodeJudge, or reuses a compatible service
already running on port 8880. Services it starts stop with Ctrl+C; a reused
Kokoro service keeps running.

For CPU-only machines, use `setup.bat --kokoro-device cpu` and
`run.bat --kokoro-device cpu` (or the equivalent `.sh` wrappers).
Set `KOKORO_DEVICE=cpu` in `.env` to remember that choice. To update only the
speech environment, run `python setup.py --kokoro-only`.
`--skip-kokoro` leaves speech setup/startup to you.

To open CodeJudge from another device on the same LAN, run:

```powershell
.\run_lan.bat
```

Open the printed `LAN: http://<computer-IP>:<port>` address on that device.
The wrapper forwards options, for example `run_lan.bat --frontend-port 5190`.
Its equivalent command is `python run.py serve --lan`, or
`./run.sh serve --lan` on Linux/macOS. The frontend handles API and narration
requests through its local backend proxy. Devices share the same stored data.

The default backend and frontend ports are `8000` and `5173`. The runner checks
both ports before launch and advances to the next available port when needed.
It prints the actual URLs selected for the session.

## Configuration

Copy `.env.example` to `.env` to customize the preferred ports, bind address,
or database path. Environment variables already defined in the terminal take
precedence over values in `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKEND_PORT` | `8000` | First backend port to try |
| `FRONTEND_PORT` | `5173` | First frontend port to try |
| `BACKEND_HOST` | `127.0.0.1` | Backend bind address |
| `COUNTER_DB_PATH` | `data/counter.db` | Persistent SQLite database |

## API

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/health` | Backend health check |
| `GET` | `/api/counter` | Read the saved count |
| `POST` | `/api/counter/click` | Increment and return the count |
| `DELETE` | `/api/counter` | Reset and return the count |

Interactive API documentation is available at the backend `/docs` URL.

## Tests and build

```powershell
python -m unittest discover -s backend\tests -v
cd frontend
npm run typecheck
npm run build
cd ..\e2e
npm run typecheck
npm test
```

The Playwright suite starts both FastAPI and Vite automatically, then exercises
the live API through the frontend proxy using an isolated test database. It
uses Microsoft Edge by default. On macOS it uses Playwright's WebKit-based
Desktop Safari profile, which is the supported automation equivalent for
Safari rendering.

On a fresh macOS checkout, install the WebKit browser once before running the
tests:

```bash
cd e2e
npm run install:webkit
```

## Project layout

```text
backend/                  FastAPI application, SQLite store, and unit tests
frontend/                 TypeScript React/Vite application
e2e/                      Standalone TypeScript Playwright end-to-end tests
data/                     Runtime database location (database is ignored)
setup.py / setup.*        Cross-platform dependency setup
run.py / run.*            Combined backend/frontend runner
```
