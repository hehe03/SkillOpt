from __future__ import annotations

import datetime
import os
import re
from collections.abc import Sequence
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPTS_ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, OPTS_ROOT, TRAIN_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def configure_windows_utf8_stdio() -> None:
    """Keep Chinese console output readable on Windows when possible."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _patch_openai_chat_to_agent_harness() -> None:
    """Route optimizer-side OpenAI chat calls through the current Agent harness."""
    enabled = os.environ.get(
        "SHORTAGE_ANALYZE_USE_AGENT_OPTIMIZER",
        os.environ.get("SHORTAGE_ANALYZE_USE_CODEX_OPTIMIZER", "1"),
    )
    if enabled.lower() in {"0", "false", "no"}:
        return

    optimizer_cwd = TRAIN_ROOT / "optimizer_workspace"
    optimizer_cwd.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CODEX_WORKING_DIRECTORY", str(optimizer_cwd))
    os.environ.setdefault("CODEX_SANDBOX_MODE", "read-only")

    from skillopt.model import azure_openai as openai_impl
    from skillopt.model import codex_backend
    from shortage_analyze_skillopt.harness_chat import describe_agent_backend, run_agent_chat

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
        return run_agent_chat(
            build_prompt(system, user),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
            stage="optimizer",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_target(*, system, user, max_completion_tokens=16384, retries=5, stage="target", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_agent_chat(
            build_prompt(system, user),
            model=codex_backend.TARGET_DEPLOYMENT,
            timeout=timeout,
            stage="target",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_with_deployment(deployment, system, user, max_completion_tokens=16384, retries=5, stage="custom", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_agent_chat(
            build_prompt(system, user),
            model=deployment,
            timeout=timeout,
            stage="custom",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_optimizer_messages(messages, max_completion_tokens=16384, retries=5, stage="optimizer", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_agent_chat(
            build_prompt_from_messages(messages),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
            stage="optimizer",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        )
        if return_message:
            from skillopt.model.common import CompatAssistantMessage
            return CompatAssistantMessage(content=text, tool_calls=[]), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_target_messages(messages, max_completion_tokens=16384, retries=5, stage="target", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_agent_chat(
            build_prompt_from_messages(messages),
            model=codex_backend.TARGET_DEPLOYMENT,
            timeout=timeout,
            stage="target",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        )
        if return_message:
            from skillopt.model.common import CompatAssistantMessage
            return CompatAssistantMessage(content=text, tool_calls=[]), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_messages_with_deployment(deployment, messages, max_completion_tokens=16384, retries=5, stage="custom", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_agent_chat(
            build_prompt_from_messages(messages),
            model=deployment,
            timeout=timeout,
            stage="custom",
            cwd=os.environ["CODEX_WORKING_DIRECTORY"],
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
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
        "  [shortage_analyze] optimizer openai_chat calls are routed to Agent harness "
        f"({describe_agent_backend()}, cwd={os.environ['CODEX_WORKING_DIRECTORY']})"
    )


def _patch_agent_harness_config_aliases() -> None:
    """Let this task's readable agent_harness config map to SkillOpt internals."""
    import scripts.train as train_module
    import skillopt.model.common as common

    original_normalize = train_module.normalize_backend_name
    original_default_model = train_module.default_model_for_backend
    original_common_normalize = common.normalize_backend_name
    original_common_default_model = common.default_model_for_backend

    def normalize_backend_name(name: str | None) -> str:
        normalized = str(name or "").strip().lower()
        if normalized in {"agent_harness", "harness", "agent"}:
            return "agent_harness"
        return original_normalize(name)

    def default_model_for_backend(backend: str | None) -> str:
        normalized = str(backend or "").strip().lower()
        if normalized in {"agent_harness", "harness", "agent"}:
            return "harness-default"
        return original_default_model(backend)

    def common_normalize_backend_name(name: str | None) -> str:
        normalized = str(name or "").strip().lower()
        if normalized in {"agent_harness", "harness", "agent"}:
            return "agent_harness"
        return original_common_normalize(name)

    def common_default_model_for_backend(backend: str | None) -> str:
        normalized = str(backend or "").strip().lower()
        if normalized in {"agent_harness", "harness", "agent"}:
            return "harness-default"
        return original_common_default_model(backend)

    train_module.normalize_backend_name = normalize_backend_name
    train_module.default_model_for_backend = default_model_for_backend
    common.normalize_backend_name = common_normalize_backend_name
    common.default_model_for_backend = common_default_model_for_backend


def _patch_agent_harness_flat_config() -> None:
    """Convert agent_harness fields after config loading but before Trainer sees them."""
    import scripts.train as train_module

    original_load_config = train_module.load_config

    def has_explicit_out_root(args) -> bool:
        if getattr(args, "out_root", None):
            return True
        for option in getattr(args, "cfg_options", None) or []:
            key = str(option).split("=", 1)[0].strip()
            if key in {"env.out_root", "out_root"}:
                return True
        return False

    def slug(value: str) -> str:
        text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value or "").strip())
        return text.strip("._-") or "skill"

    def configure_shortage_output_root(cfg: dict, args) -> None:
        skill_name = slug(str(cfg.get("env") or "shortage_analyze"))
        if not has_explicit_out_root(args):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            cfg["out_root"] = str((TRAIN_ROOT / "outputs" / f"{skill_name}_{timestamp}").resolve())
        else:
            cfg["out_root"] = str(Path(str(cfg["out_root"])).resolve())

        llm_files_dir = Path(cfg["out_root"]) / "llm-files"
        llm_files_dir.mkdir(parents=True, exist_ok=True)
        os.environ["SHORTAGE_ANALYZE_OUT_ROOT"] = str(Path(cfg["out_root"]))
        os.environ["SHORTAGE_ANALYZE_LLM_FILES_DIR"] = str(llm_files_dir)
        os.environ.setdefault("SHORTAGE_ANALYZE_OPENCODE_RUN_DIR", str(PROJECT_ROOT))

    def load_config_with_agent_harness(args):
        cfg = original_load_config(args)
        for key in ("model_backend", "optimizer_backend", "target_backend"):
            if str(cfg.get(key) or "").strip().lower() in {"agent_harness", "harness", "agent"}:
                cfg[key] = "openai_chat"
        for key in ("optimizer_model", "target_model"):
            if str(cfg.get(key) or "").strip().lower() in {"", "harness-default", "agent_harness"}:
                cfg[key] = "harness-default"
        if str(cfg.get("script_codegen_model") or "").strip().lower() in {"", "harness-default", "agent_harness"}:
            cfg["script_codegen_model"] = "harness-default"
        configure_shortage_output_root(cfg, args)
        return cfg

    train_module.load_config = load_config_with_agent_harness


def main(argv: Sequence[str] | None = None) -> None:
    configure_windows_utf8_stdio()
    original_argv = sys.argv[:]
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        _patch_openai_chat_to_agent_harness()

        import scripts.train as train_module
        from shortage_analyze_skillopt.adapter import ShortageAnalyzeAdapter

        _patch_agent_harness_config_aliases()
        _patch_agent_harness_flat_config()

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
