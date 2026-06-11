from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

COMMON_TRAIN_ROOT = Path(__file__).resolve().parents[3] / "train"
if str(COMMON_TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_TRAIN_ROOT))

from custom_model_runtime import call_custom_model_direct
from harness_chat import run_agent_chat
from skillopt.envs.searchqa.evaluator import evaluate


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_MAX_CONTEXT_CHARS = 6000


def _use_harness_for_model(model: str) -> bool:
    return str(model or "").strip().lower() in {"", "harness-default", "agent_harness"}


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8-sig").strip()


def _truncate_context(context: str, max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    if max_chars <= 0 or len(context) <= max_chars:
        return context
    docs = context.split("[DOC]")
    result = ""
    for doc in docs:
        candidate = result + "[DOC]" + doc if result else doc
        if len(candidate) > max_chars:
            break
        result = candidate
    return result or (context[:max_chars] + "\n...[truncated]")


def _build_system(skill_content: str) -> str:
    skill_section = f"## Skill\n{skill_content.strip()}\n\n" if skill_content.strip() else ""
    return _read_prompt("rollout_system.md").format(skill_section=skill_section)


def _build_user(
    question: str,
    context: str,
    *,
    max_context_chars: int,
    previous_response: str = "",
) -> str:
    parts = [
        f"## Context\n{_truncate_context(context, max_context_chars)}",
        f"## Question\n{question}",
    ]
    if previous_response:
        parts.append(
            "## Previous Attempt\n"
            f"{previous_response}\n\n"
            "Review it against the same context and question. If needed, correct it."
        )
    return "\n\n".join(parts)


def _build_prompt(system: str, user: str) -> str:
    return (
        "System instructions:\n"
        f"{system.strip()}\n\n"
        "User request:\n"
        f"{user.strip()}\n\n"
        "Answer the user request directly. Preserve the required output format exactly."
    )


def _call_target_model(
    prompt: str,
    *,
    target_model: str,
    timeout: int,
) -> tuple[str, str]:
    if _use_harness_for_model(target_model):
        response = run_agent_chat(
            prompt,
            model=target_model,
            timeout=timeout,
            stage="searchqa_rollout",
            cwd=PROJECT_ROOT,
            sandbox="read-only",
        )
        return response, response
    return call_custom_model_direct(prompt, model=target_model, stage="searchqa_rollout")


def _is_retryable_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ("timeout", "timed out", "temporarily", "rate limit", "connection"))


