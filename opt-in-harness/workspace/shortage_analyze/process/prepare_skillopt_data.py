from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_COLUMN = "answer"
DEFAULT_ID_PREFIX = "shortage"
NONE_LABEL = "- 未匹配到分支"
LABEL_DELIMITER = "、"
EXCLUDED_FEATURE_COLUMNS = {"answer", "references"}
SPLIT_NAMES = ("train", "val", "test")


def configure_windows_utf8_stdio() -> None:
    """Keep Chinese console output readable on Windows when possible."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将 shortage_analyze Excel 数据处理为 SkillOpt split 数据。"
    )
    parser.add_argument(
        "--input",
        default=r"D:\code\github\hehe03\data.xlsx",
        help="原始 Excel 路径，仅在本预处理脚本中读取。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_WORKSPACE_ROOT / "data" / "shortage_analyze_split"),
        help="输出 split 目录。",
    )
    parser.add_argument("--sheet", default=0, help="Excel sheet 名称或序号。")
    parser.add_argument("--label-column", default=DEFAULT_LABEL_COLUMN)
    parser.add_argument("--id-prefix", default=DEFAULT_ID_PREFIX)
    parser.add_argument(
        "--split-ratio",
        default="3:2:5",
        help="train:val:test 比例。默认 3:2:5。",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--include-references",
        action="store_true",
        help="是否把 references 列也写入特征。默认不写，避免冗余长文本。",
    )
    parser.add_argument(
        "--write-test-labels",
        action="store_true",
        help="显式生成私有 test_labels.json。默认不生成，避免优化阶段接触测试标签。",
    )
    return parser


def _parse_sheet(value: str) -> str | int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _parse_ratio(text: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in str(text).split(":") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"split-ratio 必须是 train:val:test 形式，当前为 {text!r}")
    values = tuple(int(part) for part in parts)
    if min(values) <= 0:
        raise ValueError(f"split-ratio 每一项都必须为正数，当前为 {text!r}")
    return values


def _split_counts(total: int, ratio: tuple[int, int, int]) -> dict[str, int]:
    denom = sum(ratio)
    raw = [total * part / denom for part in ratio]
    counts = [math.floor(value) for value in raw]
    remainder = total - sum(counts)
    order = sorted(
        range(3),
        key=lambda idx: (raw[idx] - counts[idx], ratio[idx]),
        reverse=True,
    )
    for idx in order[:remainder]:
        counts[idx] += 1
    return dict(zip(SPLIT_NAMES, counts, strict=True))


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except ValueError:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _normalize_label_text(value: Any) -> str:
    if pd.isna(value):
        return NONE_LABEL
    text = str(value).strip()
    return text or NONE_LABEL


def _label_set(answer: str) -> list[str]:
    text = _normalize_label_text(answer)
    if text == NONE_LABEL:
        return []
    return [
        part.strip()
        for part in text.replace(",", LABEL_DELIMITER).split(LABEL_DELIMITER)
        if part.strip()
    ]


def _format_feature_value(value: Any) -> str:
    if value is None:
        return "(空)"
    return str(value)


def _build_feature_text(features: dict[str, Any]) -> str:
    rows = ["| 字段 | 值 |", "| --- | --- |"]
    for key, value in features.items():
        safe_value = _format_feature_value(value).replace("\n", " ")
        rows.append(f"| {key} | {safe_value} |")
    return "\n".join(rows)


def _build_question(feature_text: str) -> str:
    labels = [
        "网容异常",
        "用量异常",
        "补库异常",
        "基线异常",
        "计划参数异常",
        "补库供应不及时",
        "责任库房异常",
        "替代交付异常",
        NONE_LABEL,
    ]
    return (
        "请根据下面一行欠料分析数据，判断应该命中的 L2 分类标签。\n"
        f"可选标签：{LABEL_DELIMITER.join(labels)}。\n"
        "如命中多个标签，请用中文顿号 `、` 连接；如果没有任何异常分支，请输出 `- 未匹配到分支`。\n"
        "最终答案必须只放在 `<answer>...</answer>` 中。\n\n"
        "## 行数据\n"
        f"{feature_text}"
    )


def _make_items(
    df: pd.DataFrame,
    *,
    label_column: str,
    id_prefix: str,
    include_references: bool,
) -> list[dict[str, Any]]:
    if label_column not in df.columns:
        raise ValueError(f"Excel 中找不到标签列 {label_column!r}")

    excluded = set(EXCLUDED_FEATURE_COLUMNS)
    if include_references:
        excluded.remove("references")
    feature_columns = [col for col in df.columns if str(col) not in excluded]

    items: list[dict[str, Any]] = []
    for index, row in df.iterrows():
        features = {
            str(column): _jsonable(row[column])
            for column in feature_columns
        }
        answer = _normalize_label_text(row[label_column])
        feature_text = _build_feature_text(features)
        item_id = f"{id_prefix}_{index + 1:04d}"
        items.append(
            {
                "id": item_id,
                "uid": item_id,
                "row_index": int(index),
                "question": _build_question(feature_text),
                "feature_text": feature_text,
                "features": features,
                "ground_truth": answer,
                "answers": [answer],
                "label_set": _label_set(answer),
                "task_type": "shortage_analyze",
            }
        )
    return items


def _stratified_split(
    items: list[dict[str, Any]],
    counts: dict[str, int],
    *,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[str(item["ground_truth"])].append(item)

    group_values = list(groups.values())
    for group in group_values:
        rng.shuffle(group)
    rng.shuffle(group_values)

    splits: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLIT_NAMES}

    def pick_split() -> str:
        candidates = [
            name for name in SPLIT_NAMES
            if len(splits[name]) < counts[name]
        ]
        if not candidates:
            return "train"
        return max(
            candidates,
            key=lambda name: (
                (counts[name] - len(splits[name])) / max(counts[name], 1),
                counts[name],
            ),
        )

    for group in group_values:
        for item in group:
            splits[pick_split()].append(item)

    for name in SPLIT_NAMES:
        rng.shuffle(splits[name])
    return splits


def _strip_test_labels(item: dict[str, Any]) -> dict[str, Any]:
    public = dict(item)
    for key in ("ground_truth", "answers", "label_set"):
        public.pop(key, None)
    return public


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    sheet = _parse_sheet(args.sheet)
    ratio = _parse_ratio(args.split_ratio)

    df = pd.read_excel(input_path, sheet_name=sheet)
    items = _make_items(
        df,
        label_column=args.label_column,
        id_prefix=args.id_prefix,
        include_references=args.include_references,
    )
    counts = _split_counts(len(items), ratio)
    splits = _stratified_split(items, counts, seed=args.seed)

    for split_name in ("train", "val"):
        _write_json(output_dir / split_name / "items.json", splits[split_name])
    _write_json(
        output_dir / "test" / "items.json",
        [_strip_test_labels(item) for item in splits["test"]],
    )

    test_label_path = None
    if args.write_test_labels:
        test_label_path = output_dir / "_private" / "test_labels.json"
        _write_json(
            test_label_path,
            [
                {
                    "id": item["id"],
                    "row_index": item["row_index"],
                    "ground_truth": item["ground_truth"],
                    "answers": item["answers"],
                    "label_set": item["label_set"],
                }
                for item in splits["test"]
            ],
        )

    manifest = {
        "source_data_path": str(input_path.resolve()),
        "source_sheet": sheet,
        "label_column": args.label_column,
        "split_ratio": args.split_ratio,
        "split_seed": args.seed,
        "counts": {name: len(splits[name]) for name in SPLIT_NAMES},
        "test_items_contain_labels": False,
        "private_test_labels_path": str(test_label_path) if test_label_path else "",
        "note": (
            "训练/优化配置应只指向本 split 目录，不能指向原始 data.xlsx。"
            "默认 test/items.json 已移除 ground_truth/answers/label_set。"
        ),
    }
    _write_json(output_dir / "split_manifest.json", manifest)

    print(f"已读取: {input_path}")
    print(f"已输出: {output_dir}")
    print(
        "split 数量: "
        + " ".join(f"{name}={len(splits[name])}" for name in SPLIT_NAMES)
    )
    print("测试集标签: 未写入 test/items.json")
    if test_label_path:
        print(f"私有测试标签: {test_label_path}")


def main(argv: Sequence[str] | None = None) -> None:
    configure_windows_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--input",
        r"D:\code\github\hehe03\data.xlsx",
        "--output-dir",
        str(DEFAULT_WORKSPACE_ROOT / "data" / "shortage_analyze_split"),
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
