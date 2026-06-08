from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TraceRecord:
    name: str
    path: Path
    trace: Any
    label: str | None = None
    source: str | None = None
    split: str | None = None
    parse_error: str | None = None
    metadata: dict[str, str] | None = None


def normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text:
        return None
    aliases = {
        "good": "goodcase",
        "good_case": "goodcase",
        "goodcase": "goodcase",
        "bad": "badcase",
        "bad_case": "badcase",
        "badcase": "badcase",
    }
    return aliases.get(text, text)


def read_metadata(path: str | Path | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    metadata_path = Path(path)
    rows: dict[str, dict[str, str]] = {}
    with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise ValueError("metadata.csv 必须包含 name 列。")
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            normalized = {key: (value or "").strip() for key, value in row.items()}
            normalized["label"] = normalize_label(normalized.get("label")) or ""
            normalized["split"] = (normalized.get("split") or "").strip().lower()
            rows[name] = normalized
    return rows


def iter_trace_paths(input_path: str | Path) -> list[Path]:
    path = Path(input_path)
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"trace path does not exist: {path}")
    return sorted(candidate for candidate in path.rglob("*.json") if candidate.is_file())


def load_trace_file(path: Path) -> tuple[Any, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle), None
    except Exception as exc:  # noqa: BLE001 - 解析失败也保留成可分类样本。
        return {"_parse_error": str(exc)}, str(exc)


def load_records(trace_path: str | Path, metadata_path: str | Path | None = None) -> list[TraceRecord]:
    metadata = read_metadata(metadata_path)
    records: list[TraceRecord] = []
    for path in iter_trace_paths(trace_path):
        trace, parse_error = load_trace_file(path)
        meta = metadata.get(path.name, {})
        records.append(
            TraceRecord(
                name=path.name,
                path=path,
                trace=trace,
                label=normalize_label(meta.get("label")),
                source=meta.get("source") or None,
                split=(meta.get("split") or "").lower() or None,
                parse_error=parse_error,
                metadata=meta or None,
            )
        )
    return records


def record_to_item(record: TraceRecord, *, include_label: bool = True) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": record.name,
        "trace": record.trace,
        "source_path": str(record.path),
    }
    if include_label:
        item["label"] = record.label
    if record.source:
        item["source"] = record.source
    if record.split:
        item["source_split"] = record.split
    if record.parse_error:
        item["parse_error"] = record.parse_error
    if record.metadata:
        metadata = dict(record.metadata)
        if not include_label:
            metadata.pop("label", None)
        item["metadata"] = metadata
    return item


def records_with_labels(records: list[TraceRecord]) -> list[TraceRecord]:
    return [record for record in records if record.label in {"goodcase", "badcase"}]


def select_by_split(records: list[TraceRecord], split: str) -> list[TraceRecord]:
    split = split.strip().lower()
    return [record for record in records if (record.split or "").lower() == split]
