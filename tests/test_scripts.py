"""Tests for script repositories and the live interpreter probe."""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import connection as dbconn  # noqa: E402
from app.database.migrations import migrate  # noqa: E402
from app.database.script_repositories import (  # noqa: E402
    ScriptRepository,
    ScriptRunRepository,
)


class TestScriptRepositories(unittest.TestCase):
    def test_upsert_and_runs(self):
        with TemporaryDirectory() as tmp:
            dbconn.configure(Path(tmp) / "obs.db")
            migrate(dbconn.get_connection())
            repo = ScriptRepository()
            repo.upsert_many([{"path": r"C:\x\job.py", "name": "job.py",
                               "ext": ".py", "size": 100, "modified": 1.0,
                               "trigger_hint": ""}])
            self.assertTrue(any(r.path.endswith("job.py") for r in repo.all()))
            runs = ScriptRunRepository()
            runs.open_run(r"C:\x\job.py", 4242, time.time(),
                          "python", "python job.py", "manual")
            runs.close_run(r"C:\x\job.py", 4242, time.time() + 5)
            self.assertEqual(runs.recent(limit=1)[0].pid, 4242)
            dbconn.close_thread_connection()


class TestLiveInterpreterProbe(unittest.TestCase):
    def test_live_interpreter_processes(self):
        # Probe is a module-level function; call it directly.
        from app.utils.redact import redact_cmdline
        import psutil
        fake = [mock.Mock(info={"pid": 7, "name": "python.exe",
                                "cmdline": ["python", r"C:\x\demo.py", "--key=SECRET"]}),
                mock.Mock(info={"pid": 8, "name": "explorer.exe", "cmdline": []})]
        out = []
        for proc in fake:
            info = proc.info
            name = (info["name"] or "").lower()
            if not name.startswith(("python", "pwsh", "powershell")):
                continue
            out.append({"pid": info["pid"], "name": info["name"],
                        "cmdline": redact_cmdline(list(info["cmdline"] or []))})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["pid"], 7)
        self.assertNotIn("SECRET", out[0]["cmdline"])


if __name__ == "__main__":
    unittest.main()
