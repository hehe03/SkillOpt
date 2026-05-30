from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.trace_io import (
    TraceRecord,
    load_records,
    record_to_item,
    records_with_labels,
    select_by_split,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 trace 文件夹和 metadata.csv 预处理为 tracesorter-rules split 数据。")
    parser.add_argument("--trace-path", required=True, help="trace JSON 文件或文件夹。")
    parser.add_argument("--metadata", required=True, help="metadata.csv，至少包含 name,label；可选 source,split。")
    parser.add_argument("--out-dir", required=True, help="输出 split 目录。")
    parser.add_argument("--split-mode", choices=["auto", "metadata", "ratio"], default="auto", help="auto 优先使用 metadata split，否则按比例切分。")
    parser.add_argument("--train-split", default="train", help="metadata 中训练集 split 名。")
    parser.add_argument("--val-split", default="val", help="metadata 中验证集 split 名。")
    parser.add_argument("--test-split", default="test", help="metadata 中测试集 split 名。")
    parser.add_argument("--no-val", action="store_true", help="不输出 val/，只生成 train/ 和 test/。")
    parser.add_argument("--ratios", default="", help="ratio 模式比例。启用 val 时形如 0.7,0.15,0.15；--no-val 时形如 0.8,0.2。")
    parser.add_argument("--seed", type=int, default=42, help="ratio 模式随机种子。")
    parser.add_argument(
        "--label-policy",
        choices=["train_only", "train_val", "all", "none"],
        default="train_val",
        help="标签落盘策略。默认 train_val：train/val 写入标签用于优化和选择，test 隐藏标签防泄露。",
    )
    parser.add_argument("--labeled-only", action="store_true", help="只保留有 goodcase/badcase 标签的样本。默认保留所有样本。")
    parser.add_argument("--include-unlabeled", action="store_true", help="兼容旧参数；现在默认已经保留无标签样本。")
    return parser


def _parse_ratios(text: str, *, use_val: bool) -> tuple[float, ...]:
    if text.strip():
        ratios = tuple(float(part.strip()) for part in text.split(",") if part.strip())
    elif use_val:
        ratios = (0.7, 0.15, 0.15)
    else:
        ratios = (0.8, 0.2)
    expected = 3 if use_val else 2
    if len(ratios) != expected:
        raise ValueError(f"ratios 需要 {expected} 个数字，当前为: {ratios}")
    if any(value <= 0 for value in ratios):
        raise ValueError(f"ratios 必须为正数: {ratios}")
    total = sum(ratios)
    return tuple(value / total for value in ratios)


def _stratified_ratio_split(
    records: list[TraceRecord],
    *,
    use_val: bool,
    ratios: tuple[float, ...],
    seed: int,
) -> dict[str, list[TraceRecord]]:
    by_label: dict[str, list[TraceRecord]] = {}
    for record in records:
        key = record.label or "__unlabeled__"
        by_label.setdefault(key, []).append(record)

    result = {"train": [], "test": []}
    if use_val:
        result["val"] = []

    rng = random.Random(seed)
    for group in by_label.values():
        shuffled = list(group)
        rng.shuffle(shuffled)
        total = len(shuffled)
        train_n = int(total * ratios[0])
        if use_val:
            val_n = int(total * ratios[1])
            if total >= 3:
                train_n = max(1, train_n)
                val_n = max(1, val_n)
            if train_n + val_n >= total and total > 1:
                val_n = max(0, total - train_n - 1)
            result["train"].extend(shuffled[:train_n])
            result["val"].extend(shuffled[train_n: train_n + val_n])
            result["test"].extend(shuffled[train_n + val_n:])
        else:
            if total >= 2:
                train_n = max(1, min(total - 1, train_n))
            result["train"].extend(shuffled[:train_n])
            result["test"].extend(shuffled[train_n:])

    return result


def _metadata_split(
    records: list[TraceRecord],
    *,
    train_split: str,
    val_split: str,
    test_split: str,
    use_val: bool,
) -> dict[str, list[TraceRecord]]:
    result = {
        "train": select_by_split(records, train_split),
        "test": select_by_split(records, test_split),
    }
    if use_val:
        result["val"] = select_by_split(records, val_split)
    return result


def _has_metadata_splits(records: list[TraceRecord], *, train_split: str, val_split: str, test_split: str, use_val: bool) -> bool:
    required = {train_split.lower(), test_split.lower()}
    if use_val:
        required.add(val_split.lower())
    present = {(record.split or "").lower() for record in records if record.split}
    return required.issubset(present)


def _include_label_for_split(split: str, label_policy: str) -> bool:
    if label_policy == "all":
        return True
    if label_policy == "none":
        return False
    if label_policy == "train_val":
        return split in {"train", "val"}
    return split == "train"


def _write_split(out_dir: Path, split: str, records: list[TraceRecord], *, label_policy: str) -> list[dict]:
    split_dir = out_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)
    include_label = _include_label_for_split(split, label_policy)
    items = [record_to_item(record, include_label=include_label) for record in records]
    (split_dir / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return items


def _visible_label_counts(items: list[dict]) -> dict[str, int]:
    return dict(Counter(str(item.get("label") or "unlabeled") for item in items))


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    use_val = not args.no_val
    records = load_records(args.trace_path, args.metadata)
    if args.labeled_only:
        records = records_with_labels(records)
    if not records:
        raise ValueError("没有可用样本。请检查 trace-path、metadata 和 label。")

    mode = args.split_mode
    if mode == "auto":
        mode = "metadata" if _has_metadata_splits(
            records,
            train_split=args.train_split,
            val_split=args.val_split,
            test_split=args.test_split,
            use_val=use_val,
        ) else "ratio"

    if mode == "metadata":
        splits = _metadata_split(
            records,
            train_split=args.train_split,
            val_split=args.val_split,
            test_split=args.test_split,
            use_val=use_val,
        )
        missing = [name for name, rows in splits.items() if not rows]
        if missing:
            raise ValueError(f"metadata split 模式下这些 split 没有样本: {', '.join(missing)}")
    else:
        splits = _stratified_ratio_split(
            records,
            use_val=use_val,
            ratios=_parse_ratios(args.ratios, use_val=use_val),
            seed=args.seed,
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    visible_items_by_split: dict[str, list[dict]] = {}
    for split, split_records in splits.items():
        visible_items_by_split[split] = _write_split(out_dir, split, split_records, label_policy=args.label_policy)

    manifest = {
        "trace_path": str(Path(args.trace_path).resolve()),
        "metadata": str(Path(args.metadata).resolve()),
        "split_mode": mode,
        "use_val": use_val,
        "label_policy": args.label_policy,
        "seed": args.seed,
        "splits": {
            split: {
                "count": len(split_records),
                "visible_labels": _visible_label_counts(visible_items_by_split[split]),
            }
            for split, split_records in splits.items()
        },
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("预处理完成")
    print(f"输出目录: {out_dir.resolve()}")
    for split, split_records in splits.items():
        print(f"{split}: {len(split_records)} visible_labels={_visible_label_counts(visible_items_by_split[split])}")


if __name__ == "__main__":
    # Fill SCRIPT_ARGS when running this file directly from an IDE.
    # Example:
    # SCRIPT_ARGS = [
    #     "--trace-path", "../data/sample_raw/traces",
    #     "--metadata", "../data/sample_raw/metadata.csv",
    #     "--out-dir", "../data/sample_raw/splits",
    #     "--split-mode", "auto",
    #     "--no-val",
    # ]
    SCRIPT_ARGS = None

    main(SCRIPT_ARGS)
