from __future__ import annotations

import re
from collections import Counter


NONE_LABEL = "- 未匹配到分支"
LABEL_DELIMITER = "、"
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
KNOWN_LABELS = set(LABEL_ORDER)


def extract_answer(response: str) -> str:
    text = str(response or "").strip()
    match = re.search(r"<answer>\s*(.*?)\s*</answer>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            return line
    return ""


def labels_to_set(text: str) -> set[str]:
    raw = str(text or "").strip()
    if not raw or raw == NONE_LABEL:
        return set()
    normalized = raw.replace("，", LABEL_DELIMITER).replace(",", LABEL_DELIMITER)
    labels = {part.strip() for part in normalized.split(LABEL_DELIMITER) if part.strip()}
    if NONE_LABEL in labels and len(labels) > 1:
        labels.remove(NONE_LABEL)
    return labels


def label_f1(predicted: set[str], gold: set[str]) -> float:
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0
    pred_counter = Counter(predicted)
    gold_counter = Counter(gold)
    common = pred_counter & gold_counter
    n_common = sum(common.values())
    if n_common == 0:
        return 0.0
    precision = n_common / len(predicted)
    recall = n_common / len(gold)
    return 2 * precision * recall / (precision + recall)


def evaluate(response: str, gold_answer: str) -> dict:
    predicted_answer = extract_answer(response)
    predicted = labels_to_set(predicted_answer)
    gold = labels_to_set(gold_answer)
    accuracy = 1.0 if predicted == gold else 0.0
    missing_labels = [label for label in LABEL_ORDER if label in gold and label not in predicted]
    extra_labels = [label for label in LABEL_ORDER if label in predicted and label not in gold]
    unknown_labels = sorted(label for label in predicted if label not in KNOWN_LABELS)
    if NONE_LABEL in unknown_labels:
        unknown_labels.remove(NONE_LABEL)
    return {
        "accuracy": accuracy,
        "em": accuracy,
        "f1": label_f1(predicted, gold),
        "predicted_answer": predicted_answer or NONE_LABEL,
        "gold_answer": gold_answer,
        "predicted_labels": sorted(predicted),
        "gold_labels": sorted(gold),
        "missing_labels": missing_labels,
        "extra_labels": extra_labels,
        "unknown_labels": unknown_labels,
        "per_label": [
            {
                "label": label,
                "gold": label in gold,
                "predicted": label in predicted,
                "status": (
                    "tp" if label in gold and label in predicted
                    else "fn" if label in gold
                    else "fp" if label in predicted
                    else "tn"
                ),
            }
            for label in LABEL_ORDER
        ],
    }
