"""Secret redaction for command lines (spec §6 and §49).

Processes are sometimes launched with secrets on their command line, e.g.
``tool --api-key=sk-...``. PC Observatory shows command lines for learning,
but it must never store or display a secret. This module rewrites any
argument that looks like it carries a credential before the value can reach
the UI or the database. When in doubt — hide. Hiding a harmless flag value
costs nothing; exposing a key would be a real failure.
"""
from __future__ import annotations

import re

# Matches credential-ish words as whole tokens: 'api-key', 'token', 'PWD'…
# but not ordinary words that merely contain them ('keyboard', 'authorize').
_SECRET_WORD = re.compile(
    r"(?:^|[^a-z0-9])"
    r"(password|passwd|pwd|token|secret|api[-_]?key|auth|credential|private[-_]?key)"
    r"(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)

HIDDEN = "[SENSITIVE VALUE HIDDEN]"


def _is_secret_flag(part: str) -> bool:
    """True for flag-style args like --api-key, /TOKEN:, -p (only if named)."""
    return bool(_SECRET_WORD.search(part))


def redact_cmdline(parts: list[str]) -> str:
    """Redact secret values in a command line before display or storage.

    Handles the two common shapes:
      --api-key=VALUE     -> --api-key=[SENSITIVE VALUE HIDDEN]
      --api-key VALUE     -> --api-key [SENSITIVE VALUE HIDDEN]
    Bare values are kept unless the previous flag was credential-ish.
    """
    out: list[str] = []
    hide_next = False
    for part in parts:
        if hide_next and not part.startswith("-"):
            out.append(HIDDEN)
            hide_next = False
            continue
        hide_next = False
        if _is_secret_flag(part):
            if "=" in part:
                flag, _value = part.split("=", 1)
                out.append(f"{flag}={HIDDEN}")
            else:
                out.append(part)
                hide_next = True
            continue
        out.append(part)
    return " ".join(out)
