# Comparison with sample-react-python-project

The reference is the `sample-react-python-project/` folder supplied in this
checkout. Its files remain unchanged.

## Implemented parity

| Behavior | The Study Platform |
| --- | --- |
| Development LAN access | Both services default to `0.0.0.0`; `--host` applies to both and existing `.env` values retain precedence over defaults. `--lan` forces LAN unless `--host` is explicit. |
| LAN URL discovery | Startup prints frontend and API URLs for usable adapters. Local-only bindings do not advertise LAN URLs. |
| Port options | Supports `--frontend-port` / `--backend-port` and sample aliases `--frontend` / `--backend`; busy ports advance and both services receive distinct ports. |
| Same-origin browser API | Development and portable frontend servers forward `/api` and `/uploads` to the selected backend. |
| Build workflow | `build.bat` / `build.py`, active environment or `.venv`, dependency installation, and `--skip-install`. |
| Portable output | `dist/Debug` and `dist/Release`, each with `server.exe`, `public/`, `run.bat`, `runtime.json`, and `port_mapping.json`; Debug is local and Release is LAN by default. |
| Port defaults artifact | Validates the project `port_mapping.json`, copies it unchanged into both profiles, and fills only missing per-user port fields from the artifact mapping before launch. |
| Distribution configuration | A distribution may have its own optional `.env`; source secrets and runtime data are not copied. |
| Safe replacement | Build stages and validates artifacts before replacing both distributions, with rollback on replacement errors. |
| Backend docs | FastAPI serves `/docs`; its generated schema covers native FastAPI routes. |

## Differences and remaining gaps

| Area | Sample | This application / implication |
| --- | --- | --- |
| Default ports | Development `5173` / `8000`; portable defaults come from its mapping, currently `3100` / `3200`. | Uses the mapping in both modes, currently `5100` / `8011`, persisted as `frontend_port` / `backend_port` in per-user settings. CLI flags override saved ports. |
| Port precedence and conflicts | Portable CLI flags, then `FRONTEND_PORT` / `BACKEND_PORT` environment values, then saved settings; identical or occupied ports stop startup. | CLI flags, then saved settings, then mapping defaults. Port environment variables do not override settings; occupied or identical requested ports advance to distinct free ports. |
| Backend | FastAPI only, with a SQLite click counter. | FastAPI hosts Jira/study routes and mounts the existing Flask archive. Flask routes do not appear in FastAPI's generated OpenAPI schema. |
| Development reload | Uvicorn reload defaults on, with `--no-reload`. | The root runner starts the unified app without automatic Python reload. Restart after backend edits; Vite still reloads frontend edits. |
| Frontend type checking | A separate `npm run typecheck` runs before packaging. | The current frontend has no complete TypeScript checking configuration/script. Packaging runs the frontend tests and Vite build; Vite transpiles TypeScript without type checking. |
| Data location | Per-user settings at `%APPDATA%/sample-react-python-project/settings.json`; default data `%TEMP%/sample-react-python-project`, with `counter.db` there. Source/Debug/Release share the user-selected folder. | Same per-user layout under `the_study_platform`, with `jira.db` and associated uploads, drafts, and study data. |
| Storage setting format | `data_directory` expands environment variables and `~`; relative paths resolve beside settings.json. | `data_dir` accepts an absolute folder or an empty string for the TEMP default. |
| Folder changes | No storage-folder UI. | Host-local Settings UI persists a folder for restart. Existing data is not automatically migrated. Explicit storage environment overrides still win. |
| Legacy migration | Only the counter database is involved. | The existing opt-in importer handles legacy archive/Jira records and draft/audio files. It does not import legacy study tables or copy old attachments/voices automatically; those need a separate backup and transfer. |
| Runtime services | Counter needs no additional service or language tools. | AI and speech need The Connector. Code execution needs installed Python, C++ and/or Java toolchains. Unavailable languages are omitted; the frozen server is never used as a submission interpreter. |
| Frontend routing | Static built frontend. | Portable serving includes SPA fallback for application navigation and attachment proxying. |
| Relative portable paths | Counter path is resolved beside the executable. | Relative database/workspace/upload overrides also resolve beside `server.exe`, so they persist outside the temporary extraction directory. |
| Storage-setting access | No host filesystem settings API. | LAN clients can view settings; only host-local requests may change them. Frontend proxies authenticate the actual client address to the backend. |

Changing the default storage layout does not import previous checkout-specific
data automatically. The existing `MIGRATE_LEGACY_DATABASES=1` opt-in remains
available for legacy database import; retain backups and copy associated files
when choosing a different folder. The new default directory is shared across
checkouts for the same OS user, as requested by the stable application name.
