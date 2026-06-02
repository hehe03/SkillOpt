from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from shortage_analyze_skillopt.evaluator import evaluate
from shortage_analyze_skillopt.harness_chat import run_agent_chat


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLOPT_ROOT = PROJECT_ROOT / "shortage_analyze-opt"
DEFAULT_INITIAL_SKILL = SKILLOPT_ROOT / "shortage_analyze-optimized" / "init" / "initial_skill.md"
DEFAULT_INITIAL_SCRIPT = SKILLOPT_ROOT / "shortage_analyze-optimized" / "init" / "analyze_shortage.py"
NONE_LABEL = "- 未匹配到分支"


def _skill_hash(skill_content: str) -> str:
    return hashlib.sha256(skill_content.encode("utf-8")).hexdigest()[:16]


def _read_text_if_exists(path: str | os.PathLike[str]) -> str:
    resolved = Path(path)
    if not resolved.exists():
        return ""
    return resolved.read_text(encoding="utf-8").strip()


def _same_skill_content(left: str, right_path: str | os.PathLike[str]) -> bool:
    right = _read_text_if_exists(right_path)
    return bool(right) and left.strip() == right


def _extract_python_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip() + "\n"
    return text.strip() + "\n"


def _build_codegen_prompt(skill_content: str, reference_script: str) -> str:
    return f"""你要把一个欠料归因 Skill 文档转换为可运行 Python 脚本。

要求：
1. 只输出完整 Python 代码，不要解释，不要 Markdown 代码围栏。
2. 规则来源只能是“当前 Skill 文档”；参考脚本只用于接口和工程风格。
3. 脚本不得读取 data.xlsx、测试集标签、训练 split、references 或其它外部规则文件。
4. 必须提供以下函数：
   - `predict_labels(features: dict) -> list[str]`
   - `format_prediction(labels: list[str]) -> str`
5. 可选提供 CLI：`--input-split`、`--input-excel`、`--output`、`--output-excel`、`--sheet`。
6. 标签顺序固定为：网容异常、用量异常、补库异常、基线异常、计划参数异常、补库供应不及时、责任库房异常、替代交付异常。
7. 无命中时 `format_prediction` 返回 `- 未匹配到分支`，多个标签用中文顿号 `、` 连接。
8. 稳健处理空值、数字转换、`d/h` 时间单位、字符串列表字段。

## 当前 Skill 文档

{skill_content}

## 接口参考脚本

{reference_script}
"""


def _run_codex_codegen(prompt: str, *, timeout: int, model: str) -> str:
    return run_agent_chat(
        prompt,
        model=model,
        timeout=timeout,
        stage="script_codegen",
        cwd=PROJECT_ROOT,
        sandbox="read-only",
    )


def _load_module(path: Path):
    module_name = f"shortage_generated_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import generated script from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _validate_predictor(path: Path) -> None:
    module = _load_module(path)
    if not callable(getattr(module, "predict_labels", None)):
        raise AttributeError(f"{path} must define predict_labels(features)")
    if not callable(getattr(module, "format_prediction", None)):
        raise AttributeError(f"{path} must define format_prediction(labels)")


