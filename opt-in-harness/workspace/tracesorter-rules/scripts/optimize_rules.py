from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.evaluator import evaluate_split
from tracesorter_rules.llm import call_cli_llm, call_custom_llm, write_harness_task
from tracesorter_rules.prompting import build_rule_optimization_prompt
from tracesorter_rules.skill import parse_skill_payload_from_text, write_skill_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="用 LLM 根据误判样本优化 TraceSorter 规则 skill。")
    parser.add_argument("--skill", required=True, help="当前规则 skill Markdown。")
    parser.add_argument("--split-dir", required=True, help="包含 train/val/test 或 train/test 的 split 目录。")
    parser.add_argument("--split", default="train", choices=["train", "val", "test"], help="用于生成误判反馈的 split。")
    parser.add_argument("--work-dir", required=True, help="本轮优化的工作目录。")
    parser.add_argument("--out-skill", required=True, help="优化后的 skill Markdown 输出路径。")
    parser.add_argument(
        "--llm-provider",
        choices=["custom", "cli", "codex", "opencode", "harness", "prompt_only"],
        default="prompt_only",
        help="custom 调用 llm_generate；cli 调任意命令；harness 生成当前对话接力任务；prompt_only 只写 prompt。",
    )
    parser.add_argument("--llm-timeout", type=int, default=600, help="CLI LLM 超时时间，单位秒。")
    parser.add_argument(
        "--llm-command",
        nargs="+",
        help=(
            "覆盖 CLI 默认命令。可使用 {prompt}、{prompt_file} 或 {stdin}。"
            "例如: --llm-command codex exec --skip-git-repo-check {prompt}"
        ),
    )
    parser.add_argument("--max-failures", type=int, default=20)
    parser.add_argument("--max-successes", type=int, default=8)
    parser.add_argument("--max-items", type=int, default=0, help="评估前 N 条样本；0 表示全部。")
    parser.add_argument("--no-features", action="store_true", help="prompt 中不包含完整标量 features。")
    return parser


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    work_dir = Path(args.work_dir)
    eval_dir = work_dir / "eval_current"
    work_dir.mkdir(parents=True, exist_ok=True)

    summary = evaluate_split(
        skill_path=args.skill,
        split_dir=args.split_dir,
        split=args.split,
        out_root=eval_dir,
        max_items=args.max_items,
    )
    predictions = _load_json(eval_dir / "predictions.json")
    if not isinstance(predictions, list):
        raise ValueError("predictions.json must contain a list")

    prompt = build_rule_optimization_prompt(
        skill_path=args.skill,
        summary=summary,
        predictions=predictions,
        max_failures=args.max_failures,
        max_successes=args.max_successes,
        include_features=not args.no_features,
    )
    prompt_path = work_dir / "rule_optimization_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    if args.llm_provider == "prompt_only":
        print("已生成 prompt，未调用 LLM。")
        print(f"Prompt: {prompt_path.resolve()}")
        print("你可以把该 prompt 交给当前对话 harness，再将响应中的 JSON 保存为新的 skill。")
        return

    if args.llm_provider == "harness":
        response_path = work_dir / "harness_response.md"
        task_path = work_dir / "harness_task.md"
        write_harness_task(
            prompt=prompt,
            task_path=task_path,
            response_path=response_path,
            out_skill=args.out_skill,
        )
        print("已生成当前对话 harness 任务，未调用外部 API。")
        print(f"Harness task: {task_path.resolve()}")
        print(f"请让当前对话 Agent 将响应写入: {response_path.resolve()}")
        print("然后运行:")
        print(
            "python .\\tracesorter-rules\\scripts\\apply_llm_response.py "
            f"--response {response_path} --out-skill {args.out_skill}"
        )
        return

    if args.llm_provider == "custom":
        response = call_custom_llm(prompt)
    else:
        cli_provider = "codex" if args.llm_provider == "cli" else args.llm_provider
        if args.llm_provider == "cli" and not args.llm_command:
            raise ValueError("--llm-provider cli 必须同时提供 --llm-command。")
        response = call_cli_llm(
            prompt,
            provider=cli_provider,
            command=args.llm_command,
            timeout=args.llm_timeout,
        )

    response_path = work_dir / "llm_response.md"
    response_path.write_text(response, encoding="utf-8")
    payload = parse_skill_payload_from_text(response)
    write_skill_markdown(payload, args.out_skill)
    print("规则优化完成")
    print(f"当前评估目录: {eval_dir.resolve()}")
    print(f"Prompt: {prompt_path.resolve()}")
    print(f"LLM 响应: {response_path.resolve()}")
    print(f"优化后 skill: {Path(args.out_skill).resolve()}")


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
