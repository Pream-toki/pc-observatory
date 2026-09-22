"""AiCollector — local AI tools and models (spec §27).

Detects well-known local AI software (Ollama, LM Studio, Jan, GPT4All) and
inventories model files in their standard storage directories. Only *reads
file listings and sizes* — never uploads anything, never executes models,
and stays inside the documented model directories (no whole-disk scan).

Model formats inventoried: GGUF/GGML (Ollama, LM Studio, GPT4All, Jan),
safetensors (HuggingFace-style local caches).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ..models.inventory import AiModel, AiTool
from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector
from .tools import _search_dirs  # shared expanders

log = logging.getLogger(__name__)

_TOOL_DEFS = [
    ("Ollama", "ollama.exe", [r"%LocalAppData%\Programs\Ollama"]),
    ("LM Studio", "LM Studio.exe", [r"%LocalAppData%\LM-Studio", r"%ProgramFiles%\LM Studio"]),
    ("Jan", "jan.exe", [r"%LocalAppData%\Programs\Jan"]),
    ("GPT4All", "gpt4all.exe", [r"%LocalAppData%\Programs\GPT4All", r"%LocalAppData%\GPT4All"]),
]

_MODEL_EXTENSIONS = (".gguf", ".ggml", ".safetensors")

# Documented per-tool model directories (expanded + globbed).
_MODEL_DIRS = {
    "Ollama": [r"%USERPROFILE%\.ollama\models"],
    "LM Studio": [r"%USERPROFILE%\.lmstudio\models", r"%USERPROFILE%\.cache\lm-studio\models"],
    "Jan": [r"%USERPROFILE%\jan\models", r"%APPDATA%\Jan\data\models"],
    "GPT4All": [r"%LOCALAPPDATA%\nomic.ai\GPT4All", r"%USERPROFILE%\.cache\gpt4all"],
}


def _iter_model_files(root: Path):
    """Yield model files under root, with a depth+count cap (never a full-disk scan)."""
    if not root.is_dir():
        return
    max_files = 500
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip heavyweight irrelevant trees
        dirnames[:] = [d for d in dirnames if d not in (".git", "tmp")]
        for filename in filenames:
            if filename.lower().endswith(_MODEL_EXTENSIONS):
                yield Path(dirpath) / filename
                count += 1
                if count >= max_files:
                    log.warning("Model scan capped at %d files under %s", max_files, root)
                    return


def _friendly_model_name(path: Path) -> str:
    return path.stem


def _ollama_models() -> list[AiModel]:
    """Parse Ollama's manifest store: one small JSON per model under
    ~/.ollama/models/manifests/<registry>/<ns>/<model>/<tag>. The real model
    size lives in the JSON 'layers' entry with the image.model media type —
    no need to stat the multi-GB blobs at all."""
    import json

    models: list[AiModel] = []
    manifests_root = Path(os.path.expandvars(r"%USERPROFILE%\.ollama\models\manifests"))
    if not manifests_root.is_dir():
        return models
    for manifest in manifests_root.rglob("*"):
        if not manifest.is_file():
            continue
        rel = manifest.relative_to(manifests_root)
        # parts like: registry.ollama.ai / library / gemma / latest
        if len(rel.parts) >= 3:
            name = f"{rel.parts[-2]}:{rel.parts[-1]}"
        else:
            name = manifest.stem
        size = 0
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for layer in data.get("layers", []):
                if str(layer.get("mediaType", "")).endswith("image.model"):
                    size += int(layer.get("size", 0))
        except (OSError, ValueError, TypeError):
            size = 0  # unreadable manifest: size stays honestly 0 ('Unavailable')
        models.append(AiModel(
            runtime="Ollama", file_path=str(manifest), name=name, size_bytes=size,
        ))
    return models


def _jan_models() -> list[AiModel]:
    """Jan stores each model as <models>/<ModelName>/model.gguf.
    Incomplete downloads end in .tmp and are skipped until finished."""
    models: list[AiModel] = []
    roots = _search_dirs([r"%APPDATA%\Jan\data\llamacpp\models", r"%USERPROFILE%\jan\models"])
    for root in roots:
        if not root.is_dir():
            continue
        for gguf in root.glob("*/model.gguf"):
            try:
                size = gguf.stat().st_size
            except OSError:
                continue
            models.append(AiModel(
                runtime="Jan", file_path=str(gguf),
                name=gguf.parent.name, size_bytes=size,
            ))
    return models


class AiCollector(BaseCollector):
    label = "AI & Models"

    def collect(self) -> CollectorResult:
        tools: list[AiTool] = []
        models: list[AiModel] = []
        errors: list[str] = []

        for name, exe, dirs in _TOOL_DEFS:
            for directory in _search_dirs(dirs):
                exe_path = directory / exe
                if exe_path.is_file():
                    tools.append(AiTool(
                        name=name,
                        exe_path=str(exe_path.resolve()),
                        version="",  # never faked; filled when a safe source exists
                        install_dir=str(exe_path.parent),
                        detection_source="Filesystem scan of known install locations",
                    ))

        path_hits = {
            "Ollama": "ollama.exe",
            "LM Studio": "LM Studio.exe",
            "Jan": "jan.exe",
            "GPT4All": "gpt4all.exe",
        }
        import shutil
        for tool_name, exe in path_hits.items():
            where = shutil.which(exe)
            if where and not any(t.name == tool_name for t in tools):
                tools.append(AiTool(
                    name=tool_name, exe_path=str(Path(where).resolve()),
                    version="", install_dir=str(Path(where).parent),
                    detection_source="Found on PATH",
                ))

        for runtime, patterns in _MODEL_DIRS.items():
            for root in _search_dirs(patterns):
                try:
                    for model_file in _iter_model_files(root):
                        try:
                            size = model_file.stat().st_size
                        except OSError as exc:
                            errors.append(f"{model_file}: {exc}")
                            continue
                        models.append(AiModel(
                            runtime=runtime,
                            file_path=str(model_file),
                            name=_friendly_model_name(model_file),
                            size_bytes=size,
                        ))
                except OSError as exc:
                    errors.append(f"{root}: {exc}")

        detected = models
        detected.extend(_ollama_models())
        detected.extend(_jan_models())
        models = detected

        status = CollectorStatus.SUCCESS
        if errors and (tools or models):
            status = CollectorStatus.PARTIAL
        elif errors:
            status = CollectorStatus.PARTIAL
        return CollectorResult(
            status=status,
            data={"tools": tools, "models": models},
            detail="; ".join(errors[:3]),
            meta=self._meta(
                source="Filesystem scan of documented AI tool + model directories",
                method=(
                    "Checks the standard install locations of local AI tools "
                    "(Ollama, LM Studio, Jan, GPT4All). Models are found three "
                    "ways: Ollama's manifest store (one small JSON per model — the "
                    "model size is read from the manifest, never by hashing the "
                    "multi-GB blobs), Jan's per-folder model.gguf files, and "
                    ".gguf/.ggml/.safetensors files in the documented model "
                    "directories. Only file listings, JSON manifests and sizes are "
                    "read — model contents are never opened or transmitted. "
                    "Read-only; no admin rights."
                ),
            ),
        )
