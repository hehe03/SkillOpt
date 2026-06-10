from __future__ import annotations

import json
import re
from typing import Any


VALID_LABELS = {"goodcase", "badcase"}
DONE_MARKER = "__TRACE_SORTER_DONE__"
EXPECTED_FIELDS = ("label", "confidence", "reasons", "evidence", "risk_signals")


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
    raw = str(text or "").replace(DONE_MARKER, "").strip()
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    first_object = re.match(r"\s*(\{.*?\})\s*(?:\Z|\n)", raw, flags=re.DOTALL)
    if first_object:
        candidates.append(first_object.group(1))
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


def _extract_explicit_label(text: str) -> str:
    raw = str(text or "")
    patterns = [
        r'"label"\s*:\s*["\']?\s*(goodcase|badcase|good|bad)\b',
        r"\blabel\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"\bfinal\s+label\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"\bpredicted\s+label\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"\bprediction\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"\bclassification\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"\banswer\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"标签\s*[:：]\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
        r"判(?:为|定为)\s*[`\"'\s]*(goodcase|badcase|good|bad)\b",
    ]
    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE | re.MULTILINE):
            label = normalize_label(match.group(1))
            if label in VALID_LABELS:
                matches.append((match.start(), label))
    if matches:
        return sorted(matches, key=lambda item: item[0])[-1][1]

    line_keywords = (
        "label",
        "final label",
        "predicted label",
        "prediction",
        "classification",
        "answer",
        "标签",
        "判定",
        "判断",
        "结果",
    )
    line_matches: list[tuple[int, str]] = []
    for line_no, line in enumerate(raw.splitlines()):
        lowered = line.lower()
        if not any(keyword in lowered for keyword in line_keywords):
            continue
        labels = [
            normalize_label(match.group(1))
            for match in re.finditer(r"\b(goodcase|badcase|good|bad)\b", line, flags=re.IGNORECASE)
        ]
        labels = [label for label in labels if label in VALID_LABELS]
        if labels:
            line_matches.append((line_no, labels[-1]))
    if line_matches:
        return line_matches[-1][1]
    return ""


def parse_prediction(response: str) -> dict[str, Any]:
    payload = _extract_json_object(response)
    parse_issues: list[str] = []
    if not payload:
        parse_issues.append("missing_json_object: expected first response line to be a JSON object")

    missing_fields = [field for field in EXPECTED_FIELDS if field not in payload]
    if missing_fields:
        parse_issues.append(f"missing_fields: {', '.join(missing_fields)}")

    label = normalize_label(payload.get("label"))
    if label not in VALID_LABELS:
        label = _extract_explicit_label(response)
    if label not in VALID_LABELS:
        parse_issues.append("invalid_or_missing_label: expected label to be goodcase or badcase")

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0
        parse_issues.append("invalid_confidence: expected confidence to be a number between 0 and 1")

    reasons = payload.get("reasons") if isinstance(payload.get("reasons"), list) else []
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    risk_signals = payload.get("risk_signals") if isinstance(payload.get("risk_signals"), list) else []
    for field, value in (
        ("reasons", payload.get("reasons")),
        ("evidence", payload.get("evidence")),
        ("risk_signals", payload.get("risk_signals")),
    ):
        if field in payload and not isinstance(value, list):
            parse_issues.append(f"invalid_field_type: {field} should be a list")

    return {
        "label": label if label in VALID_LABELS else "",
        "confidence": confidence,
        "reasons": reasons,
        "evidence": evidence,
        "risk_signals": risk_signals,
        "missing_fields": missing_fields,
        "parse_issues": parse_issues,
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
        "missing_fields": prediction["missing_fields"],
        "parse_issues": prediction["parse_issues"],
    }
