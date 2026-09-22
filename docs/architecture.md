# Architecture

PC Observatory follows one rule: **data flows in a single direction**.

```
Windows (psutil / registry / APIs)
        ↓
   Collectors          →  CollectorResult (status + data + provenance)
        ↓
 Normalized models     →  dataclasses in app/models
        ↓
 SQLite database       →  app/database (repositories own all SQL)
   + MetricBuffer      →  in-memory ring buffer for live charts
        ↓
   SystemService       →  background QThread workers emit Qt signals
        ↓
      UI               →  pages read from the service; never from Windows
```

## Layers

### Collectors (`app/collectors/`)

Plain Python classes (no Qt). Each implements `collect()` and returns a
`CollectorResult` — a status (`success`, `partial`, `permission_denied`,
`unsupported`, `error`), the normalized data, and a `CollectorMeta` holding
the collector name, source, human-readable method, and timestamp. That meta
is what powers every "How was this discovered?" button.

`BaseCollector.run()` wraps `collect()` with timing, error mapping, and an
audit row in `collection_runs`. A collector that raises `PermissionError`
becomes `permission_denied`; anything else becomes `error` — the app never
crashes because one collector failed.

Current collectors and their default frequency (all configurable in Settings):

| Collector | Frequency | Source |
|---|---|---|
| `MetricsCollector` | 2 s | psutil performance counters |
| `ProcessCollector` | 5 s | psutil.process_iter (+ per-pid exe/cmdline cache) |
| `NetworkCollector` | 10 s | psutil net_connections / net_if_addrs |
| `GpuCollector` | 30 s | nvidia-smi (if present) |
| `EventLogCollector` | 60 s | wevtutil (fixed read-only queries) |
| `AutomationCollector` | 5 min | registry Run keys, startup folders, PowerShell task query |
| `ScriptInventoryCollector` | 10 min | filesystem scan of configured project folders |
| `PythonProjectCollector` | 30 min | filesystem scan (requirements.txt, .venv, .git, ...) |
| `ApplicationsCollector` | 1 h | registry uninstall keys |
| `ToolCollector` | 1 h | PATH resolution + known install locations |
| `AiCollector` | 1 h | known AI-tool paths + Ollama API (local) + model dirs |

Two special components run alongside the collectors:

- `ProcessHistory` keeps first-seen/last-seen rows per process identity and
  writes boot/first-seen events to the timeline.
- `ScriptRunTracker` watches interpreter command lines from each process poll
  and records one row per script run (start, end, trigger), powering the My
  Automations page and its timeline events. Command lines pass through
  `utils.redact` before anything is stored.

### Models (`app/models/`)

Frozen dataclasses (`MetricSample`, `SystemInfo`, `CollectorResult`, …).
Immutable objects are safe to pass across threads without locks.

### Database (`app/database/`)

- `connection.py` — one SQLite connection per thread, WAL mode so the
  collection threads can write while the UI reads.
- `migrations.py` — ordered SQL scripts tracked in `schema_migrations`.
  Later phases add tables by appending a migration; existing databases
  upgrade in place.
- `repositories.py` — the only code that writes SQL. UI and services call
  repositories, never queries.

The charts intentionally do **not** read the database: `MetricBuffer` keeps
every 2-second sample in RAM for the longest chart window (30 min) and
persists one downsampled row every 15 seconds. The database stays small;
charts stay instant.

### Services (`app/services/`)

`CollectorScheduler` runs each collector on its own `QThread`; workers emit
`resultReady` signals. `SystemService` consumes those signals, updates the
buffer and repositories, re-emits typed Qt signals (`metricsUpdated`,
`systemInfoUpdated`, `gpuUpdated`, `collectorHealthChanged`), and answers UI
queries (`chart_window`, `latest_sample`, `collector_health`, `last_result`).
The UI thread is never blocked by collection work.

### UI (`app/ui/`, `app/widgets/`)

- `theme.py` — every color is a token in a `Palette`; one function renders
  the whole QSS. Dark and light are two palettes of the same vocabulary.
- `sidebar.py` — navigation is generated from the page registry
  (`app/ui/pages/registry.py`); pages only appear once implemented, so there
  are no empty placeholder screens.
- Widgets (`cards`, `charts`, `health_strip`, `how_discovered`) are reusable
  and know nothing about psutil or SQL.

## Error handling rules

1. Collector failures are data (`CollectorResult.status`), not exceptions
   that reach the UI.
2. An excepthook logs uncaught slot exceptions instead of dying silently.
3. Persistence failures are logged and skipped — live charts keep working.
4. The health strip shows the honest count ("2 of 3 collectors completed")
   with the real error text one click away.

## Testing strategy

- Collectors are tested with mocked `psutil` (deterministic counter deltas).
- Database tests run against a temporary database via `conftest.py`.
- One deliberately real, strictly read-only test proves the SystemCollector
  works on the actual machine.
- No test modifies Windows configuration — ever.
