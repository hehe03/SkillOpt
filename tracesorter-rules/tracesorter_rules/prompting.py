from __future__ import annotations

import json
from typing import Any

from .skill import load_skill_payload


def _compact_row(row: dict[str, Any], *, include_features: bool) -> dict[str, Any]:
    compact = {
        "id": row.get("id"),
        "label": row.get("label"),
        "predicted_label": row.get("predicted_label"),
        "bad_score": row.get("bad_score"),
        "good_score": row.get("good_score"),
        "reason": row.get("reason"),
        "matched_rules": row.get("matched_rules", [])[:8],
    }
    if include_features:
        features = row.get("features") or {}
        compact["features"] = {
            key: value
            for key, value in sorted(features.items())
            if isinstance(value, (str, int, float, bool))
        }
    return compact


def build_rule_optimization_prompt(
    *,
    skill_path: str,
    summary: dict[str, Any],
    predictions: list[dict[str, Any]],
    max_failures: int = 20,
    max_successes: int = 8,
    include_features: bool = True,
) -> str:
    payload = load_skill_payload(skill_path)
    failures = [row for row in predictions if row.get("label") in {"goodcase", "badcase"} and not row.get("hard")]
    successes = [row for row in predictions if row.get("label") in {"goodcase", "badcase"} and row.get("hard")]

    prompt_data = {
        "current_summary": summary,
        "current_skill": payload,
        "failure_cases": [_compact_row(row, include_features=include_features) for row in failures[:max_failures]],
        "success_examples": [_compact_row(row, include_features=include_features) for row in successes[:max_successes]],
    }
    return (
        "你是 TraceSorter 规则优化器。任务是优化 goodcase/badcase 分类规则。\n\n"
        "请根据当前规则、评估指标、误判样本和成功样本，输出一份新的规则 JSON。\n"
        "目标优先级：\n"
        "1. 提升 badcase precision，避免把 goodcase 误杀为 badcase。\n"
        "2. 在 precision 不明显下降的前提下提升 badcase recall。\n"
        "3. 保持规则可解释，优先使用已给出的 features。\n\n"
        "约束：\n"
        "- 只输出一个 JSON 对象，或放在 ```json 代码块中。\n"
        "- JSON 必须包含 bad_threshold、good_threshold、rules。\n"
        "- 每条 rule 必须包含 id、label、weight、group、description，以及 all 或 any 条件。\n"
        "- label 只能是 goodcase 或 badcase。\n"
        "- 支持的 op 只有 ==、!=、>、>=、<、<=、contains、regex、truthy、falsey。\n"
        "- 不要发明 Python 代码，不要修改评估程序。\n\n"
        "可用上下文如下：\n\n"
        "```json\n"
        f"{json.dumps(prompt_data, ensure_ascii=False, indent=2)}\n"
        "```\n"
    )
