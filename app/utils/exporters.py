"""Export helpers (spec §51): CSV, JSON, and a self-contained HTML report.

Exports never contain secrets — the data passed in is already the redacted,
user-visible data from the UI.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


def _export_dir() -> Path:
    from ..config.settings import project_root
    d = project_root() / "exports"
    d.mkdir(exist_ok=True)
    return d


def export_csv(headers: list[str], rows: list[list[str]], name: str) -> Path:
    path = _export_dir() / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def export_json(payload, name: str) -> Path:
    path = _export_dir() / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def export_html(title: str, sections: list[tuple[str, list[str], list[list[str]]]],
                name: str) -> Path:
    """sections: list of (heading, headers, rows). One self-contained file."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>", title, "</title><style>",
        "body{font-family:'Segoe UI',sans-serif;margin:2rem;color:#222}",
        "h1{font-size:1.4rem} h2{font-size:1.1rem;margin-top:2rem}",
        "table{border-collapse:collapse;width:100%;font-size:.85rem}",
        "th,td{border:1px solid #ccc;padding:4px 8px;text-align:left}",
        "th{background:#f0f2f5} .meta{color:#666;font-size:.8rem}",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        f"<p class='meta'>Generated locally by PC Observatory — "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}</p>",
    ]
    for heading, headers, rows in sections:
        parts.append(f"<h2>{heading}</h2><table><tr>")
        parts.extend(f"<th>{h}</th>" for h in headers)
        parts.append("</tr>")
        for row in rows:
            parts.append("<tr>")
            parts.extend(f"<td>{cell}</td>" for cell in row)
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    path = _export_dir() / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path
