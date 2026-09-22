"""LiveChart — a rolling time-series chart on pyqtgraph.

One instance can draw several curves (e.g. upload + download). Data arrives
as lists of MetricSample from the MetricBuffer; the chart never touches
psutil or the database itself.

Cold-start note: this module imports pyqtgraph at module level, which is
fine because it is only imported inside main.py's background import phase
(while the splash is up). Nothing may import this module after the main
window is visible — Qt objects must not be created late from odd contexts.
"""
from __future__ import annotations

from typing import Callable

import pyqtgraph as pg

from ..models.metrics import MetricSample
from ..utils.format import fmt_time

pg.setConfigOptions(antialias=True, background="transparent", foreground="#7a8494")


class LiveChart(pg.PlotWidget):
    """Rolling chart fed by (timestamps, values) pairs."""

    def __init__(
        self,
        title: str,
        series: list[tuple[str, str]],   # (label, color)
        y_label: str,
        x_from_sample: Callable[[MetricSample], float],
        y_from_sample: list[Callable[[MetricSample], float]] | None = None,
        y_limits: tuple[float | None, float | None] = (None, None),
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._x_from = x_from_sample
        self._getters = y_from_sample or []

        self.setTitle(title, size="10pt", color="#9aa4b1")
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.hideButtons()
        self.getPlotItem().setContentsMargins(6, 10, 6, 4)

        axis = self.getAxis("bottom")
        axis.setLabel("")
        axis.setTicks([])  # replaced per draw; simple tick builder below

        self.getAxis("left").setLabel(y_label)
        self.showGrid(x=True, y=True, alpha=0.25)
        if y_limits != (None, None):
            self.setYRange(y_limits[0] or 0, y_limits[1] or 1, padding=0.02)

        self._curves = []
        for label, color in series:
            curve = self.plot(pen=pg.mkPen(color, width=2), name=label)
            self._curves.append(curve)
        if len(self._curves) > 1:
            legend = self.addLegend(offset=(6, 6))
            legend.setLabelTextColor("#9aa4b1")

        self._x: list[float] = []
        self._ys: list[list[float]] = [[] for _ in self._curves]

    def update_samples(self, samples: list[MetricSample]) -> None:
        if not self._getters:
            return
        self._x = [self._x_from(s) for s in samples]
        for idx, getter in enumerate(self._getters):
            self._ys[idx] = [getter(s) for s in samples]
            self._curves[idx].setData(self._x, self._ys[idx])
        self._apply_time_axis()

    def _apply_time_axis(self) -> None:
        """Human-friendly HH:MM:SS ticks along the bottom axis."""
        if not self._x:
            return
        t0, t1 = self._x[0], self._x[-1]
        if t1 - t0 < 1:
            return
        step = max(1, int((t1 - t0) / 5))
        ticks = [[(t, fmt_time(t)) for t in range(int(t0), int(t1) + 1, step)]]
        self.getAxis("bottom").setTicks(ticks)