def process_one(
    item: dict,
    out_root: str,
    skill_content: str,
    *,
    target_model: str = "harness-default",
    max_turns: int = 1,
    exec_timeout: int = 300,
    llm_retries: int = 2,
    max_context_chars: int = _MAX_CONTEXT_CHARS,
) -> dict:
    item_id = str(item["id"])
    question = str(item.get("question") or "")
    context = str(item.get("context") or "")
    gold_answers = item.get("answers") or []
    if isinstance(gold_answers, str):
        gold_answers = [gold_answers]

    pred_dir = Path(out_root) / "predictions" / item_id
    pred_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "id": item_id,
        "question": question,
        "task_description": question,
        "task_type": item.get("task_type") or "qa",
        "em": 0.0,
        "f1": 0.0,
        "sub_em": 0.0,
        "hard": 0,
        "soft": 0.0,
        "predicted_answer": "",
        "gold_answers": gold_answers,
        "gold_answer": gold_answers,
        "response": "",
        "fail_reason": "",
        "agent_ok": False,
        "n_turns": 0,
    }

    system = _build_system(skill_content)
    response = ""
    conversation: list[dict] = []
    raw_response = ""
    try:
        for turn in range(max(int(max_turns), 1)):
            user = _build_user(
                question,
                context,
                max_context_chars=max_context_chars,
                previous_response=response if turn > 0 else "",
            )
            prompt = _build_prompt(system, user)
            (pred_dir / "target_system_prompt.txt").write_text(system, encoding="utf-8")
            (pred_dir / "target_user_prompt.txt").write_text(user, encoding="utf-8")
            (pred_dir / f"target_prompt_turn_{turn + 1}.txt").write_text(prompt, encoding="utf-8")

            last_exc: Exception | None = None
            for attempt in range(max(int(llm_retries), 1)):
                try:
                    response, raw_response = _call_target_model(
                        prompt,
                        target_model=target_model,
                        timeout=exec_timeout,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt >= max(int(llm_retries), 1) - 1 or not _is_retryable_error(exc):
                        raise
                    print(
                        f"    [rollout/llm] retry {attempt + 1}/{max(int(llm_retries), 1) - 1} "
                        f"for id={item_id} due to {type(exc).__name__}: {exc}",
                        flush=True,
                    )
            if last_exc is not None and not response:
                raise last_exc

            conversation.append({"role": "user", "turn": turn + 1, "content": user})
            conversation.append({"role": "assistant", "turn": turn + 1, "content": response})
            if raw_response != response:
                (pred_dir / f"target_response_raw_turn_{turn + 1}.txt").write_text(raw_response, encoding="utf-8")
            (pred_dir / "target_response.txt").write_text(response, encoding="utf-8")
            if turn > 0 and "<answer>" in response.lower():
                break

        eval_result = evaluate(response, gold_answers)
        result.update(
            {
                "em": eval_result["em"],
                "f1": eval_result["f1"],
                "sub_em": eval_result["sub_em"],
                "hard": int(eval_result["em"]),
                "soft": eval_result["f1"],
                "predicted_answer": eval_result["predicted_answer"],
                "response": response,
                "agent_ok": True,
                "n_turns": max(len(conversation) // 2, 1),
            }
        )
        if eval_result["em"] < 1.0:
            result["fail_reason"] = (
                f"EM=0: predicted {eval_result['predicted_answer']!r} "
                f"but expected {gold_answers!r}"
            )
        conversation.append(
            {
                "role": "system",
                "content": (
                    "[EVALUATION RESULT]\n"
                    f"Question: {question}\n"
                    f"Predicted answer: {eval_result['predicted_answer']!r}\n"
                    f"Gold answers: {gold_answers!r}\n"
                    f"Exact Match: {eval_result['em']}\n"
                    f"F1: {eval_result['f1']:.4f}"
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        result["fail_reason"] = f"error: {type(exc).__name__}: {exc}"

    (pred_dir / "conversation.json").write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _write_summary(out_root: Path, results: list[dict]) -> None:
    n_items = len(results)
    hard = sum(float(row.get("hard", 0) or 0) for row in results)
    f1 = sum(float(row.get("f1", row.get("soft", 0.0)) or 0.0) for row in results)
    sub_em = sum(float(row.get("sub_em", 0.0) or 0.0) for row in results)
    summary = {
        "n_items": n_items,
        "hard": hard / max(n_items, 1),
        "soft": f1 / max(n_items, 1),
        "metric": "f1",
        "em": hard / max(n_items, 1),
        "f1": f1 / max(n_items, 1),
        "sub_em": sub_em / max(n_items, 1),
        "hard_correct": int(hard),
        "hard_fail": n_items - int(hard),
    }
    (out_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_batch(
    items: list[dict],
    out_root: str,
    skill_content: str,
    max_turns: int = 1,
    exec_timeout: int = 300,
    workers: int = 1,
    max_completion_tokens: int = 4096,
    target_model: str = "harness-default",
    llm_retries: int = 2,
    max_context_chars: int = _MAX_CONTEXT_CHARS,
    task_timeout: int = 420,
    **_kwargs,
) -> list[dict]:
    del max_completion_tokens
    out_path = Path(out_root)
    out_path.mkdir(parents=True, exist_ok=True)
    results_path = out_path / "results.jsonl"
    task_timeout = max(int(task_timeout), int(exec_timeout) + 30)

    results: list[dict] = []
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
        _write_summary(out_path, results)
        return results

    total = len(results) + len(pending)
    completed = len(results)
    correct_count = sum(1 for row in results if row.get("hard"))
    started_at: dict[str, float] = {}

    def _timeout_result(item: dict) -> dict:
        return {
            "id": str(item["id"]),
            "question": item.get("question", ""),
            "task_description": item.get("question", ""),
            "task_type": item.get("task_type") or "qa",
            "hard": 0,
            "soft": 0.0,
            "em": 0.0,
            "f1": 0.0,
            "sub_em": 0.0,
            "predicted_answer": "",
            "gold_answers": item.get("answers", []),
            "gold_answer": item.get("answers", []),
            "response": "",
            "fail_reason": f"task-timeout-{task_timeout}s",
            "agent_ok": False,
            "n_turns": 0,
            "phase": "timeout",
        }

    def _run_one(item: dict) -> dict:
        started_at[str(item["id"])] = time.time()
        return process_one(
            item,
            str(out_path),
            skill_content,
            target_model=target_model,
            max_turns=max_turns,
            exec_timeout=exec_timeout,
            llm_retries=llm_retries,
            max_context_chars=max_context_chars,
        )

    with results_path.open("a", encoding="utf-8", newline="\n") as output:
        executor = ThreadPoolExecutor(max_workers=max(int(workers), 1))
        try:
            futures = {executor.submit(_run_one, item): item for item in pending}
            pending_futures = set(futures)
            while pending_futures:
                done, _ = wait(pending_futures, timeout=5, return_when=FIRST_COMPLETED)
                now = time.time()
                timed_out = [
                    fut for fut in pending_futures - done
                    if str(futures[fut]["id"]) in started_at
                    and now - started_at[str(futures[fut]["id"])] >= task_timeout
                ]
                for fut in done:
                    pending_futures.remove(fut)
                    item = futures[fut]
                    try:
                        row = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        row = _timeout_result(item)
                        row["phase"] = "error"
                        row["fail_reason"] = f"unexpected: {type(exc).__name__}: {exc}"
                    results.append(row)
                    completed += 1
                    correct_count += int(bool(row.get("hard")))
                    acc = correct_count / completed if completed else 0.0
                    print(
                        f"    [rollout/llm] {completed}/{total} "
                        f"(sample_acc={acc:.3f}) id={row['id']} hard={row.get('hard', '?')}",
                        flush=True,
                    )
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    output.flush()
                for fut in timed_out:
                    pending_futures.remove(fut)
                    fut.cancel()
                    row = _timeout_result(futures[fut])
                    results.append(row)
                    completed += 1
                    acc = correct_count / completed if completed else 0.0
                    print(
                        f"    [rollout/llm] {completed}/{total} "
                        f"(sample_acc={acc:.3f}) id={row['id']} TIMEOUT",
                        flush=True,
                    )
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    output.flush()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    _write_summary(out_path, results)
    return results
