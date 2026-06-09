from __future__ import annotations

import atexit
import importlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


_LLM_FILE_LOCK = threading.Lock()
_LLM_FILE_STEP = 0
_ACTIVE_PROCESSES: set[subprocess.Popen] = set()
_ACTIVE_PROCESS_LOCK = threading.Lock()
_CLEANUP_REGISTERED = False
_PREVIOUS_SIGNAL_HANDLERS: dict[int, object] = {}


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


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
    return _env_first("OPT_IN_HARNESS_AGENT_BACKEND", default="auto").lower() or "auto"


def _hide_subprocess_window() -> bool:
    value = _env_first("OPT_IN_HARNESS_HIDE_SUBPROCESS_WINDOW", default="1").lower()
    return value not in {"0", "false", "no", "off"}


def _stream_subprocess_output() -> bool:
    value = _env_first("OPT_IN_HARNESS_STREAM_SUBPROCESS_OUTPUT", default="0").lower()
    return value in {"1", "true", "yes", "on"}


def _harness_log(message: str) -> None:
    if _stream_subprocess_output():
        print(message, flush=True)


def _subprocess_creationflags(existing: int = 0) -> int:
    flags = int(existing or 0)
    if os.name == "nt" and _hide_subprocess_window():
        flags |= subprocess.CREATE_NO_WINDOW
    return flags


def _subprocess_startupinfo(existing=None):
    if os.name != "nt" or not _hide_subprocess_window():
        return existing
    startupinfo = existing or subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=_subprocess_creationflags(),
                startupinfo=_subprocess_startupinfo(),
            )
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _cleanup_active_processes() -> None:
    with _ACTIVE_PROCESS_LOCK:
        processes = list(_ACTIVE_PROCESSES)
    for proc in processes:
        _terminate_process_tree(proc)


def _handle_parent_exit_signal(signum, frame) -> None:
    del frame
    _cleanup_active_processes()
    previous = _PREVIOUS_SIGNAL_HANDLERS.get(signum)
    if callable(previous):
        previous(signum, None)
        return
    if signum == getattr(signal, "SIGINT", None):
        raise KeyboardInterrupt
    raise SystemExit(128 + int(signum))


def _ensure_process_cleanup_registered() -> None:
    global _CLEANUP_REGISTERED
    if _CLEANUP_REGISTERED:
        return
    _CLEANUP_REGISTERED = True
    atexit.register(_cleanup_active_processes)
    for signum in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if signum is None:
            continue
        try:
            _PREVIOUS_SIGNAL_HANDLERS[signum] = signal.getsignal(signum)
            signal.signal(signum, _handle_parent_exit_signal)
        except (OSError, ValueError):
            pass


def _write_stream(target, chunk) -> None:
    if chunk in (None, b"", ""):
        return
    try:
        target.write(chunk)
    except TypeError:
        target.write(chunk.decode("utf-8", errors="replace"))
    target.flush()


def _read_pipe_to_buffer(pipe, target, chunks: list) -> None:
    try:
        while True:
            chunk = pipe.readline()
            if not chunk:
                break
            chunks.append(chunk)
            _write_stream(target, chunk)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _join_chunks(chunks: list, *, text_mode: bool):
    if text_mode:
        return "".join(str(chunk) for chunk in chunks)
    return b"".join(chunks)


