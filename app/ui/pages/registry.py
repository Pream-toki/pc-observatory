"""Page registry — maps sidebar ids to page factories.

Sidebar navigation entries only appear for pages that exist. In Phase 1 that
is Dashboard and Settings; each later phase registers its page here once it
is actually implemented.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .ai_page import AiPage
from .applications_page import ApplicationsPage
from .assistant_page import AssistantPage
from .automation_page import AutomationPage
from .changes_page import ChangesPage
from .dashboard import DashboardPage
from .events_page import EventsPage
from .network_page import NetworkPage
from .processes_page import ProcessesPage
from .projects_page import ProjectsPage
from .scripts_page import ScriptsPage
from .search_page import SearchPage
from .settings_page import SettingsPage
from .timeline_page import TimelinePage
from .tools_page import ToolsPage

# (page_id, section, title, subtitle, factory)
# Factories receive (service, config) and return the page widget.
PAGES: list[tuple[str, str, str, str, object]] = [
    (
        "dashboard", "Overview", "Dashboard",
        "Live view of your PC — real data, updated in the background.",
        DashboardPage,
    ),
    (
        "search", "Overview", "Search",
        "Type once, find anything: apps, tools, models, scripts, tasks, services.",
        SearchPage,
    ),
    (
        "timeline", "Overview", "Timeline",
        "What happened on your PC — boots and programs starting, newest first.",
        TimelinePage,
    ),
    (
        "applications", "Software", "Applications",
        "Everything installed on this PC — version, publisher, install location.",
        ApplicationsPage,
    ),
    (
        "tools", "Software", "Tool Locations",
        "Where your development and AI tools actually live, plus a command resolver.",
        ToolsPage,
    ),
    (
        "ai", "Software", "AI & Models",
        "Local AI tools (Ollama, LM Studio, …) and the model files on your disk.",
        AiPage,
    ),
    (
        "processes", "Security", "Processes",
        "Every running program, searchable — updated every few seconds.",
        ProcessesPage,
    ),
    (
        "network", "Security", "Network",
        "Which programs are listening on which ports — local observation only.",
        NetworkPage,
    ),
    (
        "events", "Security", "Events",
        "Recent Windows event log entries with plain-language context.",
        EventsPage,
    ),
    (
        "automation", "Automation", "Automation Center",
        "Services, startup entries, and scheduled tasks — the full catalog.",
        AutomationPage,
    ),
    (
        "scripts", "Automation", "My Automations",
        "Your scripts: what runs, when, with what — and what triggers each one.",
        ScriptsPage,
    ),
    (
        "projects", "Development", "Python Projects",
        "Your detected Python projects, environments, and Git folders.",
        ProjectsPage,
    ),
    (
        "changes", "History", "Changes & Snapshots",
        "Take a snapshot, then see exactly what changed since — and export reports.",
        ChangesPage,
    ),
    (
        "assistant", "Assistant", "Assistant",
        "Ask questions about your PC — answered locally by your own Ollama.",
        AssistantPage,
    ),
    (
        "settings", "Settings", "Settings",
        "Appearance, collection intervals, and data retention.",
        SettingsPage,
    ),
]


def create_page(page_id: str, service, config) -> QWidget | None:
    for pid, _section, _title, _subtitle, factory in PAGES:
        if pid == page_id:
            return factory(service, config)  # type: ignore[operator]
    return None
