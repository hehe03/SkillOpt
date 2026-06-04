from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


_LLM_FILE_LOCK = threading.Lock()
_LLM_FILE_STEP = 0


def _resolve_codex_cli() -> str | None:
    configured = os.environ.get("CODEX_CLI_BIN") or os.environ.get("CODEX_EXEC_PATH")
    if configured:
        return configured if Path(configured).exists() or shutil.which(configured) else None

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidate = Path(local_appdata) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("codex")


def _resolve_nga_cli() -> str | None:
    configured = os.environ.get("NGA_CLI_BIN") or os.environ.get("NGA_EXEC_PATH")
    if configured:
        return configured if Path(configured).exists() or shutil.which(configured) else None

    ochome = os.environ.get("OCHOME")
    if ochome:
        for name in ("nga.cmd", "nga.exe", "nga"):
            candidate = Path(ochome) / name
            if candidate.exists():
                return str(candidate)

    user_ochome = Path.home() / "OCHOME"
    for name in ("nga.cmd", "nga.exe", "nga"):
        candidate = user_ochome / name
        if candidate.exists():
            return str(candidate)

    for name in ("nga.cmd", "nga.exe", "nga"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _resolve_opencode_cli() -> str | None:
    configured = os.environ.get("OPENCODE_CLI_BIN") or os.environ.get("OPENCODE_EXEC_PATH")
    if configured:
        return configured if Path(configured).exists() or shutil.which(configured) else None
    for name in ("opencode.cmd", "opencode.exe", "opencode"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _requested_backend() -> str:
    return os.environ.get("SHORTAGE_ANALYZE_AGENT_BACKEND", "auto").strip().lower() or "auto"


def _format_command_arg(value: str, variables: dict[str, str]) -> str:
    try:
        return value.format(**variables)
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in SHORTAGE_ANALYZE_AGENT_COMMAND: {exc}") from exc


def _safe_stage_name(stage: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(stage or "llm")).strip("._-")
    return safe or "llm"


def _next_llm_file_paths(stage: str, *, cwd: str | os.PathLike[str] | None) -> tuple[Path, Path, int]:
    global _LLM_FILE_STEP
    configured = os.environ.get("SHORTAGE_ANALYZE_LLM_FILES_DIR", "").strip()
    if configured:
        llm_dir = Path(configured)
        if not llm_dir.is_absolute():
            llm_dir = Path(cwd or os.getcwd()) / llm_dir
    else:
        llm_dir = Path(cwd or os.getcwd()) / "llm-files"
    llm_dir = llm_dir.resolve()
    llm_dir.mkdir(parents=True, exist_ok=True)

    stage_name = _safe_stage_name(stage)
    with _LLM_FILE_LOCK:
        while True:
            _LLM_FILE_STEP += 1
            step = _LLM_FILE_STEP
            suffix = f"{stage_name}_step_{step:04d}"
            prompt_path = llm_dir / f"prompt_{suffix}.md"
            response_path = llm_dir / f"response_{suffix}.txt"
            if not prompt_path.exists() and not response_path.exists():
                return prompt_path, response_path, step


def _run_custom_agent_command(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    stage: str,
    cwd: str | os.PathLike[str] | None,
) -> str:
    command_json = os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip()
    command_shell = os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND", "").strip()
    if not command_json and not command_shell:
        raise ValueError("No custom harness command configured")

    prompt_path, output_path, _step = _next_llm_file_paths(stage, cwd=cwd)
    prompt_path.write_text(prompt, encoding="utf-8")
    configured_text = command_json or command_shell
    allow_stdin = os.environ.get("SHORTAGE_ANALYZE_AGENT_USE_STDIN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if "{prompt_file}" not in configured_text and not allow_stdin:
        raise ValueError(
            "自定义 harness 默认使用文件协议，请在命令中加入 {prompt_file}。"
            "如果确实要使用 stdin，请设置 SHORTAGE_ANALYZE_AGENT_USE_STDIN=1。"
        )
    variables = {
        "prompt_file": str(prompt_path),
        "output_file": str(output_path),
        "model": model,
        "stage": stage,
        "cwd": str(cwd or os.getcwd()),
    }

    if command_json:
        raw_command = json.loads(command_json)
        if not isinstance(raw_command, list) or not all(isinstance(arg, str) for arg in raw_command):
            raise ValueError("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON must be a JSON string array")
        command = [_format_command_arg(arg, variables) for arg in raw_command]
        stdin_prompt = prompt if allow_stdin and "{prompt_file}" not in command_json else None
        proc = subprocess.run(
            command,
            input=stdin_prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=str(cwd) if cwd else None,
            encoding="utf-8",
            errors="replace",
        )
    else:
        command_text = _format_command_arg(command_shell, variables)
        stdin_prompt = prompt if allow_stdin and "{prompt_file}" not in command_shell else None
        proc = subprocess.run(
            command_text,
            input=stdin_prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=str(cwd) if cwd else None,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )

    response = output_path.read_text(encoding="utf-8-sig").strip() if output_path.exists() else ""
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail and not output_path.exists():
            output_path.write_text(detail, encoding="utf-8")
        raise RuntimeError(detail[:4000] or f"custom harness command failed with exit code {proc.returncode}")
    response = response or (proc.stdout or "").strip()
    if not response:
        raise RuntimeError("custom harness command returned an empty response")
    if not output_path.exists():
        output_path.write_text(response, encoding="utf-8")
    return response


def _run_codex_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    cwd: str | os.PathLike[str] | None,
    sandbox: str = "read-only",
) -> str:
    codex_bin = _resolve_codex_cli()
    if not codex_bin:
        raise RuntimeError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND=codex，但未找到 Codex CLI。"
            "请设置 CODEX_CLI_BIN，或改用 SHORTAGE_ANALYZE_AGENT_BACKEND=nga/opencode，"
            "或配置 SHORTAGE_ANALYZE_AGENT_COMMAND_JSON。"
        )
    with tempfile.TemporaryDirectory(prefix="shortage_codex_chat_") as temp_dir:
        output_path = Path(temp_dir) / "last_message.txt"
        command = [
            codex_bin,
            "exec",
            "--ephemeral",
            "-c",
            'approval_policy="never"',
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
            "--cd",
            str(cwd or os.getcwd()),
            "--model",
            model,
            "--output-last-message",
            str(output_path),
            "-",
        ]
        proc = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        response = output_path.read_text(encoding="utf-8-sig").strip() if output_path.exists() else ""
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail[:4000] or f"codex exec failed with exit code {proc.returncode}")
        response = response or (proc.stdout or "").strip()
        if not response:
            raise RuntimeError("Codex returned an empty final message")
        return response


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def _run_nga_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    cwd: str | os.PathLike[str] | None,
    stage: str,
) -> str:
    del model
    nga_bin = _resolve_nga_cli()
    if not nga_bin:
        raise RuntimeError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND=nga，但未找到 Nga CLI。"
            "请确认 nga 在 PATH 或 ~/OCHOME 中，或设置 NGA_CLI_BIN。"
        )

    run_dir = Path(os.environ.get("SHORTAGE_ANALYZE_NGA_RUN_DIR") or cwd or os.getcwd()).resolve()
    prompt_path, output_path, _step = _next_llm_file_paths("nga_" + _safe_stage_name(stage), cwd=run_dir)
    prompt_path.write_text(prompt, encoding="utf-8")
    instruction = os.environ.get(
        "SHORTAGE_ANALYZE_NGA_INSTRUCTION",
        "Read the attached file and answer the question directly. "
        "Preserve the requested output format exactly and do not add commentary.",
    ).strip()
    command = [
        nga_bin,
        "run",
        instruction,
        "--file",
        str(prompt_path),
    ]
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=str(run_dir),
        encoding="utf-8",
        errors="replace",
    )
    response = _strip_ansi((proc.stdout or "").strip())
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        output_path.write_text(detail, encoding="utf-8")
        raise RuntimeError(detail[:4000] or f"nga run failed with exit code {proc.returncode}")
    if not response:
        detail = (proc.stderr or "").strip()
        output_path.write_text(detail, encoding="utf-8")
        raise RuntimeError(detail[:4000] or "Nga returned an empty response")
    output_path.write_text(response, encoding="utf-8")
    return response


