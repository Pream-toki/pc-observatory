"""Dashboard — the live overview page.

Layout: metric cards (top), system fact cards (middle), four live charts with
a time-range selector, and the collector health strip (bottom). All data
arrives through SystemService signals; the page never touches psutil or SQL.

Honest-display note: CPU and Memory get 0-100% progress bars because those
percentages are real. Disk and Network show plain speeds (a bar would need an
invented maximum, and this app does not invent scales).
"""
from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...config.settings import CHART_RANGES_S
from ...models.metrics import CollectorResult, MetricSample, SystemInfo
from ...services.service import SystemService
from ...utils.format import (
    fmt_bytes_per_sec,
    fmt_duration,
    fmt_gb,
    fmt_percent,
)
from ...widgets.cards import MetricCard, StatCard
from ...widgets.charts import LiveChart
from ...widgets.health_strip import CollectorHealthStrip

_METRICS = "MetricsCollector"
_SYSTEM = "SystemCollector"
_GPU = "GpuCollector"

_RANGE_LABELS = {30: "30 seconds", 60: "1 minute", 300: "5 minutes", 1800: "30 minutes"}


class DashboardPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._range_s = 60  # selected chart window

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 18, 24, 18)
        root_layout.setSpacing(14)

        # ---- live metric cards ---------------------------------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self._cpu_card = MetricCard("CPU")
        self._ram_card = MetricCard("Memory")
        self._disk_card = StatCard("Disk Activity")
        self._net_card = StatCard("Network")
        for card in (self._cpu_card, self._ram_card, self._disk_card, self._net_card):
            top_row.addWidget(card, 1)
        root_layout.addLayout(top_row)

        # ---- system fact cards (3 per row so nothing gets truncated) --------
        facts_grid = QGridLayout()
        facts_grid.setSpacing(12)
        self._host_card = StatCard("Hostname")
        self._os_card = StatCard("Windows")
        self._uptime_card = StatCard("Uptime")
        self._gpu_card = StatCard("GPU")
        self._procs_card = StatCard("Processes")
        self._ports_card = StatCard("Listening Ports")
        fact_cards = (self._host_card, self._os_card, self._uptime_card,
                      self._gpu_card, self._procs_card, self._ports_card)
        for idx, card in enumerate(fact_cards):
            facts_grid.addWidget(card, idx // 3, idx % 3)
        root_layout.addLayout(facts_grid)

        # ---- top processes right now (from the 5 s process poll) ------------
        self._top_card = StatCard("Top Processes Now")
        self._top_card.set_value("—", sub="Waiting for the first process poll…")
        root_layout.addWidget(self._top_card)
        self._service.processesUpdated.connect(self._on_processes_top)

        # ---- charts + time range selector ------------------------------------
        charts_row = QHBoxLayout()
        charts_row.setSpacing(8)
        range_label = QLabel("Time range")
        range_label.setObjectName("CardSub")
        self._range_combo = QComboBox()
        for seconds in CHART_RANGES_S:
            self._range_combo.addItem(_RANGE_LABELS.get(seconds, f"{seconds} s"), userData=seconds)
        self._range_combo.setCurrentIndex(1)
        self._range_combo.currentIndexChanged.connect(self._on_range_changed)
        charts_row.addWidget(range_label)
        charts_row.addWidget(self._range_combo)
        charts_row.addStretch(1)
        root_layout.addLayout(charts_row)

        self._cpu_chart = LiveChart(
            "CPU utilization (%)",
            [("CPU %", "#4f8cff")],
            "%",
            x_from_sample=lambda s: s.ts,
            y_from_sample=[lambda s: s.cpu_percent],
            y_limits=(0, 100),
        )
        self._ram_chart = LiveChart(
            "Memory used (GB)",
            [("Used GB", "#4cc38a")],
            "GB",
            x_from_sample=lambda s: s.ts,
            y_from_sample=[lambda s: s.ram_used_gb],
        )
        self._disk_chart = LiveChart(
            "Disk activity (MB/s)",
            [("Read", "#e5b567"), ("Write", "#e5484d")],
            "MB/s",
            x_from_sample=lambda s: s.ts,
            y_from_sample=[lambda s: s.disk_read_mb_s, lambda s: s.disk_write_mb_s],
        )
        self._net_chart = LiveChart(
            "Network throughput (MB/s)",
            [("Up", "#4f8cff"), ("Down", "#4cc38a")],
            "MB/s",
            x_from_sample=lambda s: s.ts,
            y_from_sample=[lambda s: s.net_up_mb_s, lambda s: s.net_down_mb_s],
        )
        charts_grid = QGridLayout()
        charts_grid.setSpacing(12)
        charts_grid.addWidget(self._cpu_chart, 0, 0)
        charts_grid.addWidget(self._ram_chart, 0, 1)
        charts_grid.addWidget(self._disk_chart, 1, 0)
        charts_grid.addWidget(self._net_chart, 1, 1)
        root_layout.addLayout(charts_grid, 1)

        # ---- collector health strip -------------------------------------------
        self._health = CollectorHealthStrip()
        root_layout.addWidget(self._health)

        # ---- wiring -------------------------------------------------------------
        self._service.metricsUpdated.connect(self._on_metrics)
        self._service.systemInfoUpdated.connect(self._on_system_info)
        self._service.gpuUpdated.connect(self._on_gpu)
        self._service.collectorHealthChanged.connect(self._on_health)
        self._on_health()
        self._refresh_charts()
        self._gpu_card.set_value("—", sub="Waiting for first GPU sample…")

    # ---- slots ------------------------------------------------------------
    def _on_metrics(self, sample: MetricSample) -> None:
        self._cpu_card.set_percent(sample.cpu_percent)
        self._ram_card.set_percent(
            sample.ram_percent,
            text=f"{fmt_gb(sample.ram_used_gb)} ({fmt_percent(sample.ram_percent)})",
        )
        total_disk_mb_s = sample.disk_read_mb_s + sample.disk_write_mb_s
        self._disk_card.set_value(
            fmt_bytes_per_sec(total_disk_mb_s),
            sub=f"read {fmt_bytes_per_sec(sample.disk_read_mb_s)} · "
                f"write {fmt_bytes_per_sec(sample.disk_write_mb_s)}",
        )
        self._net_card.set_value(
            f"↓ {fmt_bytes_per_sec(sample.net_down_mb_s)}",
            sub=f"↑ {fmt_bytes_per_sec(sample.net_up_mb_s)}",
        )
        self._procs_card.set_value(str(sample.process_count))
        self._ports_card.set_value(str(sample.listening_ports))
        self._cpu_card.set_result(self._service.last_result(_METRICS))
        self._ram_card.set_result(self._service.last_result(_METRICS))
        self._disk_card.set_result(self._service.last_result(_METRICS))
        self._net_card.set_result(self._service.last_result(_METRICS))
        self._procs_card.set_result(self._service.last_result(_METRICS))
        self._ports_card.set_result(self._service.last_result(_METRICS))
        self._refresh_charts()

    def _on_processes_top(self, infos: list) -> None:
        """Live 'who is eating the CPU' card — zero extra collection cost,
        it rides the existing 5 s process poll."""
        if not infos:
            return
        by_cpu = sorted(
            (p for p in infos if p.cpu_percent is not None and p.cpu_percent > 0.1),
            key=lambda p: p.cpu_percent, reverse=True)[:3]
        by_mem = sorted(
            (p for p in infos if p.mem_mb is not None),
            key=lambda p: p.mem_mb, reverse=True)[:1]
        if not by_cpu and not by_mem:
            self._top_card.set_value("All quiet", sub="No process above 0.1% CPU")
            return
        lines = [f"{p.name}  {p.cpu_percent:.0f}% CPU · {p.mem_mb or 0:.0f} MB"
                 for p in by_cpu]
        if by_mem:
            m = by_mem[0]
            lines.append(f"{m.name}  {m.mem_mb:.0f} MB (top memory)")
        self._top_card.set_value(lines[0].split("  ")[0],
                                 sub="\n".join(lines))
        self._top_card.set_result(self._service.last_result("ProcessCollector"))

    def _on_system_info(self, info: SystemInfo) -> None:
        self._host_card.set_value(info.hostname, sub=info.current_user)
        self._os_card.set_value(
            info.os_name, sub=f"{info.os_version} · {info.architecture}"
        )
        self._uptime_card.set_value(
            fmt_duration(time.time() - info.boot_time) if info.boot_time else "Unavailable"
        )
        self._cpu_card.set_sub(
            f"{info.cpu_cores_logical} logical cores · {info.cpu_cores_physical} physical"
        )
        result = self._service.last_result(_SYSTEM)
        for card in (self._host_card, self._os_card, self._uptime_card):
            card.set_result(result)

    def _on_gpu(self, result: CollectorResult) -> None:
        if result.ok and isinstance(result.data, dict):
            data = result.data
            mem_txt = ""
            if data.get("memory_used_mb") is not None and data.get("memory_total_mb"):
                mem_txt = (f"{data['memory_used_mb'] / 1024:.1f} / "
                           f"{data['memory_total_mb'] / 1024:.1f} GB memory")
            util = data.get("utilization_percent")
            util_txt = f" · {util:.0f}% utilization" if util is not None else ""
            self._gpu_card.set_value(data.get("name", "GPU"), sub=(mem_txt + util_txt).strip(" ·"))
        else:
            self._gpu_card.set_value("Unavailable", sub=result.detail or result.status.value)
        self._gpu_card.set_result(result)

    def _on_health(self) -> None:
        self._health.sync(self._service.collector_health())

    def _on_range_changed(self, index: int) -> None:
        self._range_s = self._range_combo.itemData(index)
        self._refresh_charts()

    def _refresh_charts(self) -> None:
        samples = self._service.chart_window(self._range_s)
        for chart in (self._cpu_chart, self._ram_chart, self._disk_chart, self._net_chart):
            chart.update_samples(samples)
