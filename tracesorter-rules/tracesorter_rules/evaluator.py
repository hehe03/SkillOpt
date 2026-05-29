from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data import load_split_items
from .features import extract_features
from .rule_engine import classify_features
from .skill import load_skill_payload


def confusion_and_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [row for row in rows if row.get("label") in {"goodcase", "badcase"}]
    tp = sum(1 for row in labeled if row["label"] == "badcase" and row["predicted_label"] == "badcase")
    tn = sum(1 for row in labeled if row["label"] == "goodcase" and row["predicted_label"] == "goodcase")
    fp = sum(1 for row in labeled if row["label"] == "goodcase" and row["predicted_label"] == "badcase")
    fn = sum(1 for row in labeled if row["label"] == "badcase" and row["predicted_label"] == "goodcase")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(labeled) if labeled else 0.0
    return {
        "count": len(labeled),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "badcase_precision": round(precision, 4),
        "badcase_recall": round(recall, 4),
        "badcase_f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def evaluate_items(
    items: list[dict[str, Any]],
    skill_path: str | Path,
    *,
    bad_threshold: float | None = None,
    good_threshold: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_skill_payload(skill_path)
    rules = payload["rules"]
    bad_threshold = float(bad_threshold if bad_threshold is not None else payload.get("bad_threshold", 0.60))
    good_threshold = float(good_threshold if good_threshold is not None else payload.get("good_threshold", 0.50))

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_id = str(item.get("id") or item.get("name") or f"item_{index:04d}")
        label = item.get("label")
        features = extract_features(item.get("trace", item))
        prediction = classify_features(
            features,
            rules,
            bad_threshold=bad_threshold,
            good_threshold=good_threshold,
        )
        hard = int(label in {"goodcase", "badcase"} and prediction["predicted_label"] == label)
        rows.append(
            {
                "id": item_id,
                "label": label,
                "predicted_label": prediction["predicted_label"],
                "hard": hard,
                "soft": hard,
                "bad_score": prediction["bad_score"],
                "good_score": prediction["good_score"],
                "reason": prediction["reason"],
                "matched_rules": prediction["matched_rules"],
                "features": features,
            }
        )

    summary = confusion_and_scores(rows)
    summary.update(
        {
            "n_items": len(rows),
            "rules": len(rules),
            "bad_threshold": bad_threshold,
            "good_threshold": good_threshold,
        }
    )
    return rows, summary


def evaluate_split(
    *,
    skill_path: str | Path,
    split_dir: str | Path,
    split: str,
    out_root: str | Path,
    max_items: int = 0,
    bad_threshold: float | None = None,
    good_threshold: float | None = None,
) -> dict[str, Any]:
    items = load_split_items(split_dir, split)
    if max_items:
        items = items[:max_items]

    rows, summary = evaluate_items(
        items,
        skill_path,
        bad_threshold=bad_threshold,
        good_threshold=good_threshold,
    )

    output_dir = Path(out_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "predictions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "eval_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [row for row in rows if row.get("label") in {"goodcase", "badcase"} and not row["hard"]]
    (output_dir / "failure_cases.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