def _opencode_model_args(model: str) -> list[str]:
    configured = os.environ.get("SHORTAGE_ANALYZE_OPENCODE_MODEL") or os.environ.get("OPENCODE_MODEL")
    selected = (configured or "").strip()
    if not selected and "/" in str(model):
        selected = str(model).strip()
    return ["--model", selected] if selected else []


def _run_opencode_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    cwd: str | os.PathLike[str] | None,
    stage: str,
) -> str:
    opencode_bin = _resolve_opencode_cli()
    if not opencode_bin:
        raise RuntimeError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND=opencode，但未找到 opencode CLI。"
            "请确认 opencode 在 PATH 中，或设置 OPENCODE_CLI_BIN。"
        )

    run_dir = Path(os.environ.get("SHORTAGE_ANALYZE_OPENCODE_RUN_DIR") or cwd or os.getcwd()).resolve()
    prompt_path, output_path, _step = _next_llm_file_paths("opencode_" + _safe_stage_name(stage), cwd=run_dir)
    prompt_path.write_text(prompt, encoding="utf-8")
    try:
        file_arg = prompt_path.relative_to(run_dir).as_posix()
    except ValueError:
        file_arg = str(prompt_path)
    cli_prompt_path = (run_dir / file_arg).resolve() if not Path(file_arg).is_absolute() else Path(file_arg)
    if cli_prompt_path != prompt_path.resolve() or not cli_prompt_path.is_file():
        raise FileNotFoundError(
            "opencode --file 路径与生成的 prompt 文件不匹配："
            f" run_dir={run_dir}, file_arg={file_arg}, resolved={cli_prompt_path}, prompt={prompt_path}"
        )
    instruction = (
        f"Read the attached file {file_arg!r} and answer it directly. "
        "Preserve the requested output format exactly and do not add commentary."
    )
    command = [
        opencode_bin,
        "run",
        instruction,
        "--dir",
        str(run_dir),
        f"--file={file_arg}",
        *_opencode_model_args(model),
    ]
    agent = os.environ.get("SHORTAGE_ANALYZE_OPENCODE_AGENT", "").strip()
    if agent:
        command.extend(["--agent", agent])
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=str(run_dir),
        encoding="utf-8",
        errors="replace",
    )
    response = _strip_ansi((proc.stdout or "").strip())
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        output_path.write_text(detail, encoding="utf-8")
        raise RuntimeError(detail[:4000] or f"opencode run failed with exit code {proc.returncode}")
    if not response:
        raise RuntimeError("opencode returned an empty response")
    output_path.write_text(response, encoding="utf-8")
    return response


