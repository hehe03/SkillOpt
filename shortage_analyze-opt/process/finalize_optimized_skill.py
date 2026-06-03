from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLOPT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = SKILLOPT_ROOT / "train"


def _load_harness_chat():
    module_path = TRAIN_DIR / "shortage_analyze_skillopt" / "harness_chat.py"
    spec = importlib.util.spec_from_file_location("shortage_analyze_harness_chat", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 harness_chat.py: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_HARNESS_CHAT = _load_harness_chat()
describe_agent_backend = _HARNESS_CHAT.describe_agent_backend
run_agent_chat = _HARNESS_CHAT.run_agent_chat


DEFAULT_SKILLOPT_OUTPUT = SKILLOPT_ROOT / "train" / "outputs" / "shortage_analyze"
DEFAULT_BEST_SKILL = SKILLOPT_ROOT / "shortage_analyze-optimized" / "best" / "best_kill.md"
DEFAULT_OUTPUT_SCRIPT = (
    SKILLOPT_ROOT / "shortage_analyze-optimized" / "best" / "scripts" / "analyze_shortage.py"
)
DEFAULT_INITIAL_SCRIPT = SKILLOPT_ROOT / "shortage_analyze-init" / "analyze_shortage.py"


def configure_windows_utf8_stdio() -> None:
    """Keep Chinese console output readable on Windows when possible."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将 SkillOpt 输出的 best_skill.md 落到 shortage_analyze-optimized/best，并生成对应快速预测脚本。"
    )
    parser.add_argument(
        "--skillopt-output",
        default=str(DEFAULT_SKILLOPT_OUTPUT),
        help="SkillOpt 训练输出目录，目录下应包含 best_skill.md。",
    )
    parser.add_argument("--best-skill", default=str(DEFAULT_BEST_SKILL))
    parser.add_argument("--output-script", default=str(DEFAULT_OUTPUT_SCRIPT))
    parser.add_argument(
        "--initial-script",
        "--original-script",
        dest="initial_script",
        default=str(DEFAULT_INITIAL_SCRIPT),
        help="初始规则脚本路径，仅作为接口和工程风格参考；--original-script 是兼容旧命令的别名。",
    )
    parser.add_argument(
        "--script-mode",
        choices=("agent", "codex", "copy-initial", "copy-original", "skip"),
        default="agent",
        help=(
            "agent=用当前 harness 自带模型从 best skill 生成脚本；"
            "codex=兼容旧参数，仍走统一 harness 接口；"
            "copy-initial/copy-original=复制初始脚本作占位；skip=只落 best skill。"
        ),
    )
    parser.add_argument(
        "--codex-bin",
        default=os.environ.get("CODEX_CLI_BIN") or os.environ.get("CODEX_EXEC_PATH") or "",
        help="兼容旧参数。填写后会写入 CODEX_CLI_BIN，但不会绕过统一 harness 接口。",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SHORTAGE_ANALYZE_AGENT_MODEL", "harness-default"),
        help="传给当前 Agent harness 的模型名；harness-default 表示使用 harness 默认模型。",
    )
    parser.add_argument("--timeout", type=int, default=900)
    return parser


def extract_python_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip() + "\n"
    return text.strip() + "\n"


def build_codegen_prompt(best_skill: str, initial_script: str) -> str:
    return f"""你要把一个优化后的欠料归因规则 Skill 文档转换为可运行 Python 脚本。

要求：
1. 只输出完整 Python 代码，不要解释，不要 Markdown 代码围栏。
2. 脚本接口必须兼容训练和评估脚本：
   - `predict_labels(features: dict) -> list[str]`
   - `format_prediction(labels: list[str]) -> str`
   - 支持命令行 `--input-split`、`--input-excel`、`--output`、`--output-excel`、`--sheet`
   - 对 Excel 输入新增 `L2分类结果` 列。
3. 规则来源只能是“优化后的 Skill 文档”。不要读取 `data.xlsx`、测试集标签、训练数据、`references/` 或其它外部规则文件。
4. 保持标签顺序：网容异常、用量异常、补库异常、基线异常、计划参数异常、补库供应不及时、责任库房异常、替代交付异常。
5. 无命中时输出 `- 未匹配到分支`，多个标签用 `、` 连接。
6. 代码应稳健处理空值、数字转换、`d/h` 时间单位、字符串列表字段。

## 优化后的 Skill 文档

{best_skill}

## 初始脚本接口参考

下面的初始脚本只作为接口和工程风格参考。规则逻辑应以优化后的 Skill 文档为准。

```python
{initial_script}
```
"""


def run_agent_codegen(prompt: str, *, model: str, timeout: int) -> str:
    return run_agent_chat(
        prompt,
        model=model,
        timeout=timeout,
        stage="finalize_script_codegen",
        cwd=PROJECT_ROOT,
        sandbox="read-only",
    )


def run(args: argparse.Namespace) -> None:
    if args.codex_bin and "CODEX_CLI_BIN" not in os.environ:
        os.environ["CODEX_CLI_BIN"] = args.codex_bin

    skillopt_output = Path(args.skillopt_output)
    source_best = skillopt_output / "best_skill.md"
    if not source_best.exists():
        raise FileNotFoundError(f"找不到 SkillOpt best_skill.md: {source_best}")

    best_skill_path = Path(args.best_skill)
    output_script_path = Path(args.output_script)
    best_skill_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_best, best_skill_path)
    print(f"已复制优化后 skill: {source_best} -> {best_skill_path}")

    if args.script_mode == "skip":
        return

    output_script_path.parent.mkdir(parents=True, exist_ok=True)
    if args.script_mode in {"copy-initial", "copy-original"}:
        shutil.copy2(Path(args.initial_script), output_script_path)
        print(f"已复制初始脚本作为占位: {output_script_path}")
        return

    best_skill = best_skill_path.read_text(encoding="utf-8-sig")
    initial_script = Path(args.initial_script).read_text(encoding="utf-8-sig")
    prompt = build_codegen_prompt(best_skill, initial_script)
    print(f"使用当前 Agent harness 生成优化规则脚本: {describe_agent_backend()}")
    response = run_agent_codegen(prompt, model=args.model, timeout=args.timeout)
    code = extract_python_code(response)
    output_script_path.write_text(code, encoding="utf-8")
    print(f"已生成优化规则脚本: {output_script_path}")


def main(argv: Sequence[str] | None = None) -> None:
    configure_windows_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--skillopt-output",
        str(DEFAULT_SKILLOPT_OUTPUT),
        "--best-skill",
        str(DEFAULT_BEST_SKILL),
        "--output-script",
        str(DEFAULT_OUTPUT_SCRIPT),
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