def _communicate_with_streaming(proc: subprocess.Popen, input_data, timeout, *, text_mode: bool):
    stdout_chunks: list = []
    stderr_chunks: list = []
    threads: list[threading.Thread] = []
    if proc.stdout is not None:
        thread = threading.Thread(
            target=_read_pipe_to_buffer,
            args=(proc.stdout, sys.stdout, stdout_chunks),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    if proc.stderr is not None:
        thread = threading.Thread(
            target=_read_pipe_to_buffer,
            args=(proc.stderr, sys.stderr, stderr_chunks),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    if input_data is not None and proc.stdin is not None:
        try:
            proc.stdin.write(input_data)
            proc.stdin.close()
        except Exception:
            pass

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(proc)
        proc.wait()
        for thread in threads:
            thread.join(timeout=1)
        stdout = _join_chunks(stdout_chunks, text_mode=text_mode)
        stderr = _join_chunks(stderr_chunks, text_mode=text_mode)
        exc.output = stdout
        exc.stdout = stdout
        exc.stderr = stderr
        raise

    for thread in threads:
        thread.join()
    return (
        _join_chunks(stdout_chunks, text_mode=text_mode),
        _join_chunks(stderr_chunks, text_mode=text_mode),
    )


def _run_subprocess(*args, **kwargs) -> subprocess.CompletedProcess:
    _ensure_process_cleanup_registered()
    input_data = kwargs.pop("input", None)
    timeout = kwargs.pop("timeout", None)
    check = bool(kwargs.pop("check", False))
    capture_output = bool(kwargs.pop("capture_output", False))
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output.")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if input_data is not None and kwargs.get("stdin") is None:
        kwargs["stdin"] = subprocess.PIPE
    kwargs["creationflags"] = _subprocess_creationflags(kwargs.get("creationflags", 0))
    kwargs["startupinfo"] = _subprocess_startupinfo(kwargs.get("startupinfo"))

    proc = subprocess.Popen(*args, **kwargs)
    with _ACTIVE_PROCESS_LOCK:
        _ACTIVE_PROCESSES.add(proc)
    try:
        try:
            should_stream = _stream_subprocess_output() and (
                kwargs.get("stdout") == subprocess.PIPE or kwargs.get("stderr") == subprocess.PIPE
            )
            if should_stream:
                stdout, stderr = _communicate_with_streaming(
                    proc,
                    input_data,
                    timeout,
                    text_mode=bool(kwargs.get("text") or kwargs.get("universal_newlines")),
                )
            else:
                stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(proc)
            stdout, stderr = proc.communicate()
            exc.output = stdout
            exc.stdout = stdout
            exc.stderr = stderr
            raise
        except BaseException:
            _terminate_process_tree(proc)
            raise
        completed = subprocess.CompletedProcess(
            args=proc.args,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        if check and completed.returncode:
            raise subprocess.CalledProcessError(
                completed.returncode,
                completed.args,
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return completed
    finally:
        with _ACTIVE_PROCESS_LOCK:
            _ACTIVE_PROCESSES.discard(proc)


def _format_command_arg(value: str, variables: dict[str, str]) -> str:
    try:
        return value.format(**variables)
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in harness command: {exc}") from exc


def _safe_stage_name(stage: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(stage or "llm")).strip("._-")
    return safe or "llm"


def _next_llm_file_paths(stage: str, *, cwd: str | os.PathLike[str] | None) -> tuple[Path, Path, int]:
    global _LLM_FILE_STEP
    configured = _env_first("OPT_IN_HARNESS_LLM_FILES_DIR")
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


def _load_custom_model_callable():
    module_ref = _env_first("OPT_IN_HARNESS_CUSTOM_MODEL_MODULE", default="custom_model")
    function_name = _env_first("OPT_IN_HARNESS_CUSTOM_MODEL_FUNCTION", default="call_custom_model")
    module_path = Path(module_ref)
    sibling_path = Path(__file__).resolve().parent / f"{module_ref}.py"
    if module_path.suffix == ".py" or module_path.exists():
        if not module_path.is_absolute():
            module_path = (Path(__file__).resolve().parent / module_path).resolve()
    elif sibling_path.exists():
        module_path = sibling_path
    else:
        module_path = None

    if module_path is not None:
        spec = importlib.util.spec_from_file_location("opt_in_harness_custom_model", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载自定义模型模块：{module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_ref)
    func = getattr(module, function_name, None)
    if not callable(func):
        raise AttributeError(f"自定义模型模块 {module_ref!r} 中没有可调用函数 {function_name!r}")
    return func


def _run_custom_model_chat(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    stage: str,
    cwd: str | os.PathLike[str] | None,
) -> str:
    del model, timeout
    prompt_path, output_path, _step = _next_llm_file_paths("custom_model_" + _safe_stage_name(stage), cwd=cwd)
    prompt_path.write_text(prompt, encoding="utf-8")
    _harness_log(f"[harness/custom_model] start stage={stage} prompt={prompt_path}")
    response = str(_load_custom_model_callable()(prompt) or "").strip()
    output_path.write_text(response, encoding="utf-8")
    if not response:
        raise RuntimeError(
            "custom_model returned an empty response. "
            "请在 opt-in-harness/train/custom_model.py 的 call_custom_model(prompt) 中接入实际模型。"
        )
    _harness_log(f"[harness/custom_model] done stage={stage} chars={len(response)}")
    return response


def _run_custom_agent_command(
    prompt: str,
    *,
    model: str,
    timeout: int | None,
    stage: str,
    cwd: str | os.PathLike[str] | None,
) -> str:
    command_json = _env_first("OPT_IN_HARNESS_AGENT_COMMAND_JSON")
    command_shell = _env_first("OPT_IN_HARNESS_AGENT_COMMAND")
    if not command_json and not command_shell:
        raise ValueError("No custom harness command configured")

    prompt_path, output_path, _step = _next_llm_file_paths(stage, cwd=cwd)
    prompt_path.write_text(prompt, encoding="utf-8")
    configured_text = command_json or command_shell
    allow_stdin = _env_first("OPT_IN_HARNESS_AGENT_USE_STDIN").lower() in {
        "1",
        "true",
        "yes",
    }
    if "{prompt_file}" not in configured_text and not allow_stdin:
        raise ValueError(
            "自定义 harness 默认使用文件协议，请在命令中加入 {prompt_file}。"
            "如果确实要使用 stdin，请设置 OPT_IN_HARNESS_AGENT_USE_STDIN=1。"
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
            raise ValueError("OPT_IN_HARNESS_AGENT_COMMAND_JSON must be a JSON string array")
        command = [_format_command_arg(arg, variables) for arg in raw_command]
        stdin_prompt = prompt if allow_stdin and "{prompt_file}" not in command_json else None
        _harness_log(
            f"[harness/custom] start stage={stage} prompt={prompt_path} output={output_path}"
        )
        proc = _run_subprocess(
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
        _harness_log(
            f"[harness/custom] start stage={stage} prompt={prompt_path} output={output_path}"
        )
        proc = _run_subprocess(
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
    _harness_log(f"[harness/custom] done stage={stage} chars={len(response)}")
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
            "OPT_IN_HARNESS_AGENT_BACKEND=codex，但未找到 Codex CLI。"
            "请设置 CODEX_CLI_BIN，或改用 OPT_IN_HARNESS_AGENT_BACKEND=nga/opencode，"
            "或配置 OPT_IN_HARNESS_AGENT_COMMAND_JSON。"
        )
    with tempfile.TemporaryDirectory(prefix="opt_harness_codex_chat_") as temp_dir:
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
        _harness_log(f"[harness/codex] start cwd={cwd or os.getcwd()} output={output_path}")
        proc = _run_subprocess(
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
        _harness_log(f"[harness/codex] done chars={len(response)}")
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
            "OPT_IN_HARNESS_AGENT_BACKEND=nga，但未找到 Nga CLI。"
            "请确认 nga 在 PATH 或 ~/OCHOME 中，或设置 NGA_CLI_BIN。"
        )

    run_dir = Path(_env_first("OPT_IN_HARNESS_NGA_RUN_DIR") or cwd or os.getcwd()).resolve()
    prompt_path, output_path, _step = _next_llm_file_paths("nga_" + _safe_stage_name(stage), cwd=run_dir)
    prompt_path.write_text(prompt, encoding="utf-8")
    instruction = _env_first(
        "OPT_IN_HARNESS_NGA_INSTRUCTION",
        default=(
            "Read the attached file and answer the question directly. "
            "Preserve the requested output format exactly and do not add commentary."
        ),
    )
    command = [
        nga_bin,
        "run",
        instruction,
        "--file",
        str(prompt_path),
    ]
    _harness_log(f"[harness/nga] start stage={stage} prompt={prompt_path}")
    proc = _run_subprocess(
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
    _harness_log(f"[harness/nga] done stage={stage} chars={len(response)}")
    return response


def _opencode_model_args(model: str) -> list[str]:
    configured = _env_first("OPT_IN_HARNESS_OPENCODE_MODEL", "OPENCODE_MODEL")
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
            "OPT_IN_HARNESS_AGENT_BACKEND=opencode，但未找到 opencode CLI。"
            "请确认 opencode 在 PATH 中，或设置 OPENCODE_CLI_BIN。"
        )

    run_dir = Path(_env_first("OPT_IN_HARNESS_OPENCODE_RUN_DIR") or cwd or os.getcwd()).resolve()
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
    agent = _env_first("OPT_IN_HARNESS_OPENCODE_AGENT")
    if agent:
        command.extend(["--agent", agent])
    _harness_log(f"[harness/opencode] start stage={stage} prompt={prompt_path}")
    proc = _run_subprocess(
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
    _harness_log(f"[harness/opencode] done stage={stage} chars={len(response)}")
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
    1. OPT_IN_HARNESS_AGENT_COMMAND_JSON / OPT_IN_HARNESS_AGENT_COMMAND
    2. OPT_IN_HARNESS_AGENT_BACKEND when set to custom_model, nga,
       opencode, or codex
    3. auto-detect Nga CLI
    4. auto-detect opencode CLI
    5. auto-detect Codex CLI
    """
    if _env_first("OPT_IN_HARNESS_AGENT_COMMAND_JSON") or _env_first(
        "OPT_IN_HARNESS_AGENT_COMMAND"
    ):
        return _run_custom_agent_command(prompt, model=model, timeout=timeout, stage=stage, cwd=cwd)
    backend = _requested_backend()
    if backend in {"custom_model", "custom-model", "python"}:
        return _run_custom_model_chat(prompt, model=model, timeout=timeout, stage=stage, cwd=cwd)
    if backend == "nga":
        return _run_nga_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if backend == "opencode":
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if backend == "codex":
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    if backend not in {"auto", ""}:
        raise ValueError(
            "OPT_IN_HARNESS_AGENT_BACKEND 只支持 auto、custom_model、nga、opencode、codex；"
            "其它 harness 请配置 OPT_IN_HARNESS_AGENT_COMMAND_JSON。"
        )
    if _resolve_nga_cli():
        return _run_nga_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if _resolve_opencode_cli():
        return _run_opencode_chat(prompt, model=model, timeout=timeout, cwd=cwd, stage=stage)
    if _resolve_codex_cli():
        return _run_codex_chat(prompt, model=model, timeout=timeout, cwd=cwd, sandbox=sandbox)
    raise RuntimeError(
        "没有找到可自动调用的 Agent harness。请安装/配置 Nga、opencode 或 Codex CLI，"
        "或设置 OPT_IN_HARNESS_AGENT_COMMAND_JSON / OPT_IN_HARNESS_AGENT_COMMAND。"
    )


def describe_agent_backend() -> str:
    if _env_first("OPT_IN_HARNESS_AGENT_COMMAND_JSON"):
        return "custom harness command from OPT_IN_HARNESS_AGENT_COMMAND_JSON"
    if _env_first("OPT_IN_HARNESS_AGENT_COMMAND"):
        return "custom harness command from OPT_IN_HARNESS_AGENT_COMMAND"
    backend = _requested_backend()
    if backend in {"custom_model", "custom-model", "python"}:
        return "custom Python model function"
    if backend == "nga" or (backend == "auto" and _resolve_nga_cli()):
        return f"Nga CLI ({_resolve_nga_cli()})"
    if backend == "opencode" or (backend == "auto" and _resolve_opencode_cli()):
        return f"opencode CLI ({_resolve_opencode_cli()})"
    if backend == "codex" or (backend == "auto" and _resolve_codex_cli()):
        return f"Codex CLI ({_resolve_codex_cli()})"
    return "unconfigured Agent harness"
