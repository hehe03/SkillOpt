from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .data import load_split_items
from .features import extract_features
from .rule_engine import classify_features
from .skill import load_skill_payload


def _prediction_rules_only(matched_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for rule in matched_rules:
        item = dict(rule)
        if "label" in item:
            item["rule_label"] = item.pop("label")
        cleaned.append(item)
    return cleaned


def predict_items(
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
        features = extract_features(item.get("trace", item))
        prediction = classify_features(
            features,
            rules,
            bad_threshold=bad_threshold,
            good_threshold=good_threshold,
        )
        rows.append(
            {
                "id": item_id,
                "predicted_label": prediction["predicted_label"],
                "bad_score": prediction["bad_score"],
                "good_score": prediction["good_score"],
                "reason": prediction["reason"],
                "matched_rules": _prediction_rules_only(prediction["matched_rules"]),
            }
        )

    summary = {
        "n_items": len(rows),
        "rules": len(rules),
        "bad_threshold": bad_threshold,
        "good_threshold": good_threshold,
        "predicted_goodcase": sum(1 for row in rows if row["predicted_label"] == "goodcase"),
        "predicted_badcase": sum(1 for row in rows if row["predicted_label"] == "badcase"),
    }
    return rows, summary


def write_predictions(rows: list[dict[str, Any]], summary: dict[str, Any], out_root: str | Path) -> None:
    output_dir = Path(out_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "predictions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "prediction_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with (output_dir / "predictions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "predicted_label", "bad_score", "good_score", "reason"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "predicted_label": row["predicted_label"],
                    "bad_score": row["bad_score"],
                    "good_score": row["good_score"],
                    "reason": row["reason"],
                }
            )


def predict_split(
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
    rows, summary = predict_items(
        items,
        skill_path,
        bad_threshold=bad_threshold,
        good_threshold=good_threshold,
    )
    write_predictions(rows, summary, out_root)
    return summary
