"""Local-only AI assistant client (spec §42, respecting §3 LOCAL FIRST).

Talks exclusively to the user's own Ollama server on 127.0.0.1 — the same
machine, no cloud, no external endpoints, ever. Cloud providers are NOT
implemented by design (privacy first). The assistant receives a compact,
structured slice of observed data, never the whole database, and never any
secret values (command lines are pre-redacted upstream).

Reliability notes (why the Assistant "did not work" before):
- The Ollama *server* is not always running when PC Observatory starts —
  Windows only starts it when the user opens the Ollama app. A squatting
  process (e.g. WSL's wslrelay) can even listen on 11434 and answer /api/tags
  while refusing real API calls, so availability is verified with a version
  handshake, not just a socket check.
- The default model must be one the user has actually pulled; requesting an
  unpulled model is a 404. The client therefore picks the first available
  model from /api/tags at call time.
- First use of a big model loads it into RAM and can exceed a minute on
  CPU; the chat timeout is generous and the UI reports progress honestly.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_HOST = "http://127.0.0.1:11434"
_TIMEOUT = 300  # first call of a big model on CPU can be slow


def _get(path: str, timeout: float) -> object:
    with urllib.request.urlopen(f"{_HOST}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_available() -> tuple[bool, str]:
    """True only when the real Ollama API answers a version handshake."""
    try:
        _get("/api/version", timeout=4)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = str(getattr(exc, "reason", exc))[:120]
        return False, reason
    try:
        models = _get("/api/tags", timeout=6).get("models", [])
        names = [m.get("name", "?") for m in models]
        if not names:
            return False, "server running but no models pulled"
        return True, ", ".join(names[:8])
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(exc)[:120]


def _pick_model() -> str:
    """Prefer small/fast known models the user actually has; else first."""
    try:
        names = [m.get("name", "") for m in _get("/api/tags", timeout=6).get("models", [])]
    except Exception:  # noqa: BLE001
        return "qwen2.5-coder:7b"
    for want in ("qwen2.5-coder:7b", "gemma:latest", "llama3.2:latest"):
        for n in names:
            if n == want or n.split(":")[0] == want.split(":")[0]:
                return n
    return names[0] if names else "qwen2.5-coder:7b"


def ask(prompt: str, context: str, model: str | None = None) -> tuple[str, str]:
    """Ask the local model. Returns (answer, error)."""
    chosen = model or _pick_model()
    payload = json.dumps({
        "model": chosen,
        "messages": [
            {"role": "system",
             "content": (
                 "You are PC Observatory Assistant, helping the user understand "
                 "their own Windows PC. You receive OBSERVED DATA collected from "
                 "their machine. Stick to the data; never claim malware without "
                 "strong evidence; use neutral language (Normal / Unknown / Needs "
                 "Review). Be concise. If the data does not answer the question, "
                 "say what is missing."
             )},
            {"role": "user",
             "content": f"OBSERVED DATA:\n{context}\n\nQUESTION: {prompt}"},
        ],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{_HOST}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            answer = json.loads(resp.read().decode("utf-8"))
            return str(answer.get("message", {}).get("content", "")).strip(), ""
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "", (f"Model '{chosen}' is not pulled in Ollama (404). "
                        "Pull it with: ollama pull " + chosen)
        return "", f"Ollama returned HTTP {exc.code}."
    except urllib.error.URLError as exc:
        return "", (f"Could not reach Ollama on 127.0.0.1:11434 "
                    f"({exc.reason}). Start the Ollama app, then try again.")
    except (OSError, ValueError) as exc:
        return "", f"Unexpected local AI error: {exc}"
