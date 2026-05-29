from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any


ERROR_RE = re.compile(r"\b(error|exception|traceback|timeout|failed|failure|invalid)\b", re.IGNORECASE)
FINAL_KEYS = {"final_answer", "answer", "final", "final_result", "result"}
OBSERVATION_KEYS = {"steps", "messages", "actions", "events", "trajectory", "tool_calls"}
RESULT_KEYS = {"result", "output", "observation", "content", "response"}
ACTION_KEYS = {"action", "tool", "tool_name", "name", "function", "command"}


def _as_trace_object(trace: Any) -> tuple[Any, bool]:
    if isinstance(trace, str):
        text = trace.strip()
        if not text:
            return {}, False
        try:
            return json.loads(text), False
        except json.JSONDecodeError:
            return {"raw_text": trace}, True
    return trace, False


def _iter_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_values(child)
    else:
        yield value


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _collect_observations(trace: Any) -> list[dict[str, Any]]:
    if isinstance(trace, list):
        return [item for item in trace if isinstance(item, dict)]
    if not isinstance(trace, dict):
        return []

    for key in OBSERVATION_KEYS:
        value = trace.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [trace]


def _field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _add_dynamic_field_features(features: dict[str, Any], value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            path = _field_path(prefix, str(key))
            features[f"field_exists:{path}"] = True
            if isinstance(child, str):
                features[f"field_text:{path}"] = child
                features[f"field_text_chars:{path}"] = len(child)
            elif isinstance(child, bool):
                features[f"field_bool:{path}"] = child
            elif isinstance(child, (int, float)):
                features[f"field_number:{path}"] = float(child)
            elif isinstance(child, list):
                features[f"field_count:{path}"] = len(child)
            _add_dynamic_field_features(features, child, path)
    elif isinstance(value, list):
        list_path = f"{prefix}[]" if prefix else "[]"
        features[f"field_count:{list_path}"] = len(value)
        for child in value:
            _add_dynamic_field_features(features, child, list_path)


def extract_features(raw_trace: Any) -> dict[str, Any]:
    trace, parse_error = _as_trace_object(raw_trace)
    observations = _collect_observations(trace)
    dicts = list(_iter_dicts(trace))
    text_values = [str(value) for value in _iter_values(trace) if isinstance(value, str)]
    joined_text = "\n".join(text_values)

    result_values: list[Any] = []
    actions: list[str] = []
    for entry in observations:
        for key in RESULT_KEYS:
            if key in entry:
                result_values.append(entry.get(key))
        for key in ACTION_KEYS:
            if key in entry and not _is_empty(entry.get(key)):
                actions.append(str(entry.get(key)))
                break

    empty_results = sum(1 for value in result_values if _is_empty(value))
    nonempty_results = sum(1 for value in result_values if not _is_empty(value))
    result_total = len(result_values)

    max_repeat = 0
    current = 0
    previous = None
    for action in actions:
        if action == previous:
            current += 1
        else:
            current = 1
            previous = action
        max_repeat = max(max_repeat, current)

    final_answer_hits = 0
    for entry in dicts:
        for key, value in entry.items():
            if str(key).lower() in FINAL_KEYS and not _is_empty(value):
                final_answer_hits += 1

    error_count = sum(1 for text in text_values if ERROR_RE.search(text))
    action_counts = Counter(actions)

    features: dict[str, Any] = {
        "parse_error": parse_error,
        "is_empty_trace": trace in ({}, [], None, ""),
        "has_steps": bool(observations),
        "step_count": len(observations),
        "trace_text_chars": len(joined_text),
        "has_error_text": bool(error_count),
        "error_count": error_count,
        "result_count": result_total,
        "empty_result_ratio": round(empty_results / result_total, 4) if result_total else 0.0,
        "nonempty_result_ratio": round(nonempty_results / result_total, 4) if result_total else 0.0,
        "has_final_answer": final_answer_hits > 0,
        "final_answer_count": final_answer_hits,
        "action_count": len(actions),
        "unique_action_count": len(action_counts),
        "max_consecutive_same_action": max_repeat,
    }
    _add_dynamic_field_features(features, trace)
    return features

