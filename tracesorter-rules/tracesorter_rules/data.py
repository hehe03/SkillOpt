from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_or_jsonl(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get("data") or data.get("items")
        if isinstance(nested, list):
            return nested
        return list(data.values())

    items: list[dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"JSONL item must be an object: {file_path}")
            items.append(item)
    return items


def load_split_items(split_dir: str | Path, split: str) -> list[dict[str, Any]]:
    split_path = Path(split_dir) / split
    if not split_path.is_dir():
        raise FileNotFoundError(f"split directory not found: {split_path}")

    candidates = sorted(split_path.glob("*.json")) + sorted(split_path.glob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"no .json or .jsonl file found in: {split_path}")
    return load_json_or_jsonl(candidates[0])

