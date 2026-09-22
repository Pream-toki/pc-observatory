"""EventLogCollector — incremental Windows event reads (spec §23-24).

Strategy: keep the newest timestamp already stored; query only events newer
than that (incremental polling — no huge repeated loads). Queries run through
wevtutil with a fixed argument list; an XPath time filter is built from the
stored timestamp using System.TimeCreated — the query string contains data
from our own database only, never user input.

Security log without admin rights returns permission errors → the collector
reports PARTIAL and the UI says 'Permission required' honestly.
"""
from __future__ import annotations

import json
import logging
import subprocess  # noqa: S404 - fixed argument list, read-only query
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

from ..models.metrics import CollectorResult, CollectorStatus
from ..database.ops_repositories import EventRepository
from .base import BaseCollector

log = logging.getLogger(__name__)

_LOGS = ["System", "Application"]
_MAX_EVENTS_PER_LOG = 300


def _level_name(level: int | None) -> str:
    return {1: "Critical", 2: "Error", 3: "Warning", 4: "Information",
            0: "Information", 5: "Verbose"}.get(level or 0, f"Level {level}")


def _query_log(log_name: str, since_ts: float | None) -> tuple[list[dict], str | None]:
    """Returns (events, error). error is None on full success."""
    xpath = "*"
    if since_ts:
        start = datetime.fromtimestamp(since_ts + 1, tz=timezone.utc)
        xpath = (f"*[System[TimeCreated[@SystemTime>='{start.isoformat().replace('+00:00', 'Z')}']]]")
    cmd = [
        "wevtutil", "qe", log_name,
        f"/query:{xpath}",
        f"/count:{_MAX_EVENTS_PER_LOG}",
        "/rd:true", "/format:xml",
    ]
    proc = None
    for attempt in (1, 2):  # one retry: wevtutil can fail transiently under load
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=60, shell=False, check=False,
                                  errors="replace")
        except (subprocess.SubprocessError, OSError) as exc:
            return [], str(exc)
        if proc.returncode == 0:
            break
        if attempt == 1:
            time.sleep(1.0)
    if proc is None or proc.returncode != 0:
        err = (proc.stderr or "").strip() if proc is not None else ""
        if not err:
            rc = proc.returncode if proc is not None else -1
            err = f"wevtutil exited with code {rc} (no error text; usually transient)"
        return [], err
    events: list[dict] = []
    try:
        for chunk in proc.stdout.split("</Event>"):
            chunk = chunk.strip()
            if "<Event" not in chunk:
                continue
            xml_text = chunk[chunk.index("<Event"):] + "</Event>"
            root = ElementTree.fromstring(xml_text)
            ns = {"e": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            system = root.find("e:System", ns) if ns else root.find("System")

            def txt(parent, tag: str) -> str:
                if parent is None:
                    return ""
                el = parent.find(f"e:{tag}", ns) if ns else parent.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""

            time_el = (system.find("e:TimeCreated", ns) if ns
                       else system.find("TimeCreated")) if system is not None else None
            ts = time.time()
            if time_el is not None:
                raw = time_el.get("SystemTime", "")
                try:
                    ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            level_el = (system.find("e:Level", ns) if ns
                        else system.find("Level")) if system is not None else None
            try:
                level_val = int(level_el.text) if level_el is not None and level_el.text else 0
            except ValueError:
                level_val = 0
            id_el = (system.find("e:EventID", ns) if ns
                     else system.find("EventID")) if system is not None else None
            try:
                event_id = int(id_el.text) if id_el is not None and id_el.text else 0
            except ValueError:
                event_id = 0
            # Message: RenderingInfo may be absent; keep provider + id as title.
            message = txt(root.find("e:RenderingInfo", ns) if ns
                          else root.find("RenderingInfo"), "Message") or \
                      f"{txt(system, 'Provider') if system is not None else ''} event {event_id}"
            events.append({
                "ts": ts,
                "log_name": log_name,
                "provider": txt(system, "Provider") if system is not None else "",
                "event_id": event_id,
                "level": _level_name(level_val),
                "message": message,
            })
    except ElementTree.ParseError as exc:
        return events, f"XML parse issue: {exc}"
    return events, None


class EventLogCollector(BaseCollector):
    label = "Event Logs"

    def __init__(self, run_repo=None, event_repo: EventRepository | None = None) -> None:
        super().__init__(run_repo)
        self._event_repo = event_repo or EventRepository()
        self._last_ts: float | None = None

    def collect(self) -> CollectorResult:
        if self._last_ts is None:
            latest = self._event_repo.recent(limit=1)
            self._last_ts = latest[0].ts if latest else time.time() - 900
        all_events: list[dict] = []
        errors: list[str] = []
        for log_name in _LOGS:
            events, error = _query_log(log_name, self._last_ts)
            all_events.extend(events)
            if error:
                errors.append(f"{log_name}: {error}")
        if all_events:
            try:
                self._event_repo.insert_many(all_events)
                self._last_ts = max(e["ts"] for e in all_events)
            except Exception:  # noqa: BLE001
                log.exception("Failed to persist events")
        status = CollectorStatus.SUCCESS
        if errors:
            status = CollectorStatus.PARTIAL if all_events else CollectorStatus.PERMISSION_DENIED \
                if "Access is denied" in "; ".join(errors) else CollectorStatus.ERROR
        return CollectorResult(
            status=status,
            data=all_events,
            detail="; ".join(errors[:2]),
            meta=self._meta(
                source="Windows Event Log via wevtutil (read-only query)",
                method=(
                    "Reads the System and Application event logs incrementally — "
                    "only events newer than the newest one already stored, capped "
                    "at 300 per log per poll, so nothing heavy repeats. The "
                    "Security log needs administrator rights; when it is denied, "
                    "the app shows 'Permission required' instead of pretending. "
                    "Read-only; events are never modified or cleared."
                ),
            ),
        )
