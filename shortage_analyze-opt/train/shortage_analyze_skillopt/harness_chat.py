from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


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

    with tempfile.TemporaryDirectory(prefix=f"shortage_agent_{stage}_") as temp_dir:
        temp_path = Path(temp_dir)
        prompt_path = temp_path / "prompt.md"
        output_path = temp_path / "response.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
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
            proc = subprocess.run(
                command,
                input=prompt,
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
            proc = subprocess.run(
                command_text,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                cwd=str(cwd) if cwd else None,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

        response = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail[:4000] or f"custom harness command failed with exit code {proc.returncode}")
        response = response or (proc.stdout or "").strip()
        if not response:
            raise RuntimeError("custom harness command returned an empty response")
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
            "请设置 CODEX_CLI_BIN，或改用 SHORTAGE_ANALYZE_AGENT_BACKEND=opencode，"
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
        response = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail[:4000] or f"codex exec failed with exit code {proc.returncode}")
        response = response or (proc.stdout or "").strip()
        if not response:
            raise RuntimeError("Codex returned an empty final message")
        return response


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


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
) -> str:
    opencode_bin = _resolve_opencode_cli()
    if not opencode_bin:
        raise RuntimeError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND=opencode，但未找到 opencode CLI。"
            "请确认 opencode 在 PATH 中，或设置 OPENCODE_CLI_BIN。"
        )

    with tempfile.TemporaryDirectory(prefix="shortage_opencode_chat_") as temp_dir:
        prompt_path = Path(temp_dir) / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        command = [
            opencode_bin,
            "run",
            "--dir",
            str(cwd or os.getcwd()),
            "--file",
            str(prompt_path),
            *_opencode_model_args(model),
        ]
        agent = os.environ.get("SHORTAGE_ANALYZE_OPENCODE_AGENT", "").strip()
        if agent:
            command.extend(["--agent", agent])
        command.append(
            "Read the attached prompt.md and answer it directly. "
            "Preserve the requested output format exactly and do not add commentary."
        )
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=str(cwd) if cwd else None,
            encoding="utf-8",
            errors="replace",
        )
        response = _strip_ansi((proc.stdout or "").strip())
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail[:4000] or f"opencode run failed with exit code {proc.returncode}")
        if not response:
            raise RuntimeError("opencode returned an empty response")
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
    2. SHORTAGE_ANALYZE_AGENT_BACKEND when set to opencode or codex
    3. auto-detect opencode CLI
    4. auto-detect Codex CLI
    """
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip() or os.environ.get(
        "SHORTAGE_ANALYZE_AGENT_COMMAND", ""
    ).strip():
        return _run_custom_agent_command(prompt, model=model, timeout=timeout, stage=stage, cwd=cwd)
    backend = _requested_backend()
    if backend == "opencode":
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd)
    if backend == "codex":
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    if backend not in {"auto", ""}:
        raise ValueError(
            "SHORTAGE_ANALYZE_AGENT_BACKEND 只支持 auto、opencode、codex；"
            "其它 harness 请配置 SHORTAGE_ANALYZE_AGENT_COMMAND_JSON。"
        )
    if _resolve_opencode_cli():
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd)
    if _resolve_codex_cli():
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    raise RuntimeError(
        "没有找到可自动调用的 Agent harness。请安装/配置 opencode 或 Codex CLI，"
        "或设置 SHORTAGE_ANALYZE_AGENT_COMMAND_JSON / SHORTAGE_ANALYZE_AGENT_COMMAND。"
    )


def describe_agent_backend() -> str:
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND_JSON"
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND"
    backend = _requested_backend()
    if backend == "opencode" or (backend == "auto" and _resolve_opencode_cli()):
        return f"opencode CLI ({_resolve_opencode_cli()})"
    if backend == "codex" or (backend == "auto" and _resolve_codex_cli()):
        return f"Codex CLI ({_resolve_codex_cli()})"
    return "unconfigured Agent harness"
