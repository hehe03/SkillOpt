from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class RuleHit:
    rule_id: str
    label: str
    weight: float
    description: str
    group: str


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def condition_matches(features: dict[str, Any], condition: dict[str, Any]) -> bool:
    feature = condition.get("feature")
    op = condition.get("op", "==")
    expected = condition.get("value")
    actual = features.get(feature)

    if actual is None and isinstance(feature, str):
        if feature.startswith("field_exists:"):
            actual = False
        elif feature.startswith("field_text:"):
            actual = ""
        elif feature.startswith(("field_count:", "field_text_chars:")):
            actual = 0

    if op == "truthy":
        return bool(actual)
    if op == "falsey":
        return not bool(actual)
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op in {">", ">=", "<", "<="}:
        left = _coerce_number(actual)
        right = _coerce_number(expected)
        if left is None or right is None:
            return False
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        return left <= right
    if op == "contains":
        return str(expected).lower() in str(actual).lower()
    if op == "regex":
        return re.search(str(expected), str(actual), re.IGNORECASE) is not None
    raise ValueError(f"unsupported rule operator: {op}")


def rule_matches(features: dict[str, Any], rule: dict[str, Any]) -> bool:
    all_conditions = rule.get("all") or []
    any_conditions = rule.get("any") or []
    if all_conditions and not all(condition_matches(features, condition) for condition in all_conditions):
        return False
    if any_conditions and not any(condition_matches(features, condition) for condition in any_conditions):
        return False
    return bool(all_conditions or any_conditions)


def _add_grouped_score(
    scores: dict[str, dict[str, float]],
    rule: dict[str, Any],
    label: str,
    weight: float,
    *,
    use_group_cap: bool,
) -> None:
    group = str(rule.get("group") or rule.get("id") or "ungrouped")
    current = scores[label].get(group, 0.0)
    next_score = current + weight
    if use_group_cap:
        group_cap = float(rule.get("group_cap", 999.0))
        next_score = min(group_cap, next_score)
    scores[label][group] = next_score


def classify_features(
    features: dict[str, Any],
    rules: Iterable[dict[str, Any]],
    *,
    bad_threshold: float = 0.60,
    good_threshold: float = 0.50,
    use_group_cap: bool = True,
) -> dict[str, Any]:
    hits: list[RuleHit] = []
    grouped_scores = {"badcase": {}, "goodcase": {}}

    for rule in rules:
        if not rule_matches(features, rule):
            continue
        label = str(rule.get("label", "badcase"))
        weight = float(rule.get("weight", 0.0))
        group = str(rule.get("group") or rule.get("id") or "ungrouped")
        hits.append(
            RuleHit(
                rule_id=str(rule.get("id", "unnamed_rule")),
                label=label,
                weight=weight,
                description=str(rule.get("description", "")),
                group=group,
            )
        )
        if label not in grouped_scores:
            grouped_scores[label] = {}
        _add_grouped_score(grouped_scores, rule, label, weight, use_group_cap=use_group_cap)

    bad_score = round(sum(grouped_scores.get("badcase", {}).values()), 4)
    good_score = round(sum(grouped_scores.get("goodcase", {}).values()), 4)
    if bad_score >= bad_threshold and bad_score >= good_score:
        predicted_label = "badcase"
    elif good_score >= good_threshold:
        predicted_label = "goodcase"
    else:
        predicted_label = "goodcase"

    reason = "; ".join(f"{hit.rule_id}({hit.label},{hit.weight:g})" for hit in hits[:8])
    return {
        "predicted_label": predicted_label,
        "bad_score": bad_score,
        "good_score": good_score,
        "use_group_cap": use_group_cap,
        "matched_rules": [asdict(hit) for hit in hits],
        "reason": reason or "no rule matched; default to goodcase",
    }
