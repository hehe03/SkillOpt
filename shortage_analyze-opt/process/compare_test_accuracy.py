from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLOPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = SKILLOPT_ROOT / "processed" / "shortage_analyze_split" / "test" / "items.json"
DEFAULT_PRIVATE_LABELS = (
    SKILLOPT_ROOT / "processed" / "shortage_analyze_split" / "_private" / "test_labels.json"
)
DEFAULT_SOURCE_EXCEL = Path(r"D:\code\github\hehe03\data.xlsx")
FALLBACK_SOURCE_EXCEL = SKILLOPT_ROOT / "shortage_analyze" / "data.xlsx"
DEFAULT_LEGACY_SCRIPT = SKILLOPT_ROOT / "shortage_analyze" / "scripts" / "analyze_shortage.py"
DEFAULT_OPTIMIZED_SCRIPT = (
    SKILLOPT_ROOT / "shortage_analyze-optimized" / "best" / "scripts" / "analyze_shortage.py"
)
DEFAULT_OUTPUT = SKILLOPT_ROOT / "processed" / "eval" / "test_accuracy_compare.json"

NONE_LABEL = "- 未匹配到分支"
LABEL_ORDER = [
    "网容异常",
    "用量异常",
    "补库异常",
    "基线异常",
    "计划参数异常",
    "补库供应不及时",
    "责任库房异常",
    "替代交付异常",
]


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
        description="比较优化前后 shortage_analyze skill 在测试集上的准确率。"
    )
    parser.add_argument("--test-items", default=str(DEFAULT_SPLIT))
    parser.add_argument(
        "--private-labels",
        default=str(DEFAULT_PRIVATE_LABELS),
        help="私有测试标签 JSON。不存在时可用 --source-excel 从原始 Excel 按 row_index 读取标签。",
    )
    parser.add_argument(
        "--source-excel",
        default=str(DEFAULT_SOURCE_EXCEL),
        help="原始 Excel，仅用于优化结束后的离线评估，不参与训练/优化。",
    )
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--label-column", default="answer")
    parser.add_argument("--legacy-script", default=str(DEFAULT_LEGACY_SCRIPT))
    parser.add_argument("--optimized-script", default=str(DEFAULT_OPTIMIZED_SCRIPT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _parse_sheet(value: str) -> str | int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def normalize_answer(value: Any) -> str:
    if value is None:
        return NONE_LABEL
    text = str(value).strip()
    return text or NONE_LABEL


def label_set(value: Any) -> set[str]:
    text = normalize_answer(value)
    if text == NONE_LABEL:
        return set()
    normalized = text.replace(",", "、").replace("，", "、")
    return {part.strip() for part in normalized.split("、") if part.strip()}


def label_f1(prediction: str, gold: str) -> float:
    pred = label_set(prediction)
    target = label_set(gold)
    if not pred and not target:
        return 1.0
    if not pred or not target:
        return 0.0
    overlap = len(pred & target)
    if overlap == 0:
        return 0.0
    return 2 * overlap / (len(pred) + len(target))


def load_items(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}")
    return data


def load_gold_from_private_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}")
    return {
        str(item["id"]): normalize_answer(item.get("ground_truth") or item.get("answer"))
        for item in data
    }


def load_gold_from_excel(
    path: Path,
    *,
    sheet: str | int,
    label_column: str,
    items: list[dict[str, Any]],
) -> dict[str, str]:
    df = pd.read_excel(path, sheet_name=sheet)
    if label_column not in df.columns:
        raise ValueError(f"Excel 中找不到标签列 {label_column!r}")
    gold: dict[str, str] = {}
    for item in items:
        row_index = int(item["row_index"])
        gold[str(item["id"])] = normalize_answer(df.iloc[row_index][label_column])
    return gold


def load_gold_labels(args: argparse.Namespace, items: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    embedded = {
        str(item["id"]): normalize_answer(item.get("ground_truth"))
        for item in items
        if item.get("ground_truth") is not None
    }
    if len(embedded) == len(items):
        return embedded, "embedded_ground_truth"

    private_path = Path(args.private_labels)
    if private_path.exists():
        return load_gold_from_private_labels(private_path), str(private_path)

    source_path = Path(args.source_excel)
    if source_path.exists():
        return (
            load_gold_from_excel(
                source_path,
                sheet=_parse_sheet(args.sheet),
                label_column=args.label_column,
                items=items,
            ),
            str(source_path),
        )
    if FALLBACK_SOURCE_EXCEL.exists():
        return (
            load_gold_from_excel(
                FALLBACK_SOURCE_EXCEL,
                sheet=_parse_sheet(args.sheet),
                label_column=args.label_column,
                items=items,
            ),
            str(FALLBACK_SOURCE_EXCEL),
        )

    raise FileNotFoundError(
        "找不到测试集标签，无法计算准确率。\n"
        f"- test items: {args.test_items}\n"
        f"- private labels not found: {private_path}\n"
        f"- source Excel not found: {source_path}\n"
        f"- fallback source Excel not found: {FALLBACK_SOURCE_EXCEL}\n\n"
        "可选做法：\n"
        "1. 将原始 data.xlsx 放回 shortage_analyze-opt/shortage_analyze/data.xlsx 后重跑本脚本；或\n"
        "2. 优化结束后运行 prepare_skillopt_data.py --write-test-labels 生成 "
        "shortage_analyze-opt/processed/shortage_analyze_split/_private/test_labels.json，"
        "再重跑本脚本。注意不要把该私有标签路径写入训练配置。"
    )


def predict_with_legacy_script(module, features: dict[str, Any]) -> str:
    return normalize_answer(module.analyze_row(pd.Series(features)))


def evaluate_predictions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    exact = sum(1 for row in rows if label_set(row["prediction"]) == label_set(row["gold"]))
    f1_total = sum(label_f1(row["prediction"], row["gold"]) for row in rows)
    return {
        "total": total,
        "accuracy": exact / total if total else 0.0,
        "exact_match": exact / total if total else 0.0,
        "exact_count": exact,
        "macro_label_f1": f1_total / total if total else 0.0,
    }


def run(args: argparse.Namespace) -> None:
    items = load_items(Path(args.test_items))
    gold, gold_source = load_gold_labels(args, items)

    legacy = load_module(Path(args.legacy_script), "shortage_legacy_analyze")
    optimized = load_module(
        Path(args.optimized_script),
        "shortage_optimized_predict",
    )

    before_rows: list[dict[str, Any]] = []
    after_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for item in items:
        item_id = str(item["id"])
        features = item["features"]
        gold_answer = gold[item_id]
        before = predict_with_legacy_script(legacy, features)
        after = optimized.format_prediction(optimized.predict_labels(features))
        before_rows.append({"id": item_id, "prediction": before, "gold": gold_answer})
        after_rows.append({"id": item_id, "prediction": after, "gold": gold_answer})
        details.append(
            {
                "id": item_id,
                "row_index": item.get("row_index"),
                "gold": gold_answer,
                "before_prediction": before,
                "after_prediction": after,
                "before_exact": label_set(before) == label_set(gold_answer),
                "after_exact": label_set(after) == label_set(gold_answer),
                "before_f1": label_f1(before, gold_answer),
                "after_f1": label_f1(after, gold_answer),
            }
        )

    before_metrics = evaluate_predictions(before_rows)
    after_metrics = evaluate_predictions(after_rows)
    result = {
        "test_items": str(Path(args.test_items)),
        "gold_source": gold_source,
        "legacy_script": str(Path(args.legacy_script)),
        "optimized_predictor": str(Path(args.optimized_script)),
        "before": before_metrics,
        "after": after_metrics,
        "delta": {
            "accuracy": after_metrics["accuracy"] - before_metrics["accuracy"],
            "exact_match": after_metrics["exact_match"] - before_metrics["exact_match"],
            "macro_label_f1": after_metrics["macro_label_f1"] - before_metrics["macro_label_f1"],
        },
        "details": details,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"测试集标签来源: {gold_source}")
    print(
        "优化前: "
        f"accuracy={before_metrics['accuracy']:.4f} "
        f"({before_metrics['exact_count']}/{before_metrics['total']}), "
        f"macro_label_f1={before_metrics['macro_label_f1']:.4f}"
    )
    print(
        "优化后: "
        f"accuracy={after_metrics['accuracy']:.4f} "
        f"({after_metrics['exact_count']}/{after_metrics['total']}), "
        f"macro_label_f1={after_metrics['macro_label_f1']:.4f}"
    )
    print(
        "变化: "
        f"accuracy={result['delta']['accuracy']:+.4f}, "
        f"macro_label_f1={result['delta']['macro_label_f1']:+.4f}"
    )
    print(f"详细结果: {output_path}")


def main(argv: Sequence[str] | None = None) -> None:
    configure_windows_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--test-items",
        str(DEFAULT_SPLIT),
        "--private-labels",
        str(DEFAULT_PRIVATE_LABELS),
        "--source-excel",
        str(DEFAULT_SOURCE_EXCEL),
        "--optimized-script",
        str(DEFAULT_OPTIMIZED_SCRIPT),
        "--output",
        str(DEFAULT_OUTPUT),
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
