from __future__ import annotations

import datetime
import importlib.util
import os
import re
from collections.abc import Sequence
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, OPT_ROOT, TRAIN_ROOT):
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


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value or "").strip())
    return text.strip("._-") or "skill"


def _resolve_path(value: str | os.PathLike[str], *, base: Path = PROJECT_ROOT) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _workspace_from_config_path(args, cfg: dict) -> Path:
    configured = str(cfg.get("workspace_root") or cfg.get("skill_workspace") or "").strip()
    if configured:
        return _resolve_path(configured)

    config_path = _resolve_path(str(args.config))
    if config_path.parent.name == "configs":
        return config_path.parent.parent.resolve()

    return (OPT_ROOT / "workspace" / _slug(str(cfg.get("env") or "skill"))).resolve()


def _load_adapter_class(cfg: dict, workspace_root: Path):
    adapter_class_name = str(cfg.get("adapter_class") or "Adapter").strip()
    adapter_module = str(cfg.get("adapter_module") or cfg.get("adapter_path") or "").strip()
    if adapter_module:
        module_path = _resolve_path(adapter_module)
    else:
        module_path = workspace_root / "train" / "adapter.py"

    if not module_path.exists():
        raise FileNotFoundError(
            "未找到 workspace adapter。请在配置 env.adapter_module 指定 adapter.py，"
            f"或创建默认文件：{module_path}"
        )

    module_dir = str(module_path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    module_name = f"opt_in_harness_adapter_{_slug(str(cfg.get('env') or module_path.parent.name))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 adapter 模块：{module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    adapter_class = getattr(module, adapter_class_name, None)
    if adapter_class is None:
        raise AttributeError(f"{module_path} 中没有 {adapter_class_name}")
    return adapter_class


def _patch_openai_chat_to_agent_harness() -> None:
    """Route optimizer-side OpenAI chat calls through the current Agent harness."""
    enabled = _env_first(
        "OPT_IN_HARNESS_USE_AGENT_OPTIMIZER",
        default="1",
    )
    if enabled.lower() in {"0", "false", "no"}:
        return

    os.environ.setdefault("CODEX_SANDBOX_MODE", "read-only")

    from skillopt.model import azure_openai as openai_impl
    from skillopt.model import codex_backend
    from harness_chat import run_agent_chat

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

    def harness_cwd() -> str:
        cwd = os.environ.get("OPT_IN_HARNESS_OPTIMIZER_CWD") or os.environ.get("CODEX_WORKING_DIRECTORY")
        return cwd or str(PROJECT_ROOT)

    def chat_optimizer(*, system, user, max_completion_tokens=16384, retries=5, stage="optimizer", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_agent_chat(
            build_prompt(system, user),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
            stage="optimizer",
            cwd=harness_cwd(),
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_target(*, system, user, max_completion_tokens=16384, retries=5, stage="target", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_agent_chat(
            build_prompt(system, user),
            model=codex_backend.TARGET_DEPLOYMENT,
            timeout=timeout,
            stage="target",
            cwd=harness_cwd(),
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_with_deployment(deployment, system, user, max_completion_tokens=16384, retries=5, stage="custom", timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage
        return run_agent_chat(
            build_prompt(system, user),
            model=deployment,
            timeout=timeout,
            stage="custom",
            cwd=harness_cwd(),
            sandbox=os.environ.get("CODEX_SANDBOX_MODE", "read-only"),
        ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def chat_optimizer_messages(messages, max_completion_tokens=16384, retries=5, stage="optimizer", tools=None, tool_choice=None, return_message=False, timeout=None, **_kwargs):
        del max_completion_tokens, retries, stage, tools, tool_choice
        text = run_agent_chat(
            build_prompt_from_messages(messages),
            model=codex_backend.OPTIMIZER_DEPLOYMENT,
            timeout=timeout,
            stage="optimizer",
            cwd=harness_cwd(),
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
            cwd=harness_cwd(),
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
            cwd=harness_cwd(),
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


def _patch_agent_harness_config_aliases() -> None:
    """Let readable agent_harness config map to SkillOpt internals."""
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
    state: dict[str, object] = {}

    def has_explicit_out_root(args) -> bool:
        if getattr(args, "out_root", None):
            return True
        for option in getattr(args, "cfg_options", None) or []:
            key = str(option).split("=", 1)[0].strip()
            if key in {"env.out_root", "out_root"}:
                return True
        return False

    def configure_output_root(cfg: dict, args) -> None:
        workspace_root = _workspace_from_config_path(args, cfg)
        cfg["workspace_root"] = str(workspace_root)
        skill_name = _slug(str(cfg.get("env") or workspace_root.name))
        if not has_explicit_out_root(args):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            cfg["out_root"] = str((workspace_root / "outputs" / f"{skill_name}_{timestamp}").resolve())
        else:
            cfg["out_root"] = str(_resolve_path(str(cfg["out_root"])))

        llm_files_dir = Path(cfg["out_root"]) / "llm-files"
        optimizer_cwd = workspace_root / "outputs" / "_optimizer_workspace"
        llm_files_dir.mkdir(parents=True, exist_ok=True)
        optimizer_cwd.mkdir(parents=True, exist_ok=True)

        os.environ["OPT_IN_HARNESS_WORKSPACE_ROOT"] = str(workspace_root)
        os.environ["OPT_IN_HARNESS_OUT_ROOT"] = str(Path(cfg["out_root"]))
        os.environ["OPT_IN_HARNESS_LLM_FILES_DIR"] = str(llm_files_dir)
        os.environ["OPT_IN_HARNESS_OPTIMIZER_CWD"] = str(optimizer_cwd)
        os.environ.setdefault("CODEX_WORKING_DIRECTORY", str(optimizer_cwd))
        os.environ.setdefault("OPT_IN_HARNESS_NGA_RUN_DIR", str(PROJECT_ROOT))
        os.environ.setdefault("OPT_IN_HARNESS_OPENCODE_RUN_DIR", str(PROJECT_ROOT))

    def configure_agent_harness_from_config(cfg: dict) -> None:
        agent_backend = str(cfg.get("agent_backend") or "").strip()
        agent_command_json = str(cfg.get("agent_command_json") or "").strip()
        agent_command = str(cfg.get("agent_command") or "").strip()

        if agent_backend:
            os.environ["OPT_IN_HARNESS_AGENT_BACKEND"] = agent_backend
            if not agent_command_json:
                os.environ.pop("OPT_IN_HARNESS_AGENT_COMMAND_JSON", None)
            if not agent_command:
                os.environ.pop("OPT_IN_HARNESS_AGENT_COMMAND", None)
        if agent_command_json:
            os.environ["OPT_IN_HARNESS_AGENT_COMMAND_JSON"] = agent_command_json
        if agent_command:
            os.environ["OPT_IN_HARNESS_AGENT_COMMAND"] = agent_command

        env_mappings = {
            "agent_use_stdin": "OPT_IN_HARNESS_AGENT_USE_STDIN",
            "hide_subprocess_window": "OPT_IN_HARNESS_HIDE_SUBPROCESS_WINDOW",
            "stream_subprocess_output": "OPT_IN_HARNESS_STREAM_SUBPROCESS_OUTPUT",
            "nga_cli_bin": "NGA_CLI_BIN",
            "nga_exec_path": "NGA_EXEC_PATH",
            "nga_instruction": "OPT_IN_HARNESS_NGA_INSTRUCTION",
            "nga_run_dir": "OPT_IN_HARNESS_NGA_RUN_DIR",
            "opencode_cli_bin": "OPENCODE_CLI_BIN",
            "opencode_exec_path": "OPENCODE_EXEC_PATH",
            "opencode_instruction": "OPT_IN_HARNESS_OPENCODE_INSTRUCTION",
            "opencode_run_dir": "OPT_IN_HARNESS_OPENCODE_RUN_DIR",
            "opencode_model": "OPT_IN_HARNESS_OPENCODE_MODEL",
            "opencode_agent": "OPT_IN_HARNESS_OPENCODE_AGENT",
            "codex_cli_bin": "CODEX_CLI_BIN",
            "codex_exec_path": "CODEX_EXEC_PATH",
        }
        for cfg_key, env_key in env_mappings.items():
            value = cfg.get(cfg_key)
            if value is not None and str(value).strip():
                os.environ[env_key] = str(value)

    def load_config_with_agent_harness(args):
        cfg = original_load_config(args)
        configure_agent_harness_from_config(cfg)
        for key in ("model_backend", "optimizer_backend", "target_backend"):
            if str(cfg.get(key) or "").strip().lower() in {"agent_harness", "harness", "agent"}:
                cfg[key] = "openai_chat"
        for key in ("optimizer_model", "target_model"):
            if str(cfg.get(key) or "").strip().lower() in {"", "harness-default", "agent_harness"}:
                cfg[key] = "harness-default"
        if str(cfg.get("script_codegen_model") or "").strip().lower() in {"", "harness-default", "agent_harness"}:
            cfg["script_codegen_model"] = "harness-default"
        configure_output_root(cfg, args)
        state["cfg"] = cfg
        state["workspace_root"] = Path(str(cfg["workspace_root"]))
        state["adapter_class"] = _load_adapter_class(cfg, Path(str(cfg["workspace_root"])))
        return cfg

    train_module.load_config = load_config_with_agent_harness
    train_module._opt_in_harness_state = state


def main(argv: Sequence[str] | None = None) -> None:
    configure_windows_utf8_stdio()
    original_argv = sys.argv[:]
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        _patch_openai_chat_to_agent_harness()

        import scripts.train as train_module

        _patch_agent_harness_config_aliases()
        _patch_agent_harness_flat_config()

        original_register_builtins = train_module._register_builtins

        def register_with_workspace_adapter() -> None:
            original_register_builtins()
            state = getattr(train_module, "_opt_in_harness_state", {})
            cfg = state.get("cfg")
            adapter_class = state.get("adapter_class")
            if not isinstance(cfg, dict) or adapter_class is None:
                raise RuntimeError("workspace adapter 尚未随配置加载完成")
            train_module._ENV_REGISTRY[str(cfg.get("env") or "workspace_skill")] = adapter_class

        train_module._register_builtins = register_with_workspace_adapter
        train_module.main()
    finally:
        if argv is not None:
            sys.argv = original_argv


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--config",
        "opt-in-harness/workspace/<skill>/configs/default.yaml",
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
