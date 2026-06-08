from __future__ import annotations

import argparse
import csv
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
    parser = argparse.ArgumentParser(description="用 GT metadata 和预测结果计算聚合指标，不输出逐条真实标签。")
    parser.add_argument("--predictions", help="eval_skill.py/predict_skill.py 生成的 predictions.json。")
    parser.add_argument("--metadata", help="兼容旧参数：包含 name,label 的 GT metadata.csv。")
    parser.add_argument("--gt-metadata", help="包含 name,label 的 GT metadata.csv。")
    parser.add_argument(
        "--pred-metadata",
        help="预测 metadata.csv，需包含 name,predicted_label；若没有 predicted_label，则兼容使用 label 列作为预测标签。",
    )
    parser.add_argument("--output", required=True, help="聚合指标 JSON 输出路径。")
    parser.add_argument("--split", help="只统计 metadata 中指定 split 的样本。")
    return parser


def _read_csv(path: str | Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise ValueError(f"metadata CSV must contain a name column: {path}")
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            rows[name] = {key: (value or "").strip() for key, value in row.items()}
    return rows


def _rows_from_prediction_json(predictions_path: str | Path, gt_metadata: dict[str, dict[str, str]], split: str | None) -> list[dict]:
    predictions = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    if not isinstance(predictions, list):
        raise ValueError("predictions.json must contain a list")

    rows = []
    for row in predictions:
        name = str(row.get("id") or "")
        meta = gt_metadata.get(name, {})
        if split and (meta.get("split") or "").lower() != split.lower():
            continue
        label = normalize_label(meta.get("label"))
        if label not in {"goodcase", "badcase"}:
            continue
        rows.append(
            {
                "label": label,
                "predicted_label": normalize_label(row.get("predicted_label")),
            }
        )
    return rows


def _rows_from_prediction_metadata(
    pred_metadata_path: str | Path,
    gt_metadata: dict[str, dict[str, str]],
    split: str | None,
) -> list[dict]:
    pred_metadata = _read_csv(pred_metadata_path)
    rows = []
    for name, meta in gt_metadata.items():
        if split and (meta.get("split") or "").lower() != split.lower():
            continue
        label = normalize_label(meta.get("label"))
        if label not in {"goodcase", "badcase"}:
            continue
        pred = pred_metadata.get(name, {})
        predicted_label = normalize_label(pred.get("predicted_label") or pred.get("label"))
        if predicted_label not in {"goodcase", "badcase"}:
            continue
        rows.append(
            {
                "label": label,
                "predicted_label": predicted_label,
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    gt_metadata_path = args.gt_metadata or args.metadata
    if not gt_metadata_path:
        raise ValueError("请提供 --gt-metadata，或使用兼容旧参数 --metadata。")
    if bool(args.predictions) == bool(args.pred_metadata):
        raise ValueError("请二选一提供 --predictions 或 --pred-metadata。")

    metadata = read_metadata(gt_metadata_path)
    if args.predictions:
        rows = _rows_from_prediction_json(args.predictions, metadata, args.split)
        input_mode = "predictions_json"
    else:
        rows = _rows_from_prediction_metadata(args.pred_metadata, metadata, args.split)
        input_mode = "prediction_metadata"

    summary = confusion_and_scores(rows)
    summary["scored_predictions"] = len(rows)
    summary["split"] = args.split or "all"
    summary["input_mode"] = input_mode
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("聚合指标计算完成")
    print(f"输出: {output.resolve()}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
