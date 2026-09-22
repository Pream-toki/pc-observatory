# PC Observatory

A Windows desktop app that shows what your computer is doing.

It collects real data from your own PC — running programs, installed software,
scripts, scheduled tasks, services, network ports, event logs — and stores
everything in a local database. Nothing is sent to the internet.

## What it shows

**Overview**

- **Dashboard** — live charts for CPU, memory, disk activity, and network
  throughput. Cards for uptime, Windows version, GPU, process count, listening
  ports, and the processes using the most CPU right now.
- **Search** — type one word (for example `python` or `ollama`) and find it
  across installed apps, tool locations, AI models, scripts, tasks, and
  services at the same time.
- **Timeline** — a running list of what happened: Windows boots, programs
  starting, scripts running. Newest first.

**Software**

- **Applications** — installed programs with version, publisher, and install
  location, read from the Windows registry.
- **Tool Locations** — the exact exe path of each tool (Python, Git, Node,
  VS Code, ...), plus a command resolver: type `python` and it shows which
  python.exe your PATH picks and its version.
- **AI & Models** — local AI tools (Ollama, LM Studio, Jan, GPT4All) and the
  model files on your disk, with sizes.

**Security**

- **Processes** — every running program, refreshed every 5 seconds: PID, user,
  CPU, memory, executable path, and command line. Protected processes show
  "Permission required" instead of guessed values.
- **Network** — which programs listen on which ports and which connections
  exist. It observes your own machine only.
- **Events** — recent Windows event log entries with filters by log, level,
  and time, and plain-language context for common event IDs.

**Automation**

- **Automation Center** — the full catalog of Windows services, startup
  entries, and scheduled tasks, with filter buttons.
- **My Automations** — your own scripts (`.py`, `.ps1`, `.bat`, `.cmd`, `.js`).
  When one runs, the app records when it started, how long it ran, what
  command ran it, and what triggered it (a scheduled task, a startup entry,
  or a manual run). It shows a green "running" marker while the script is
  still alive. It never runs or changes your scripts.

**Development**

- **Python Projects** — detected projects in your configured folders:
  Python files, virtual environments, Git folders, dependency files.

**History**

- **Changes & Snapshots** — take a snapshot of your PC's inventory, then
  compare it with a later one: what was added, removed, or changed.
  Export any report as CSV, JSON, or HTML.

**Assistant**

- Ask questions about your PC in plain language ("what python files are
  running?", "what changed since my last snapshot?"). Answers come from your
  own local Ollama models on 127.0.0.1 — no cloud, no account. If Ollama is
  not running, the page says so instead of hanging.

**Settings**

- Dark or light theme, update intervals for each collector, how long history
  is kept, and buttons to open the log and data folders.

## "How was this discovered?"

Every important number has a button next to it. It shows:

- which collector produced the value,
- the data source (psutil, Windows registry, PowerShell, event log, ...),
- when it was collected and whether it succeeded,
- a short technical explanation of the method.

No number in the app is anonymous.

## Rules the app follows

1. **Real data only.** If a value cannot be read, it says "Unavailable" or
   "Permission required". Nothing is invented.
2. **Local first.** No telemetry, no accounts, no cloud. The only network
   call the app can make is to your own Ollama server on 127.0.0.1, and only
   when you use the Assistant.
3. **Read only.** The app never kills processes, changes settings, deletes
   files, or edits the registry.
4. **Neutral words.** Unknown does not mean dangerous. The app never calls
   something malware without real evidence.
5. **No secrets.** Values that look like keys, tokens, or passwords are
   hidden, and command lines are redacted before anything is stored.

## Requirements

- Windows 10 or 11 (built and tested on 11)
- Python 3.12 or newer
- No administrator rights needed for normal use

## Install

Open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

## Run

Double-click `Start PC Observatory.bat`, or:

```powershell
.venv\Scripts\python main.py
```

The first start can take up to ~20 seconds because Windows scans every
library file on first run. A splash appears within about 2 seconds; the main
window follows. After the first start it opens faster.

To launch without a console window: `.venv\Scripts\pythonw.exe main.py`.

## Run the tests

```powershell
.venv\Scripts\pytest
```

All tests are mocked or strictly read-only. None of them change Windows
settings.

## Where your data is stored

| Data | Location |
|---|---|
| Database (SQLite) | `%APPDATA%\PCObservatory\observatory.db` |
| Config | `%APPDATA%\PCObservatory\config.json` |
| Logs | `logs\` in the project folder |

Delete those files to remove all traces of the app.

## How it works

Collectors run on background threads and read Windows through psutil, registry
reads, PowerShell queries, and the event log. Each result is normalized and
written to SQLite. The UI reads from the service layer, never from Windows
directly, so collection never freezes the window. If one collector fails, the
rest keep working and the health strip on the Dashboard shows which one and
why.

More detail: [docs/architecture.md](docs/architecture.md) ·
developer guide: [docs/development.md](docs/development.md)

## Project layout

```
main.py                  entry point
launch.py                target for the desktop shortcut
Start PC Observatory.bat no-console launcher
app/
  collectors/            one module per data source
  services/              background workers, service layer, snapshots, Ollama client
  database/              SQLite connection, migrations, repositories
  models/                shared dataclasses
  ui/                    theme, main window, one page per screen
  widgets/               cards, charts, provenance dialog
  utils/                 logging, redaction, exporters, formatting
tests/                   pytest suite
docs/                    architecture and developer notes
```

## Notes

- The Assistant needs Ollama installed and running (system tray). The app
  tells you when it is not available.
- Scheduled tasks are read through a fixed read-only PowerShell query.
- Security event logs need the right to read them; without it the Events page
  says "Permission required" instead of showing partial guesses.