def resolve_script_for_skill(
    *,
    skill_content: str,
    script_cache_dir: str,
    initial_skill_path: str,
    initial_script_path: str,
    codegen_timeout: int,
    codegen_model: str,
) -> Path:
    initial_script = Path(initial_script_path)
    if _same_skill_content(skill_content, initial_skill_path):
        _validate_predictor(initial_script)
        return initial_script

    cache_root = Path(script_cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    digest = _skill_hash(skill_content)
    script_dir = cache_root / digest
    script_path = script_dir / "analyze_shortage.py"
    skill_path = script_dir / "skill.md"
    prompt_path = script_dir / "codegen_prompt.md"
    raw_path = script_dir / "codegen_response.txt"
    script_dir.mkdir(parents=True, exist_ok=True)

    if script_path.exists():
        _validate_predictor(script_path)
        return script_path

    reference_script = Path(initial_script_path).read_text(encoding="utf-8")
    prompt = _build_codegen_prompt(skill_content, reference_script)
    skill_path.write_text(skill_content, encoding="utf-8")
    prompt_path.write_text(prompt, encoding="utf-8")
    response = _run_codex_codegen(prompt, timeout=codegen_timeout, model=codegen_model)
    raw_path.write_text(response, encoding="utf-8")
    script_path.write_text(_extract_python_code(response), encoding="utf-8")
    _validate_predictor(script_path)
    return script_path


def _prediction_from_module(module, features: dict[str, Any]) -> str:
    labels = module.predict_labels(features)
    return str(module.format_prediction(labels))


def _build_result(item: dict[str, Any], prediction: str, *, script_path: Path, skill_content: str) -> dict[str, Any]:
    item_id = str(item["id"])
    question = str(item.get("question") or "")
    gold_answer = str(item.get("ground_truth") or "")
    response = f"<answer>{prediction or NONE_LABEL}</answer>"
    result: dict[str, Any] = {
        "id": item_id,
        "question": question,
        "task_description": question[:1000],
        "task_type": item.get("task_type") or "shortage_analyze",
        "hard": 0,
        "soft": 0.0,
        "em": 0.0,
        "f1": 0.0,
        "predicted_answer": prediction or NONE_LABEL,
        "gold_answer": gold_answer,
        "predicted_labels": [],
        "gold_labels": [],
        "missing_labels": [],
        "extra_labels": [],
        "per_label": [],
        "response": response,
        "fail_reason": "",
        "agent_ok": True,
        "n_turns": 1,
        "executor": "generated_script",
        "script_path": str(script_path),
    }

    conversation: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "目标执行由当前 skill 生成的 Python 规则脚本完成，而不是让 LLM 逐条阅读理解。"
                f"\nScript: {script_path}\n\n## Current Skill\n{skill_content[:5000]}"
            ),
        },
        {"role": "user", "content": question},
        {"role": "assistant", "content": response},
    ]

    if gold_answer:
        eval_result = evaluate(response, gold_answer)
        result.update(
            {
                "accuracy": eval_result["accuracy"],
                "em": eval_result["accuracy"],
                "f1": eval_result["f1"],
                "hard": int(eval_result["accuracy"]),
                "soft": eval_result["accuracy"],
                "predicted_answer": eval_result["predicted_answer"],
                "predicted_labels": eval_result["predicted_labels"],
                "gold_labels": eval_result["gold_labels"],
                "missing_labels": eval_result["missing_labels"],
                "extra_labels": eval_result["extra_labels"],
                "per_label": eval_result["per_label"],
                "unknown_labels": eval_result["unknown_labels"],
            }
        )
        if eval_result["accuracy"] < 1.0:
            result["fail_reason"] = (
                f"accuracy=0: predicted {eval_result['predicted_answer']!r} "
                f"but expected {gold_answer!r}; "
                f"missing={eval_result['missing_labels']}; "
                f"extra={eval_result['extra_labels']}"
            )
        conversation.append(
            {
                "role": "system",
                "content": (
                    "[EVALUATION RESULT]\n"
                    f"Predicted answer: {eval_result['predicted_answer']!r}\n"
                    f"Gold answer: {gold_answer!r}\n"
                    f"Accuracy: {eval_result['accuracy']}\n"
                    f"F1: {eval_result['f1']:.4f}\n"
                    f"Missing labels: {eval_result['missing_labels']}\n"
                    f"Extra labels: {eval_result['extra_labels']}\n"
                    "Per-label comparison:\n"
                    + "\n".join(
                        f"- {row['label']}: gold={row['gold']} "
                        f"predicted={row['predicted']} status={row['status']}"
                        for row in eval_result["per_label"]
                        if row["status"] != "tn"
                    )
                ),
            }
        )
    else:
        result["fail_reason"] = "unlabeled item; skipped scoring"
    result["_conversation"] = conversation
    return result


