from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _load_items_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                if isinstance(row, dict):
                    items.append(row)
        return items
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        values = list(data.values())
        if all(isinstance(row, dict) for row in values):
            return values
    raise ValueError(f"Unsupported SearchQA data format: {path}")


def _infer_split_from_path(path: Path, root: Path) -> str:
    aliases = {
        "train": "train",
        "training": "train",
        "valid": "val",
        "validation": "val",
        "val": "val",
        "dev": "val",
        "test": "test",
    }
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    candidates = [path.stem.lower(), *(part.lower() for part in parts[:-1])]
    for candidate in candidates:
        for token, split in aliases.items():
            if candidate == token or candidate.startswith(f"{token}.") or candidate.startswith(f"{token}_"):
                return split
    return ""


def _load_items(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        return _load_items_file(path)
    if not path.is_dir():
        raise FileNotFoundError(path)

    items: list[dict[str, Any]] = []
    files = sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".json", ".jsonl"}
    )
    if not files:
        raise FileNotFoundError(f"No .json/.jsonl files found under {path}")
    for file_path in files:
        inferred_split = _infer_split_from_path(file_path, path)
        for row in _load_items_file(file_path):
            item = dict(row)
            item.setdefault("_source_file", str(file_path))
            if inferred_split and not str(item.get("split") or "").strip():
                item["split"] = inferred_split
            items.append(item)
    return items


def _normalise_item(row: dict[str, Any], index: int) -> dict[str, Any]:
    question = str(row.get("question") or row.get("query") or "").strip()
    context = row.get("context")
    if context is None:
        passages = row.get("passages") or row.get("documents") or row.get("ctxs")
        if isinstance(passages, list):
            parts = []
            for passage in passages:
                if isinstance(passage, dict):
                    title = str(passage.get("title") or "").strip()
                    text = str(passage.get("text") or passage.get("content") or "").strip()
                    parts.append(f"[DOC] {title}\n{text}" if title else f"[DOC] {text}")
                else:
                    parts.append(f"[DOC] {passage}")
            context = "\n\n".join(parts)
        else:
            context = ""
    answers = row.get("answers", row.get("answer", row.get("gold_answers", [])))
    if isinstance(answers, str):
        answers = [answers]
    if not isinstance(answers, list):
        answers = [str(answers)]
    item = dict(row)
    item["id"] = str(row.get("id") or row.get("name") or f"searchqa-{index:06d}")
    item["question"] = question
    item["context"] = str(context or "")
    item["answers"] = [str(answer) for answer in answers if str(answer).strip()]
    item["task_type"] = str(row.get("task_type") or "qa")
    if not item["question"]:
        raise ValueError(f"Item {item['id']} is missing question/query")
    if not item["answers"]:
        raise ValueError(f"Item {item['id']} is missing answers/answer")
    return item


def _ratio_counts(n: int, ratio: str) -> tuple[int, int, int, int]:
    parts = [
        float(x.strip().rstrip("%"))
        for x in str(ratio).replace(",", ":").split(":")
        if x.strip()
    ]
    if len(parts) != 3 or any(x < 0 for x in parts) or sum(parts) <= 0:
        raise ValueError("--split-ratio must contain three non-negative values, e.g. 8:1:1 or 80:10:0")
    total = sum(parts)
    if total <= 10:
        # Backward-compatible weight mode: 8:1:1 means use all data as 80/10/10.
        scale = n / total
    elif total <= 100:
        # Percent mode: 70:10:0 uses 80% of data and leaves 20% unused.
        scale = n / 100.0
    else:
        # Fallback for arbitrary weights.
        scale = n / total
    train_n = int(round(parts[0] * scale))
    val_n = int(round(parts[1] * scale))
    test_n = int(round(parts[2] * scale))
    train_n = min(train_n, n)
    val_n = min(val_n, n - train_n)
    test_n = min(test_n, n - train_n - val_n)
    unused_n = n - train_n - val_n - test_n
    return train_n, val_n, test_n, unused_n


def _split_items(items: list[dict[str, Any]], *, ratio: str, seed: int) -> dict[str, list[dict[str, Any]]]:
    explicit = {"train": [], "val": [], "test": []}
    aliases = {
        "train": "train",
        "training": "train",
        "valid": "val",
        "validation": "val",
        "val": "val",
        "dev": "val",
        "test": "test",
    }
    all_have_split = all(str(item.get("split") or "").strip() for item in items)
    if all_have_split:
        for item in items:
            split = aliases.get(str(item.get("split") or "").strip().lower())
            if split is None:
                raise ValueError(f"Unknown split {item.get('split')!r} for item {item['id']}")
            explicit[split].append(item)
        return explicit

    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    train_n, val_n, test_n, _unused_n = _ratio_counts(len(shuffled), ratio)
    return {
        "train": shuffled[:train_n],
        "val": shuffled[train_n : train_n + val_n],
        "test": shuffled[train_n + val_n : train_n + val_n + test_n],
    }


def _write_split(out_dir: Path, splits: dict[str, list[dict[str, Any]]], *, source_total: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in splits.items():
        split_dir = out_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "items.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "source_total": source_total,
        "splits": {split: len(rows) for split, rows in splits.items()},
        "unused": source_total - sum(len(rows) for rows in splits.values()),
    }
    (out_dir / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare SearchQA data for opt-in harness.")
    parser.add_argument(
        "--input",
        default="opt-in-harness/workspace/searchqa/data/raw/searchqa",
        help="Raw SearchQA JSON/JSONL file or directory such as data/raw/searchqa.",
    )
    parser.add_argument(
        "--output-dir",
        default="opt-in-harness/workspace/searchqa/data/default_split",
        help="Output split_dir containing train/val/test folders.",
    )
    parser.add_argument(
        "--split-ratio",
        default="8:1:1",
        help=(
            "Either weights, e.g. 8:1:1 uses all data, or percentages, "
            "e.g. 70:10:0 uses 80%% and leaves the rest unused."
        ),
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    rows = _load_items(Path(args.input))
    items = [_normalise_item(row, index) for index, row in enumerate(rows, 1)]
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    splits = _split_items(items, ratio=args.split_ratio, seed=args.seed)
    _write_split(Path(args.output_dir), splits, source_total=len(items))
    print(
        "Prepared SearchQA splits: "
        + ", ".join(f"{split}={len(rows)}" for split, rows in splits.items())
        + f", unused={len(items) - sum(len(rows) for rows in splits.values())}"
    )


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--input",
        "opt-in-harness/workspace/searchqa/data/raw/searchqa",
        "--output-dir",
        "opt-in-harness/workspace/searchqa/data/default_split",
    ]
    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
