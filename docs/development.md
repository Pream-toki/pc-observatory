# Development guide

## Setup

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

## Run the app

```powershell
.venv\Scripts\python main.py
```

## Run the tests

```powershell
.venv\Scripts\pytest
```

Tests use a temporary database (see `tests/conftest.py`) and mocked psutil.
No test modifies Windows configuration.

## Project layout

```
main.py                 entry point: logging → config → database → service → window
launch.py               stable target for desktop/Start Menu shortcuts
app/
  config/settings.py    AppConfig dataclass saved as JSON in %APPDATA%\PCObservatory
  models/               shared frozen dataclasses (samples, results, provenance)
  collectors/           one module per source: system, metrics, processes, network,
                        gpu, events, automation, applications, tools, ai, projects, scripts
  services/             CollectorScheduler (QThreads), SystemService, process history,
                        snapshots/diff engine, Ollama client
  database/             connection (WAL, per-thread), migrations, repositories
  ui/                   theme (QSS), sidebar, main window
    pages/              registry.py (PAGES list) + one module per page
  widgets/              cards, charts (pyqtgraph), health strip, HowDiscoveredDialog
  utils/                logging, global excepthook, redaction, exporters, formatting
tests/                  pytest suite (mocked / read-only)
logs/                   rotating log file (gitignored)
docs/                   architecture.md, development.md
```

## Workflow for a new phase

1. Add/extend collectors in `app/collectors/` returning `CollectorResult`.
2. Add models in `app/models/` if new normalized shapes are needed.
3. Add a migration in `app/database/migrations.py` (never edit old ones) and
   a repository for any new table.
4. Expose data through `SystemService` (signal for live updates, method for
   queries).
5. Build the page in `app/ui/pages/`, register it in `app/ui/pages/registry.py`
   (`PAGES` list) — the sidebar picks it up automatically.
6. Add tests with mocked sources; run `pytest`.
7. Update `docs/architecture.md` if the flow changed.

## Conventions

- Type hints everywhere; frozen dataclasses for data crossing threads.
- Collectors contain **no Qt code**; UI contains **no psutil/SQL**.
- All SQL lives in `app/database/repositories.py`.
- Every user-visible fact gets provenance (`CollectorMeta`) so a
  "How was this discovered?" button can be attached.
- Unavailable data renders as "Unavailable" or "Permission required" —
  never as a guessed value, never as zero.