def run_batch(
    *,
    items: list[dict],
    out_root: str,
    skill_content: str,
    workers: int = 4,
    exec_timeout: int = 300,
    max_completion_tokens: int = 4096,
    diagnostic_mode: bool = False,
    diagnostic_instruction: str = "",
    task_timeout: int = 600,
    script_cache_dir: str = "",
    initial_skill_path: str = str(DEFAULT_INITIAL_SKILL),
    initial_script_path: str = str(DEFAULT_INITIAL_SCRIPT),
    script_codegen_timeout: int = 900,
    script_codegen_model: str = "",
) -> list[dict]:
    del workers, exec_timeout, max_completion_tokens, diagnostic_mode, diagnostic_instruction, task_timeout
    out_path = Path(out_root)
    out_path.mkdir(parents=True, exist_ok=True)
    results_path = out_path / "results.jsonl"
    predictions_dir = out_path / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if results_path.exists():
        with results_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done_ids.add(str(row.get("id")))
                results.append(row)

    pending = [item for item in items if str(item["id"]) not in done_ids]
    if not pending:
        return results

    initial_skill_path = initial_skill_path or str(DEFAULT_INITIAL_SKILL)
    initial_script_path = initial_script_path or str(DEFAULT_INITIAL_SCRIPT)
    cache_dir = script_cache_dir or str(out_path.parents[1] / "generated_scripts")
    codegen_model = script_codegen_model or os.environ.get("OPTIMIZER_DEPLOYMENT") or os.environ.get("CODEX_MODEL") or "gpt-5.5"
    script_path = resolve_script_for_skill(
        skill_content=skill_content,
        script_cache_dir=cache_dir,
        initial_skill_path=initial_skill_path,
        initial_script_path=initial_script_path,
        codegen_timeout=script_codegen_timeout,
        codegen_model=codegen_model,
    )
    module = _load_module(script_path)

    total = len(results) + len(pending)
    correct_count = sum(1 for row in results if row.get("hard"))
    with results_path.open("a", encoding="utf-8", newline="\n") as outf:
        for item in pending:
            item_id = str(item["id"])
            pred_dir = predictions_dir / item_id
            pred_dir.mkdir(parents=True, exist_ok=True)
            try:
                prediction = _prediction_from_module(module, dict(item.get("features") or {}))
                row = _build_result(item, prediction, script_path=script_path, skill_content=skill_content)
            except Exception as exc:  # noqa: BLE001
                row = {
                    "id": item_id,
                    "question": item.get("question", ""),
                    "task_description": str(item.get("question", ""))[:1000],
                    "task_type": item.get("task_type") or "shortage_analyze",
                    "hard": 0,
                    "soft": 0.0,
                    "predicted_answer": "",
                    "gold_answer": item.get("ground_truth", ""),
                    "response": "",
                    "fail_reason": f"script-error: {type(exc).__name__}: {exc}",
                    "agent_ok": False,
                    "n_turns": 0,
                    "executor": "generated_script",
                    "script_path": str(script_path),
                    "_conversation": [
                        {
                            "role": "system",
                            "content": f"Generated script execution failed: {type(exc).__name__}: {exc}",
                        }
                    ],
                }

            conversation = row.pop("_conversation", [])
            (pred_dir / "conversation.json").write_text(
                json.dumps(conversation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (pred_dir / "target_system_prompt.txt").write_text(
                f"Program executor generated from current skill.\nScript: {script_path}\n",
                encoding="utf-8",
            )
            (pred_dir / "target_user_prompt.txt").write_text(
                str(item.get("question") or ""),
                encoding="utf-8",
            )
            outf.write(json.dumps(row, ensure_ascii=False) + "\n")
            outf.flush()
            results.append(row)
            correct_count += int(bool(row.get("hard")))
            acc = correct_count / len(results) if results else 0.0
            print(
                f"    [rollout/script] {len(results)}/{total} "
                f"(acc={acc:.3f}) id={row['id']} hard={row.get('hard', '?')}",
                flush=True,
            )
    return results
