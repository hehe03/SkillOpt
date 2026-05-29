from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def llm_generate(prompt: str) -> str:
    """自定义 LLM 接入点。

    你可以在这里接入任意模型、公司内部网关或本地推理服务。
    输入是完整 prompt，返回值应是 LLM 原始响应文本，响应中需要包含 JSON 规则对象。
    默认返回空字符串，表示尚未接入。
    """

    return ""


def call_custom_llm(prompt: str) -> str:
    response = llm_generate(prompt)
    if not response.strip():
        raise RuntimeError(
            "llm_generate(prompt) returned empty response. "
            "请在 tracesorter_rules/llm.py 中实现 llm_generate，或改用 --llm-provider codex/opencode/prompt_only。"
        )
    return response


def _default_command(provider: str) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", "--skip-git-repo-check", "{prompt}"]
    if provider == "opencode":
        return ["opencode", "run", "{prompt}"]
    raise ValueError(f"unsupported CLI provider: {provider}")


def _build_command(provider: str, prompt: str, command: list[str] | None, prompt_file: Path) -> tuple[list[str], str | None]:
    parts = command or _default_command(provider)
    if not parts:
        raise ValueError("LLM command cannot be empty")

    has_stdin = False
    rendered: list[str] = []
    for part in parts:
        if part == "{stdin}":
            has_stdin = True
            continue
        rendered.append(
            part.replace("{prompt}", prompt).replace("{prompt_file}", str(prompt_file))
        )

    stdin_text = prompt if has_stdin or ("{prompt}" not in " ".join(parts) and "{prompt_file}" not in " ".join(parts)) else None
    return rendered, stdin_text


def call_cli_llm(
    prompt: str,
    *,
    provider: str,
    command: list[str] | None = None,
    timeout: int = 600,
) -> str:
    with tempfile.TemporaryDirectory(prefix="tracesorter_llm_") as tmp:
        prompt_file = Path(tmp) / "prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        cmd, stdin_text = _build_command(provider, prompt, command, prompt_file)
        completed = subprocess.run(
            cmd,
            input=stdin_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    output = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"{provider} command failed with exit code {completed.returncode}.\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr:\n{stderr}"
        )
    if not output:
        raise RuntimeError(f"{provider} command returned empty stdout. stderr:\n{stderr}")
    return output


def write_harness_task(
    *,
    prompt: str,
    task_path: str | Path,
    response_path: str | Path,
    out_skill: str | Path,
) -> None:
    task = (
        "# TraceSorter Harness 规则优化任务\n\n"
        "请使用当前对话所在 harness 自带的大模型完成本任务，不需要 API key。\n\n"
        "## 输入\n\n"
        "下面是规则优化 prompt。请阅读 prompt，生成新的规则 JSON。\n\n"
        "## 输出要求\n\n"
        f"- 将 LLM 响应写入：`{Path(response_path).resolve()}`\n"
        f"- 响应必须包含一个 JSON 对象，包含 `bad_threshold`、`good_threshold`、`rules`。\n"
        f"- 之后可运行 `apply_llm_response.py` 生成：`{Path(out_skill).resolve()}`\n\n"
        "## Prompt\n\n"
        f"{prompt}\n"
    )
    Path(task_path).write_text(task, encoding="utf-8")
