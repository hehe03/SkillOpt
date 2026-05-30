from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.evaluator import confusion_and_scores
from tracesorter_rules.trace_io import normalize_label, read_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="用 metadata.csv 内部计算预测结果指标，只输出聚合指标。")
    parser.add_argument("--predictions", required=True, help="eval_skill.py 生成的 predictions.json。")
    parser.add_argument("--metadata", required=True, help="包含 name,label 的 metadata.csv。脚本内部读取，不输出逐条标签。")
    parser.add_argument("--output", required=True, help="聚合指标 JSON 输出路径。")
    parser.add_argument("--split", help="只统计 metadata 中指定 split 的样本。")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    metadata = read_metadata(args.metadata)
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    if not isinstance(predictions, list):
        raise ValueError("predictions.json must contain a list")

    rows = []
    for row in predictions:
        name = str(row.get("id") or "")
        meta = metadata.get(name, {})
        if args.split and (meta.get("split") or "").lower() != args.split.lower():
            continue
        label = normalize_label(meta.get("label"))
        if label not in {"goodcase", "badcase"}:
            continue
        rows.append(
            {
                "label": label,
                "predicted_label": row.get("predicted_label"),
            }
        )

    summary = confusion_and_scores(rows)
    summary["scored_predictions"] = len(rows)
    summary["split"] = args.split or "all"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("聚合指标计算完成")
    print(f"输出: {output.resolve()}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
