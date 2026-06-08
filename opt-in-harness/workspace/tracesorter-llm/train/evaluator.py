from __future__ import annotations

import json
import re
from typing import Any


VALID_LABELS = {"goodcase", "badcase"}


def normalize_label(value: Any) -> str:
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
    return aliases.get(text, text)


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def parse_prediction(response: str) -> dict[str, Any]:
    payload = _extract_json_object(response)
    label = normalize_label(payload.get("label"))
    if label not in VALID_LABELS:
        label_match = re.search(r"\b(goodcase|badcase|good|bad)\b", str(response or ""), flags=re.IGNORECASE)
        label = normalize_label(label_match.group(1) if label_match else "")
    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "label": label if label in VALID_LABELS else "",
        "confidence": confidence,
        "reasons": payload.get("reasons") if isinstance(payload.get("reasons"), list) else [],
        "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
        "risk_signals": payload.get("risk_signals") if isinstance(payload.get("risk_signals"), list) else [],
        "raw_payload": payload,
    }


def evaluate(response: str, gold_answer: str) -> dict[str, Any]:
    prediction = parse_prediction(response)
    predicted_label = prediction["label"]
    gold_label = normalize_label(gold_answer)
    hard = int(predicted_label in VALID_LABELS and predicted_label == gold_label)
    soft = float(hard)
    if predicted_label in VALID_LABELS and gold_label in VALID_LABELS and predicted_label != gold_label:
        soft = 0.0
    return {
        "hard": hard,
        "soft": soft,
        "accuracy": float(hard),
        "prediction": predicted_label,
        "predicted_label": predicted_label,
        "gold_answer": gold_label,
        "gold_label": gold_label,
        "confidence": prediction["confidence"],
        "reasons": prediction["reasons"],
        "evidence": prediction["evidence"],
        "risk_signals": prediction["risk_signals"],
        "parse_ok": predicted_label in VALID_LABELS,
    }