def run_agent_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None = None,
    stage: str = "optimizer",
    cwd: str | os.PathLike[str] | None = None,
    sandbox: str = "read-only",
) -> str:
    """Call the current Agent harness model.

    Backend resolution order:
    1. SHORTAGE_ANALYZE_AGENT_COMMAND_JSON / SHORTAGE_ANALYZE_AGENT_COMMAND
    2. SHORTAGE_ANALYZE_AGENT_BACKEND when set to nga, opencode, or codex
    3. auto-detect Nga CLI
    4. auto-detect opencode CLI
    5. auto-detect Codex CLI
    """
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip() or os.environ.get(
        "SHORTAGE_ANALYZE_AGENT_COMMAND", ""
    ).strip():
        return _run_custom_agent_command(prompt, model=model, timeout=timeout, stage=stage, cwd=cwd)
    backend = _requested_backend()
    if backend == "nga":
        return _run_nga_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if backend == "opencode":
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if backend == "codex":
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    if backend not in {"auto", ""}:
        raise ValueError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND 只支持 auto、nga、opencode、codex；"
            "其它 harness 请配置 SHORTAGE_ANALYZE_AGENT_COMMAND_JSON。"
        )
    if _resolve_nga_cli():
        return _run_nga_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if _resolve_opencode_cli():
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if _resolve_codex_cli():
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    raise RuntimeError(
        "没有找到可自动调用的 Agent harness。请安装/配置 Nga、opencode 或 Codex CLI，"
        "或设置 SHORTAGE_ANALYZE_AGENT_COMMAND_JSON / SHORTAGE_ANALYZE_AGENT_COMMAND。"
    )


def describe_agent_backend() -> str:
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND_JSON"
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND"
    backend = _requested_backend()
    if backend == "nga" or (backend == "auto" and _resolve_nga_cli()):
        return f"Nga CLI ({_resolve_nga_cli()})"
    if backend == "opencode" or (backend == "auto" and _resolve_opencode_cli()):
        return f"opencode CLI ({_resolve_opencode_cli()})"
    if backend == "codex" or (backend == "auto" and _resolve_codex_cli()):
        return f"Codex CLI ({_resolve_codex_cli()})"
    return "unconfigured Agent harness"
