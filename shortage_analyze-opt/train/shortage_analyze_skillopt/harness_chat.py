from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _resolve_codex_cli() -> str:
    configured = os.environ.get("CODEX_CLI_BIN") or os.environ.get("CODEX_EXEC_PATH")
    if configured:
        return configured

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidate = Path(local_appdata) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if candidate.exists():
            return str(candidate)
    return "codex"


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


def run_agent_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None = None,
    stage: str = "optimizer",
    cwd: str | os.PathLike[str] | None = None,
    sandbox: str = "read-only",
) -> str:
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip() or os.environ.get(
        "SHORTAGE_ANALYZE_AGENT_COMMAND", ""
    ).strip():
        return _run_custom_agent_command(prompt, model=model, timeout=timeout, stage=stage, cwd=cwd)
    return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)


def describe_agent_backend() -> str:
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND_JSON", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND_JSON"
    if os.environ.get("SHORTAGE_ANALYZE_AGENT_COMMAND", "").strip():
        return "custom harness command from SHORTAGE_ANALYZE_AGENT_COMMAND"
    return f"Codex CLI ({_resolve_codex_cli()})"
