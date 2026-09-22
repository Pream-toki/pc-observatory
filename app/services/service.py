"""SystemService — the one object the UI talks to.

It wires collectors to background threads, funnels samples into the
MetricBuffer and the database, and answers UI queries. The UI never touches
psutil, SQL, or worker threads directly.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, Signal

from ..collectors.base import BaseCollector
from ..collectors.ai import AiCollector
from ..collectors.applications import ApplicationsCollector
from ..collectors.automation import AutomationCollector
from ..collectors.events import EventLogCollector
from ..collectors.gpu import GpuCollector
from ..collectors.metrics import MetricsCollector
from ..collectors.network import NetworkCollector
from ..collectors.processes import ProcessCollector
from ..collectors.projects import PythonProjectCollector
from ..collectors.scripts import ScriptInventoryCollector, ScriptRunTracker
from ..collectors.tools import ToolLocationsCollector
from ..collectors.system import SystemCollector
from ..config.settings import AppConfig
from ..database.repositories import (
    CollectionRunRepository,
    MetricRepository,
    SystemInfoRepository,
)
from ..database.history_repositories import (
    ProcessRepository,
    TimelineEvent,
    TimelineRepository,
)
from ..database.inventory_repositories import (
    AiModelRepository,
    AiToolRepository,
    ApplicationRepository,
    ToolRepository,
)
from ..database.ops_repositories import (
    ChangeRepository,
    EventRepository,
    PortRepository,
    ProjectRepository,
    ServiceRepository,
    SnapshotRepository,
    StartupRepository,
    TaskRepository,
)
from ..database.script_repositories import ScriptRepository, ScriptRunRepository
from .process_history import ProcessHistory
from .snapshots import SnapshotEngine
from ..models.metrics import CollectorResult, MetricSample, SystemInfo
from .metric_buffer import MetricBuffer
from .workers import CollectorScheduler

log = logging.getLogger(__name__)

_BUFFER_SECONDS = 1800  # 30 min — the longest chart window


class SystemService(QObject):
    """Facade for all system data. Signals carry the newest normalized models."""

    metricsUpdated = Signal(object)        # MetricSample
    systemInfoUpdated = Signal(object)     # SystemInfo
    gpuUpdated = Signal(object)            # CollectorResult
    processesUpdated = Signal(object)      # list[ProcessInfo]
    timelineChanged = Signal()
    inventoryChanged = Signal()            # applications / tools / AI updated
    collectorHealthChanged = Signal()      # health strip re-reads latest runs

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._last_results: dict[str, CollectorResult] = {}
        self._buffer = MetricBuffer(max_seconds=_BUFFER_SECONDS,
                                    persist_every=config.persist_sample_every_s)
        self._metrics_repo = MetricRepository()
        self._system_repo = SystemInfoRepository()
        self._runs_repo = CollectionRunRepository()

        self._system_collector = SystemCollector(self._runs_repo)
        self._metrics_collector = MetricsCollector(self._runs_repo)
        self._gpu_collector = GpuCollector(self._runs_repo)
        self._apps_collector = ApplicationsCollector(self._runs_repo)
        self._tools_collector = ToolLocationsCollector(self._runs_repo)
        self._ai_collector = AiCollector(self._runs_repo)
        self._process_collector = ProcessCollector(self._runs_repo)
        self._process_repo = ProcessRepository()
        self._timeline_repo = TimelineRepository()
        self._process_history = ProcessHistory(self._process_repo)
        self._app_repo = ApplicationRepository()
        self._tool_repo = ToolRepository()
        self._aitool_repo = AiToolRepository()
        self._aimodel_repo = AiModelRepository()
        self._port_repo = PortRepository()
        self._service_repo = ServiceRepository()
        self._startup_repo = StartupRepository()
        self._task_repo = TaskRepository()
        self._event_repo = EventRepository()
        self._project_repo = ProjectRepository()
        self._change_repo = ChangeRepository()
        self._script_repo = ScriptRepository()
        self._scriptrun_repo = ScriptRunRepository()
        self._scripts_collector = ScriptInventoryCollector(
            self._runs_repo, config=config, script_repo=self._script_repo)
        self._script_tracker = ScriptRunTracker(script_repo=self._script_repo)
        self._snapshots_engine = SnapshotEngine()

        self._scheduler = CollectorScheduler(self)
        self._connect_workers()
        self._apply_retention()
        # First run: record the baseline snapshot so all later "what changed?"
        # questions have a reference point (spec §33). Triggered from the first
        # automation inventory (guaranteed to have run after apps/tools/AI too,
        # same worker loop) — more reliable than a fixed startup timer.
        self._baseline_done = False
        self.inventoryChanged.connect(self._maybe_auto_baseline)

    # ---- wiring ------------------------------------------------------
    def _connect_workers(self) -> None:
        metrics_worker = self._scheduler.add_collector(
            self._metrics_collector, self._config.metrics_interval_s
        )
        metrics_worker.resultReady.connect(self._on_metrics)

        system_worker = self._scheduler.add_collector(
            self._system_collector, self._config.system_info_interval_s
        )
        system_worker.resultReady.connect(self._on_system_info)

        gpu_worker = self._scheduler.add_collector(self._gpu_collector, 30.0)
        gpu_worker.resultReady.connect(self._on_gpu)

        process_worker = self._scheduler.add_collector(self._process_collector, 5.0)
        process_worker.resultReady.connect(self._on_processes)

        # Inventories: once at startup, then hourly (spec §46). Heavy scans
        # take an initial delay so the window appears before they compete for
        # CPU/disk — fast pages stay instant, the rest fill in over ~45 s.
        apps_worker = self._scheduler.add_collector(self._apps_collector, 3600.0,
                                                    initial_delay_s=5.0)
        apps_worker.resultReady.connect(self._on_applications)
        tools_worker = self._scheduler.add_collector(self._tools_collector, 3600.0,
                                                     initial_delay_s=20.0)
        tools_worker.resultReady.connect(self._on_tools)
        ai_worker = self._scheduler.add_collector(self._ai_collector, 3600.0,
                                                  initial_delay_s=35.0)
        ai_worker.resultReady.connect(self._on_ai)

        self._network_collector = NetworkCollector(self._runs_repo)
        net_worker = self._scheduler.add_collector(self._network_collector, 10.0)
        net_worker.resultReady.connect(self._on_network)

        self._automation_collector = AutomationCollector(self._runs_repo)
        auto_worker = self._scheduler.add_collector(self._automation_collector, 300.0,
                                                    initial_delay_s=12.0)
        auto_worker.resultReady.connect(self._on_automation)

        self._events_collector = EventLogCollector(self._runs_repo, self._event_repo)
        events_worker = self._scheduler.add_collector(self._events_collector, 60.0)
        events_worker.resultReady.connect(self._on_events)

        self._projects_collector = PythonProjectCollector(self._runs_repo,
                                                          config=self._config)
        proj_worker = self._scheduler.add_collector(self._projects_collector, 1800.0,
                                                    initial_delay_s=25.0)
        proj_worker.resultReady.connect(self._on_projects)

        self._scripts_worker = self._scheduler.add_collector(
            self._scripts_collector, 600.0, initial_delay_s=8.0)
        self._scripts_worker.resultReady.connect(self._on_scripts)

    # ---- slots -------------------------------------------------------
    def _remember(self, name: str, result: CollectorResult) -> None:
        self._last_results[name] = result

    def _on_metrics(self, result: CollectorResult) -> None:
        self._remember("MetricsCollector", result)
        sample: MetricSample | None = result.data if result.ok else None
        if sample is not None:
            to_persist = self._buffer.add(sample)
            if to_persist is not None:
                try:
                    self._metrics_repo.insert_sample(to_persist)
                except Exception:  # noqa: BLE001 — DB hiccup must not stop live charts
                    log.exception("Failed to persist metric sample")
            self.metricsUpdated.emit(sample)
        self.collectorHealthChanged.emit()

    def _on_system_info(self, result: CollectorResult) -> None:
        self._remember("SystemCollector", result)
        info: SystemInfo | None = result.data if result.ok else None
        if info is not None:
            try:
                previous = self._system_repo.latest()
                self._record_boot_event(info, previous)
                self._system_repo.upsert(info)
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist system info")
            self.systemInfoUpdated.emit(info)
        self.collectorHealthChanged.emit()

    def _record_boot_event(self, info: SystemInfo, previous) -> None:
        """Timeline event when a new Windows boot is detected.

        First run ever: honestly record that the PC was already running when
        observation began. Later boots: record the exact boot time.
        """
        try:
            if previous is None:
                if info.boot_time:
                    self._timeline_repo.add(TimelineEvent(
                        ts=info.boot_time,
                        kind="boot",
                        title="Windows was running when PC Observatory first started",
                        details="First observation; boot time read via psutil.boot_time().",
                    ))
                    self.timelineChanged.emit()
                return
            if info.boot_time > previous.boot_time + 60:
                self._timeline_repo.add(TimelineEvent(
                    ts=info.boot_time,
                    kind="boot",
                    title="Windows booted",
                    details="Uptime counter restarted — a new Windows session began.",
                ))
                self.timelineChanged.emit()
        except Exception:  # noqa: BLE001
            log.exception("Failed to record boot event")

    def _on_gpu(self, result: CollectorResult) -> None:
        self._remember("GpuCollector", result)
        self.gpuUpdated.emit(result)
        self.collectorHealthChanged.emit()

    def _on_applications(self, result: CollectorResult) -> None:
        self._remember("ApplicationsCollector", result)
        apps = result.data if result.ok else []
        if apps:
            try:
                self._app_repo.upsert_many(apps)
                self.inventoryChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist applications")
        self.collectorHealthChanged.emit()

    def _on_tools(self, result: CollectorResult) -> None:
        self._remember("ToolLocationsCollector", result)
        tools = result.data if result.ok else []
        if tools:
            try:
                self._tool_repo.upsert_many(tools)
                self.inventoryChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist tool locations")
        self.collectorHealthChanged.emit()

    def _on_ai(self, result: CollectorResult) -> None:
        self._remember("AiCollector", result)
        data = result.data if result.ok else None
        if data:
            try:
                self._aitool_repo.upsert_many(data.get("tools", []))
                self._aimodel_repo.upsert_many(data.get("models", []))
                self.inventoryChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist AI inventory")
        self.collectorHealthChanged.emit()

    def _on_network(self, result: CollectorResult) -> None:
        self._remember("NetworkCollector", result)
        ports = result.data if result.ok else []
        if ports:
            try:
                self._port_repo.upsert_many(ports)
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist ports")
        self.collectorHealthChanged.emit()

    def _on_automation(self, result: CollectorResult) -> None:
        self._remember("AutomationCollector", result)
        data = result.data if result.ok else None
        if data:
            try:
                self._service_repo.upsert_many(data.get("services", []))
                self._startup_repo.upsert_many(data.get("startup", []))
                self._task_repo.upsert_many(data.get("tasks", []))
                self.inventoryChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist automation data")
        self.collectorHealthChanged.emit()

    def _on_events(self, result: CollectorResult) -> None:
        self._remember("EventLogCollector", result)
        self.collectorHealthChanged.emit()

    def _on_projects(self, result: CollectorResult) -> None:
        self._remember("PythonProjectCollector", result)
        projects = result.data if result.ok else []
        if projects:
            try:
                self._project_repo.upsert_many(projects)
                self.inventoryChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist projects")
        self.collectorHealthChanged.emit()

    def _on_scripts(self, result: CollectorResult) -> None:
        self._remember("ScriptInventoryCollector", result)
        # The collector persisted its own inventory; refresh tracker paths.
        if result.ok and result.data:
            self._script_tracker.invalidate()
            self.inventoryChanged.emit()
        self.collectorHealthChanged.emit()

    # ---- snapshots -----------------------------------------------------
    def take_snapshot(self, label: str = "manual") -> int:
        return self._snapshots_engine.take_snapshot(label)

    def _maybe_auto_baseline(self) -> None:
        """Take the baseline snapshot on the first full inventory pass — but
        only the first time. Later snapshots are manual (Changes page)."""
        if self._baseline_done:
            return
        self._baseline_done = True
        try:
            if self._snapshots_engine._snapshots.latest("fingerprint") is None:
                sid = self.take_snapshot("baseline (automatic)")
                log.info("Baseline snapshot #%s recorded", sid)
            else:
                log.info("Baseline skipped — fingerprint snapshot already exists")
        except Exception:  # noqa: BLE001 — never block startup
            log.exception("Automatic baseline snapshot failed")

    def recent_changes(self, since_ts: float | None = None):
        return self._change_repo.recent(limit=500, since_ts=since_ts)

    def snapshot_list(self):
        return self._snapshots_engine._snapshots.all()

    def _on_processes(self, result: CollectorResult) -> None:
        self._remember("ProcessCollector", result)
        infos = result.data if result.ok else []
        if infos:
            self.processesUpdated.emit(infos)
            try:
                events = self._process_history.update(infos)
                # Automation Monitor: detect scripts running in this poll.
                script_events = self._script_tracker.update(infos)
                for ev in script_events:
                    events.append(TimelineEvent(
                        ts=ev["ts"], kind=ev["kind"], title=ev["title"],
                        details=ev["details"], ref_table=ev["ref_table"],
                        ref_key=ev["ref_key"],
                    ))
                if events:
                    self._timeline_repo.add_many(events)
                    self.timelineChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Failed to update process history")
        self.collectorHealthChanged.emit()

    # ---- UI API --------------------------------------------------------
    def last_result(self, collector_name: str) -> CollectorResult | None:
        """Latest CollectorResult for a collector — provenance for the UI."""
        return self._last_results.get(collector_name)

    def applications(self):
        try:
            return self._app_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read applications")
            return []

    def tool_locations(self):
        try:
            return self._tool_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read tool locations")
            return []

    def ai_tools(self):
        try:
            return self._aitool_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read AI tools")
            return []

    def ai_models(self):
        try:
            return self._aimodel_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read AI models")
            return []

    def listening_ports(self):
        try:
            return self._port_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read ports")
            return []

    def services(self):
        try:
            return self._service_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read services")
            return []

    def startup_items(self):
        try:
            return self._startup_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read startup items")
            return []

    def scheduled_tasks(self):
        try:
            return self._task_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read scheduled tasks")
            return []

    def recent_events(self, limit: int = 400, level: str | None = None,
                      since_ts: float | None = None):
        try:
            return self._event_repo.recent(limit, level=level, since_ts=since_ts)
        except Exception:  # noqa: BLE001
            log.exception("Failed to read events")
            return []

    def scripts(self):
        try:
            return self._script_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read scripts")
            return []

    def script_runs(self, limit: int = 200, script_path: str | None = None,
                    since_ts: float | None = None):
        try:
            return self._scriptrun_repo.recent(limit, script_path=script_path,
                                               since_ts=since_ts)
        except Exception:  # noqa: BLE001
            log.exception("Failed to read script runs")
            return []

    def open_script_runs(self):
        try:
            return self._scriptrun_repo.open_runs()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read open script runs")
            return []

    def global_search(self, query: str) -> dict[str, list]:
        """One input, everything: apps, tools, AI models, scripts, tasks,
        services, startup entries, and projects. Grouped by category.
        Case-insensitive substring match on each inventory's natural key."""
        q = (query or "").strip().lower()
        if not q:
            return {}
        out: dict[str, list] = {}
        try:
            out["Applications"] = [
                a for a in self._app_repo.all()
                if q in a.name.lower() or q in a.publisher.lower()
                or q in a.install_location.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Applications"] = []
        try:
            out["Tool Locations"] = [
                t for t in self._tool_repo.all()
                if q in t.tool.lower() or q in t.exe_path.lower()
                or q in t.install_dir.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Tool Locations"] = []
        try:
            models = [m for m in self._aimodel_repo.all()
                      if q in m.name.lower() or q in m.runtime.lower()][:20]
            tools = [t for t in self._aitool_repo.all()
                     if q in t.name.lower() or q in t.exe_path.lower()][:20]
            out["AI & Models"] = tools + models
        except Exception:  # noqa: BLE001
            out["AI & Models"] = []
        try:
            out["Scripts"] = [
                s for s in self._script_repo.all()
                if q in s.name.lower() or q in s.path.lower()
                or q in s.project.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Scripts"] = []
        try:
            out["Scheduled Tasks"] = [
                t for t in self._task_repo.all()
                if q in t.task_path.lower() or q in t.action_exe.lower()
                or q in t.action_args.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Scheduled Tasks"] = []
        try:
            out["Services"] = [
                s for s in self._service_repo.all()
                if q in s.name.lower() or q in s.display_name.lower()
                or q in s.description.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Services"] = []
        try:
            out["Startup"] = [
                s for s in self._startup_repo.all()
                if q in s.entry_name.lower() or q in s.command.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Startup"] = []
        try:
            out["Python Projects"] = [
                p for p in self._project_repo.all()
                if q in p.name.lower() or q in p.path.lower()][:20]
        except Exception:  # noqa: BLE001
            out["Python Projects"] = []
        return {k: v for k, v in out.items() if v}

    def python_projects(self):
        try:
            return self._project_repo.all()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read projects")
            return []

    def recent_processes(self, limit: int = 300):
        """First/last-seen history rows, newest activity first."""
        try:
            return self._process_repo.recent(limit)
        except Exception:  # noqa: BLE001
            log.exception("Failed to read process history")
            return []

    def live_interpreter_processes(self) -> list[dict]:
        """Python/PowerShell processes running RIGHT NOW, with redacted
        command lines. Read directly via psutil (one fresh snapshot), so the
        Assistant always answers from the live state, not the last poll."""
        import psutil
        from ..utils.redact import redact_cmdline
        out: list[dict] = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = (proc.info['name'] or '').lower()
                if not name.startswith(('python', 'pwsh', 'powershell')):
                    continue
                out.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cmdline': redact_cmdline(list(proc.info['cmdline'] or [])),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out

    def timeline_events(self, limit: int = 400, kind: str | None = None,
                        since_ts: float | None = None):
        """Chronological events (newest first) with optional filters."""
        try:
            return self._timeline_repo.latest(limit, kind=kind, since_ts=since_ts)
        except Exception:  # noqa: BLE001
            log.exception("Failed to read timeline")
            return []

    def record_manual_event(self, title: str, details: str = "",
                            kind: str = "manual") -> None:
        """User-added timeline note (one home for later phases too)."""
        try:
            self._timeline_repo.add(TimelineEvent(
                ts=time.time(), kind=kind, title=title, details=details))
            self.timelineChanged.emit()
        except Exception:  # noqa: BLE001
            log.exception("Failed to record manual event")
    def chart_window(self, seconds: float) -> list[MetricSample]:
        return self._buffer.window(seconds)

    def latest_sample(self) -> MetricSample | None:
        return self._buffer.latest()

    def latest_system_info(self) -> SystemInfo | None:
        return self._system_repo.latest()

    def collector_health(self) -> dict[str, tuple[str, str, float]]:
        """collector name -> (status, detail, started_at) from the audit table."""
        try:
            return self._runs_repo.latest_per_collector()
        except Exception:  # noqa: BLE001
            log.exception("Failed to read collector health")
            return {}

    # ---- housekeeping --------------------------------------------------
    def _apply_retention(self) -> None:
        cutoff = time.time() - self._config.retention_days * 86400
        try:
            self._metrics_repo.delete_before(cutoff)
            self._runs_repo.delete_before(cutoff)
            self._process_repo.delete_before(cutoff)
            self._timeline_repo.delete_before(cutoff)
            self._scriptrun_repo.delete_before(cutoff)
        except Exception:  # noqa: BLE001
            log.exception("Retention cleanup failed")

    def apply_retention(self) -> None:
        """Public hook for the Settings page ('Apply and clean up now')."""
        self._apply_retention()

    def restart_workers(self, config: AppConfig) -> None:
        """Restart background workers after interval changes (Settings page)."""
        self._scheduler.shutdown()
        self._config = config
        self._connect_workers()

    def shutdown(self) -> None:
        self._scheduler.shutdown()
