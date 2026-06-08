from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

COMMON_TRAIN_ROOT = Path(__file__).resolve().parents[3] / "train"
if str(COMMON_TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_TRAIN_ROOT))
TRAIN_ROOT = Path(__file__).resolve().parent
if str(TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(TRAIN_ROOT))

from evaluator import evaluate
from harness_chat import run_agent_chat


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    keep_head = max_chars // 2
    keep_tail = max_chars - keep_head
    return text[:keep_head] + "\n\n...[trace truncated]...\n\n" + text[-keep_tail:]


def _json_dumps(value: Any, *, max_chars: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        text = str(value)
    return _truncate_text(text, max_chars)


def _build_prompt(item: dict[str, Any], skill_content: str, *, max_trace_chars: int) -> str:
    features = dict(item.get("features") or {})
    trace = features.get("trace", item.get("trace"))
    parse_error = features.get("parse_error") or item.get("parse_error")
    source = features.get("source") or item.get("metadata", {}).get("source")
    source_text = f"\nTrace source: {source}" if source else ""
    parse_error_text = f"\nTrace parse_error: {parse_error}" if parse_error else ""
    trace_text = _json_dumps(trace, max_chars=max_trace_chars)
    return (
        "你是一个严格遵守 skill 文档的 trace 分类器。"
        "请只根据 trace 内容判断，不要根据文件名、样本 id、split 或标签推断。\n\n"
        "## Current Skill\n"
        f"{skill_content.strip()}\n\n"
        "## Input Trace"
        f"{source_text}{parse_error_text}\n"
        "```json\n"
        f"{trace_text}\n"
        "```\n\n"
        "请严格输出一个 JSON object，字段为 label、confidence、reasons、evidence、risk_signals。"
    )


def _build_result(
    item: dict[str, Any],
    response: str,
    *,
    prompt: str,
    prediction_dir: Path,
) -> dict[str, Any]:
    item_id = str(item["id"])
    gold_answer = str(item.get("ground_truth") or "")
    eval_result = evaluate(response, gold_answer) if gold_answer else {
        "hard": 0,
        "soft": 0.0,
        "accuracy": 0.0,
        "prediction": "",
        "predicted_label": "",
        "gold_answer": "",
        "gold_label": "",
        "confidence": 0.0,
        "reasons": [],
        "evidence": [],
        "risk_signals": [],
        "parse_ok": False,
    }
    result = {
        "id": item_id,
        "question": item.get("question") or f"Classify trace {item_id} as goodcase or badcase.",
        "task_description": "Classify an Agent execution trace as goodcase or badcase.",
        "task_type": item.get("task_type") or "trace_classification",
        "hard": eval_result["hard"],
        "soft": eval_result["soft"],
        "accuracy": eval_result["accuracy"],
        "predicted_answer": eval_result["predicted_label"],
        "predicted_label": eval_result["predicted_label"],
        "gold_answer": eval_result["gold_label"],
        "gold_label": eval_result["gold_label"],
        "confidence": eval_result["confidence"],
        "reasons": eval_result["reasons"],
        "evidence": eval_result["evidence"],
        "risk_signals": eval_result["risk_signals"],
        "parse_ok": eval_result["parse_ok"],
        "response": response,
        "fail_reason": "",
        "agent_ok": True,
        "n_turns": 1,
        "executor": "llm_direct",
        "metadata": item.get("metadata", {}),
    }
    if gold_answer and not result["hard"]:
        result["fail_reason"] = (
            f"predicted={result['predicted_label']!r}, "
            f"gold={result['gold_label']!r}, parse_ok={result['parse_ok']}"
        )
    elif not gold_answer:
        result["fail_reason"] = "unlabeled item; skipped scoring"

    conversation = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response},
        {
            "role": "system",
            "content": (
                "[EVALUATION RESULT]\n"
                f"Predicted label: {result['predicted_label']!r}\n"
                f"Gold label: {result['gold_label']!r}\n"
                f"Hard: {result['hard']}\n"
                f"Reasons: {result['reasons']}\n"
                f"Evidence: {result['evidence']}\n"
                f"Risk signals: {result['risk_signals']}"
            ),
        },
    ]
    prediction_dir.mkdir(parents=True, exist_ok=True)
    (prediction_dir / "conversation.json").write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (prediction_dir / "target_user_prompt.txt").write_text(prompt, encoding="utf-8")
    (prediction_dir / "target_response.txt").write_text(response, encoding="utf-8")
    return result


def run_batch(
    *,
    items: list[dict],
    out_root: str,
    skill_content: str,
    workers: int = 1,
    llm_timeout: int = 300,
    max_trace_chars: int = 24000,
    target_model: str = "harness-default",
) -> list[dict]:
    del workers
    out_path = Path(out_root)
    out_path.mkdir(parents=True, exist_ok=True)
    predictions_dir = out_path / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_path / "results.jsonl"

    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if results_path.exists():
        with results_path.open(encoding="utf-8-sig") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done_ids.add(str(row.get("id")))
                results.append(row)

    pending = [item for item in items if str(item["id"]) not in done_ids]
    if not pending:
        return results

    total = len(results) + len(pending)
    correct_count = sum(1 for row in results if row.get("hard"))
    with results_path.open("a", encoding="utf-8", newline="\n") as output:
        for item in pending:
            item_id = str(item["id"])
            prompt = _build_prompt(item, skill_content, max_trace_chars=max_trace_chars)
            prediction_dir = predictions_dir / item_id
            try:
                response = run_agent_chat(
                    prompt,
                    model=target_model,
                    timeout=llm_timeout,
                    stage="tracesorter_rollout",
                    cwd=PROJECT_ROOT,
                    sandbox="read-only",
                )
                row = _build_result(item, response, prompt=prompt, prediction_dir=prediction_dir)
            except Exception as exc:  # noqa: BLE001
                prediction_dir.mkdir(parents=True, exist_ok=True)
                (prediction_dir / "target_user_prompt.txt").write_text(prompt, encoding="utf-8")
                row = {
                    "id": item_id,
                    "question": item.get("question") or f"Classify trace {item_id}.",
                    "task_description": "Classify an Agent execution trace as goodcase or badcase.",
                    "task_type": item.get("task_type") or "trace_classification",
                    "hard": 0,
                    "soft": 0.0,
                    "predicted_answer": "",
                    "predicted_label": "",
                    "gold_answer": item.get("ground_truth", ""),
                    "gold_label": item.get("ground_truth", ""),
                    "response": "",
                    "fail_reason": f"llm-error: {type(exc).__name__}: {exc}",
                    "agent_ok": False,
                    "n_turns": 0,
                    "executor": "llm_direct",
                }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            results.append(row)
            correct_count += int(bool(row.get("hard")))
            acc = correct_count / len(results) if results else 0.0
            print(
                f"    [rollout/llm] {len(results)}/{total} "
                f"(acc={acc:.3f}) id={item_id} hard={row.get('hard', '?')}",
                flush=True,
            )
    return results
