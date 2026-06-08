from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_LABELS = {"goodcase", "badcase"}


@dataclass(slots=True)
class TraceRecord:
    name: str
    path: Path
    trace: Any
    label: str | None
    source: str | None
    split: str | None
    parse_error: str | None


def normalize_label(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    aliases = {
        "good": "goodcase",
        "good_case": "goodcase",
        "good-case": "goodcase",
        "goodcase": "goodcase",
        "bad": "badcase",
        "bad_case": "badcase",
        "bad-case": "badcase",
        "badcase": "badcase",
    }
    label = aliases.get(text, text)
    return label if label in VALID_LABELS else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 trace JSON 文件夹和 metadata.csv 预处理为 tracesorter-llm 标准 split。")
    parser.add_argument("--trace-dir", required=True, help="包含多个 trace JSON 文件的目录。")
    parser.add_argument("--metadata", required=True, help="metadata.csv，列名至少包含 name,label，可选 source,split。")
    parser.add_argument("--out-dir", required=True, help="输出目录，目录下会生成 train/val/test/items.json。")
    parser.add_argument(
        "--split-mode",
        choices=["auto", "metadata", "ratio"],
        default="auto",
        help="auto 优先使用 metadata split；缺失时按比例分层切分。",
    )
    parser.add_argument("--ratios", default="0.7,0.15,0.15", help="ratio 模式 train,val,test 比例。")
    parser.add_argument("--seed", type=int, default=42, help="ratio 模式随机种子。")
    parser.add_argument("--train-split", default="train", help="metadata 中训练 split 名。")
    parser.add_argument("--val-split", default="val", help="metadata 中验证 split 名。")
    parser.add_argument("--test-split", default="test", help="metadata 中测试 split 名。")
    parser.add_argument("--include-test-label", action="store_true", help="默认隐藏 test/items.json 的 ground_truth；启用后也写入测试标签。")
    parser.add_argument("--keep-unlabeled", action="store_true", help="保留无标签样本；仅适合预测，不适合默认训练。默认只保留 goodcase/badcase 标注样本。")
    return parser


def _read_metadata(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = {"name", "label"} - fieldnames
        if missing:
            raise ValueError(f"metadata.csv 缺少必需列: {', '.join(sorted(missing))}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            normalized = {str(key): str(value or "").strip() for key, value in row.items()}
            normalized["label"] = normalize_label(normalized.get("label")) or ""
            normalized["split"] = normalized.get("split", "").strip().lower()
            rows[name] = normalized
    return rows


def _load_trace(path: Path) -> tuple[Any, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle), None
    except Exception as exc:  # noqa: BLE001
        return {"_parse_error": str(exc)}, str(exc)


def _load_records(trace_dir: Path, metadata_path: Path, *, keep_unlabeled: bool) -> list[TraceRecord]:
    metadata = _read_metadata(metadata_path)
    if not trace_dir.exists():
        raise FileNotFoundError(f"trace-dir 不存在: {trace_dir}")
    records: list[TraceRecord] = []
    for path in sorted(trace_dir.rglob("*.json")):
        meta = metadata.get(path.name, {})
        label = normalize_label(meta.get("label"))
        if label not in VALID_LABELS and not keep_unlabeled:
            continue
        trace, parse_error = _load_trace(path)
        records.append(
            TraceRecord(
                name=path.name,
                path=path,
                trace=trace,
                label=label,
                source=meta.get("source") or None,
                split=(meta.get("split") or "").lower() or None,
                parse_error=parse_error,
            )
        )
    return records


def _parse_ratios(text: str) -> tuple[float, float, float]:
    values = tuple(float(part.strip()) for part in text.split(",") if part.strip())
    if len(values) != 3:
        raise ValueError("--ratios 需要 3 个数字，例如 0.7,0.15,0.15")
    if any(value < 0 for value in values) or sum(values) <= 0:
        raise ValueError(f"--ratios 必须是非负且总和大于 0: {values}")
    total = sum(values)
    return values[0] / total, values[1] / total, values[2] / total


def _ratio_split(records: list[TraceRecord], *, ratios: tuple[float, float, float], seed: int) -> dict[str, list[TraceRecord]]:
    result = {"train": [], "val": [], "test": []}
    groups: dict[str, list[TraceRecord]] = {}
    for record in records:
        groups.setdefault(record.label or "__unlabeled__", []).append(record)
    rng = random.Random(seed)
    for group in groups.values():
        shuffled = list(group)
        rng.shuffle(shuffled)
        total = len(shuffled)
        train_n = int(total * ratios[0])
        val_n = int(total * ratios[1])
        if total >= 3:
            train_n = max(1, train_n)
            val_n = max(1, val_n)
        if train_n + val_n >= total and total > 1:
            val_n = max(0, total - train_n - 1)
        result["train"].extend(shuffled[:train_n])
        result["val"].extend(shuffled[train_n : train_n + val_n])
        result["test"].extend(shuffled[train_n + val_n :])
    return result


def _metadata_split(
    records: list[TraceRecord],
    *,
    train_split: str,
    val_split: str,
    test_split: str,
) -> dict[str, list[TraceRecord]]:
    names = {
        "train": train_split.strip().lower(),
        "val": val_split.strip().lower(),
        "test": test_split.strip().lower(),
    }
    return {split: [record for record in records if (record.split or "").lower() == name] for split, name in names.items()}


def _metadata_has_splits(records: list[TraceRecord], *, train_split: str, val_split: str, test_split: str) -> bool:
    present = {(record.split or "").lower() for record in records if record.split}
    required = {train_split.lower(), val_split.lower(), test_split.lower()}
    return required.issubset(present)


def _record_to_item(record: TraceRecord, *, include_label: bool) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": Path(record.name).stem,
        "features": {
            "trace": record.trace,
            "parse_error": record.parse_error,
            "source": record.source,
        },
        "task_type": "trace_classification",
        "metadata": {
            "name": record.name,
            "source": record.source or "",
            "source_split": record.split or "",
            "source_path": str(record.path),
        },
        "question": "Classify this Agent execution trace as goodcase or badcase.",
    }
    if include_label and record.label:
        item["ground_truth"] = record.label
    return item


def _write_split(out_dir: Path, split: str, records: list[TraceRecord], *, include_label: bool) -> list[dict[str, Any]]:
    split_dir = out_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)
    items = [_record_to_item(record, include_label=include_label) for record in records]
    (split_dir / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return items


def _label_counts(records: list[TraceRecord]) -> dict[str, int]:
    return dict(Counter(record.label or "unlabeled" for record in records))


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    keep_unlabeled = bool(args.keep_unlabeled)
    records = _load_records(Path(args.trace_dir), Path(args.metadata), keep_unlabeled=keep_unlabeled)
    if not records:
        raise ValueError("没有可用 trace 样本。请检查 trace-dir、metadata 和 label。")

    mode = args.split_mode
    if mode == "auto":
        mode = "metadata" if _metadata_has_splits(
            records,
            train_split=args.train_split,
            val_split=args.val_split,
            test_split=args.test_split,
        ) else "ratio"
    if mode == "metadata":
        splits = _metadata_split(
            records,
            train_split=args.train_split,
            val_split=args.val_split,
            test_split=args.test_split,
        )
        empty = [split for split, rows in splits.items() if not rows]
        if empty:
            raise ValueError(f"metadata split 模式下这些 split 没有样本: {', '.join(empty)}")
    else:
        splits = _ratio_split(records, ratios=_parse_ratios(args.ratios), seed=args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, split_records in splits.items():
        include_label = split in {"train", "val"} or args.include_test_label
        _write_split(out_dir, split, split_records, include_label=include_label)

    manifest = {
        "trace_dir": str(Path(args.trace_dir).resolve()),
        "metadata": str(Path(args.metadata).resolve()),
        "split_mode": mode,
        "ratios": args.ratios if mode == "ratio" else "",
        "seed": args.seed,
        "include_test_label": bool(args.include_test_label),
        "splits": {
            split: {
                "count": len(split_records),
                "label_counts": _label_counts(split_records),
            }
            for split, split_records in splits.items()
        },
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("预处理完成")
    print(f"输出目录: {out_dir.resolve()}")
    for split, split_records in splits.items():
        print(f"{split}: {len(split_records)} label_counts={_label_counts(split_records)}")


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None
    main(SCRIPT_ARGS)
