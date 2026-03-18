"""TAU2-Bench data loader — reads TAU2-Bench format JSON/JSONL into dicts."""

import json
from pathlib import Path
from typing import Any


def load_tau2_json(path: Path) -> list[dict[str, Any]]:
    """Load a TAU2-Bench JSON file containing a list of conversations.

    Expected format::

        [
            {"id": "...", "domain": "...", "conversations": [...], ...},
            ...
        ]

    Or a single conversation dict (wrapped in a list automatically).
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    msg = f"Expected list or dict in TAU2 JSON, got {type(data).__name__}"
    raise ValueError(msg)


def load_tau2_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a TAU2-Bench JSONL file (one conversation per line)."""
    conversations: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                msg = f"Invalid JSON on line {line_num} of {path}"
                raise ValueError(msg) from exc
            if isinstance(record, dict):
                conversations.append(record)
    return conversations


def load_tau2_file(path: Path) -> list[dict[str, Any]]:
    """Auto-detect format and load TAU2-Bench data.

    ``.jsonl`` → line-delimited, ``.json`` → array or single dict.
    """
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return load_tau2_jsonl(path)
    return load_tau2_json(path)
