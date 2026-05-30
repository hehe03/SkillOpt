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


def _iter_field_values(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = _field_path(prefix, str(key))
            yield path, child
            yield from _iter_field_values(child, path)
    elif isinstance(value, list):
        list_path = f"{prefix}[]" if prefix else "[]"
        for child in value:
            yield list_path, child
            yield from _iter_field_values(child, list_path)


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


def _add_dynamic_field_features(features: dict[str, Any], value: Any) -> None:
    values_by_path: dict[str, list[Any]] = {}
    for path, child in _iter_field_values(value):
        values_by_path.setdefault(path, []).append(child)

    for path, values in values_by_path.items():
        texts = [_text_of(item).strip() for item in values]
        nonempty_texts = [text for text in texts if text]
        unique_texts = set(texts)
        text_lengths = [len(text) for text in texts]
        numbers: list[float] = []
        bools: list[bool] = []
        for item in values:
            if isinstance(item, bool):
                bools.append(item)
            elif isinstance(item, (int, float)):
                numbers.append(float(item))
            else:
                try:
                    numbers.append(float(str(item)))
                except (TypeError, ValueError):
                    pass

        features[f"field_exists:{path}"] = True
        features[f"field_count:{path}"] = len(values)
        features[f"field_text:{path}"] = "\n".join(nonempty_texts)[:4000]
        features[f"field_empty_count:{path}"] = len(values) - len(nonempty_texts)
        features[f"field_text_chars:{path}"] = sum(text_lengths)
        features[f"field_text_max_chars:{path}"] = max(text_lengths) if text_lengths else 0
        features[f"field_unique_value_count:{path}"] = len(unique_texts)
        features[f"field_unique_value_ratio:{path}"] = round(len(unique_texts) / len(values), 4) if values else 0.0
        features[f"field_nonempty_ratio:{path}"] = round(len(nonempty_texts) / len(values), 4) if values else 0.0
        features[f"field_error_text_count:{path}"] = sum(1 for text in texts if ERROR_RE.search(text))
        features[f"field_number_count:{path}"] = len(numbers)
        features[f"field_number_ratio:{path}"] = round(len(numbers) / len(values), 4) if values else 0.0
        if numbers:
            features[f"field_number_min:{path}"] = min(numbers)
            features[f"field_number_max:{path}"] = max(numbers)
            features[f"field_number_mean:{path}"] = round(sum(numbers) / len(numbers), 4)
            features[f"field_number_range:{path}"] = round(max(numbers) - min(numbers), 4)
            features[f"field_number_zero_ratio:{path}"] = round(sum(1 for number in numbers if number == 0) / len(numbers), 4)
            features[f"field_number_positive_ratio:{path}"] = round(
                sum(1 for number in numbers if number > 0) / len(numbers),
                4,
            )
            if len(numbers) == 1:
                features[f"field_number:{path}"] = numbers[0]
        if bools:
            features[f"field_bool_true_ratio:{path}"] = round(sum(1 for item in bools if item) / len(bools), 4)
            features[f"field_bool_false_ratio:{path}"] = round(sum(1 for item in bools if not item) / len(bools), 4)
            if len(bools) == 1:
                features[f"field_bool:{path}"] = bools[0]


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
    repeated_action_count = sum(count - 1 for count in action_counts.values() if count > 1)

    features: dict[str, Any] = {
        "parse_error": parse_error,
        "is_empty_trace": trace in ({}, [], None, ""),
        "has_steps": bool(observations),
        "step_count": len(observations),
        "trace_text_chars": len(joined_text),
        "has_error_text": bool(error_count),
        "error_count": error_count,
        "result_count": result_total,
        "empty_result_count": empty_results,
        "empty_result_ratio": round(empty_results / result_total, 4) if result_total else 0.0,
        "nonempty_result_ratio": round(nonempty_results / result_total, 4) if result_total else 0.0,
        "has_final_answer": final_answer_hits > 0,
        "final_answer_count": final_answer_hits,
        "action_count": len(actions),
        "unique_action_count": len(action_counts),
        "unique_action_ratio": round(len(action_counts) / len(actions), 4) if actions else 0.0,
        "repeated_action_count": repeated_action_count,
        "max_consecutive_same_action": max_repeat,
        "text_chars": len(joined_text),
    }
    _add_dynamic_field_features(features, trace)
    return features
