from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPTS_ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, OPTS_ROOT, TRAIN_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


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


def _argv_has_codex_exec_path() -> bool:
    for arg in sys.argv[1:]:
        if arg == "--codex_exec_path":
            return True
        if arg.startswith("model.codex_exec_path="):
            return True
        if arg.startswith("env.codex_exec_path="):
            return True
    return False


def _patch_openai_chat_to_codex_cli() -> None:
    """Route optimizer-side OpenAI chat calls through the local Codex CLI backend."""
    if os.environ.get("SHORTAGE_ANALYZE_USE_CODEX_OPTIMIZER", "1").lower() in {"0", "false", "no"}:
        return

    optimizer_cwd = TRAIN_ROOT / "optimizer_workspace"
    optimizer_cwd.mkdir(parents=True, exist_ok=True)
    codex_cli = _resolve_codex_cli()
    os.environ.setdefault("CODEX_CLI_BIN", codex_cli)
    os.environ.setdefault("CODEX_WORKING_DIRECTORY", str(optimizer_cwd))
    os.environ.setdefault("CODEX_SANDBOX_MODE", "read-only")

    if not _argv_has_codex_exec_path() and codex_cli != "codex":
        sys.argv.extend(["--codex_exec_path", codex_cli])

    from skillopt.model import azure_openai as openai_impl
    from skillopt.model import codex_backend

    def run_codex_chat(prompt: str, *, model: str, timeout: int | None = None) -> str:
        with tempfile.TemporaryDirectory(prefix="shortage_codex_chat_") as temp_dir:
            output_path = Path(temp_dir) / "last_message.txt"
            command = [
                os.environ["CODEX_CLI_BIN"],
                "exec",
                "--ephemeral",
                "-c",
                "approval_policy=\"never\"",
                "--sandbox",
                os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
                "--skip-git-repo-check",
                "--cd",
                os.environ["CODEX_WORKING_DIRECTORY"],
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
            )
            last_message = ""
            if output_path.exists():
                last_message = output_path.read_text(encoding="utf-8").strip()
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                raise RuntimeError(detail[:4000] or f"codex exec failed with exit code {proc.returncode}")
            if not last_message:
                last_message = (proc.stdout or "").strip()
            if not last_message:
                raise RuntimeError("Codex returned an empty final message")
            return last_message

    def build_prompt(system: str, user: str) -> str:
        return (
            "System instructions:\n"
            f"{system.strip()}\n\n"
            "User request:\n"
            f"{user.strip()}\n\n"
            "Answer the user request directly. Preserve any required output format exactly."
        )

    def build_prompt_from_messages(messages) -> str:
        parts: list[str] = []
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", ""))
            parts.append(f"{role}:\n{content}")
        parts.append("Answer the latest user request directly. Preserve any required output format exactly.")
        return "\n\n".join(parts)

    def chat_optimizer(*, system, user, max_completion_tokens=16384, retries=5, stage="optimizer", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_codex_chat(
            build_prompt(system, user),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_target(*, system, user, max_completion_tokens=16384, retries=5, stage="target", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_codex_chat(
            build_prompt(system, user),
            model=codex_backend.TARGET_DEPLOYMENT,
            timeout=timeout,
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_with_deployment(deployment, system, user, max_completion_tokens=16384, retries=5, stage="custom", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_codex_chat(
            build_prompt(system, user),
            model=deployment,
            timeout=timeout,
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_optimizer_messages(messages, max_completion_tokens=16384, retries=5, stage="optimizer", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_codex_chat(
            build_prompt_from_messages(messages),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
        )
        if return_message:
            from skillopt.model.common import CompatAssistantMessage
            return CompatAssistantMessage(content=text, tool_calls=[]), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_target_messages(messages, max_completion_tokens=16384, retries=5, stage="target", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_codex_chat(
            build_prompt_from_messages(messages),
            model=codex_backend.TARGET_DEPLOYMENT,
            timeout=timeout,
        )
        if return_message:
            from skillopt.model.common import CompatAssistantMessage
            return CompatAssistantMessage(content=text, tool_calls=[]), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_messages_with_deployment(deployment, messages, max_completion_tokens=16384, retries=5, stage="custom", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_codex_chat(
            build_prompt_from_messages(messages),
            model=deployment,
            timeout=timeout,
        )
        if return_message:
            from skillopt.model.common import CompatAssistantMessage
            return CompatAssistantMessage(content=text, tool_calls=[]), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    openai_impl.chat_optimizer = chat_optimizer
    openai_impl.chat_optimizer_messages = chat_optimizer_messages
    openai_impl.chat_target = chat_target
    openai_impl.chat_target_messages = chat_target_messages
    openai_impl.chat_with_deployment = chat_with_deployment
    openai_impl.chat_messages_with_deployment = chat_messages_with_deployment
    openai_impl.set_target_deployment = codex_backend.set_target_deployment
    openai_impl.set_optimizer_deployment = codex_backend.set_optimizer_deployment
    openai_impl.set_reasoning_effort = codex_backend.set_reasoning_effort
    openai_impl.get_token_summary = codex_backend.get_token_summary
    openai_impl.reset_token_tracker = codex_backend.reset_token_tracker
    print(
        "  [shortage_analyze] optimizer openai_chat calls are routed to Codex CLI "
        f"(bin={os.environ['CODEX_CLI_BIN']}, cwd={os.environ['CODEX_WORKING_DIRECTORY']})"
    )


def main(argv: Sequence[str] | None = None) -> None:
    original_argv = sys.argv[:]
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        _patch_openai_chat_to_codex_cli()

        import scripts.train as train_module
        from shortage_analyze_skillopt.adapter import ShortageAnalyzeAdapter

        original_register_builtins = train_module._register_builtins

        def register_with_shortage() -> None:
            original_register_builtins()
            train_module._ENV_REGISTRY["shortage_analyze"] = ShortageAnalyzeAdapter

        train_module._register_builtins = register_with_shortage
        train_module._ENV_REGISTRY["shortage_analyze"] = ShortageAnalyzeAdapter
        train_module.main()
    finally:
        if argv is not None:
            sys.argv = original_argv


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--config",
        "shortage_analyze-opt/train/configs/default.yaml",
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
