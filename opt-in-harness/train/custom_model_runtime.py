from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import re
from collections.abc import Iterable
from pathlib import Path


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def load_custom_model_callable():
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


def call_custom_model_function(func, prompt: str, *, model: str, stage: str) -> str:
    signature = inspect.signature(func)
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    kwargs = {}
    if accepts_kwargs or "model" in signature.parameters:
        kwargs["model"] = model
    if accepts_kwargs or "stage" in signature.parameters:
        kwargs["stage"] = stage
    response = func(prompt, **kwargs)
    if response is None:
        return ""
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="replace").strip()
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, Iterable) and not isinstance(response, dict):
        chunks: list[str] = []
        for chunk in response:
            if chunk is None:
                continue
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8", errors="replace"))
            else:
                chunks.append(str(chunk))
        return "".join(chunks).strip()
    return str(response).strip()


def strip_custom_model_think_enabled() -> bool:
    value = _env_first("OPT_IN_HARNESS_STRIP_CUSTOM_MODEL_THINK", default="1").lower()
    return value not in {"0", "false", "no", "off"}


def strip_think_blocks(text: str) -> str:
    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<think\b[^>]*>.*\Z", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def call_custom_model_direct(prompt: str, *, model: str, stage: str) -> tuple[str, str]:
    """Call a custom Python model without routing through an Agent CLI harness."""
    raw_response = call_custom_model_function(
        load_custom_model_callable(),
        prompt,
        model=model,
        stage=stage,
    )
    response = strip_think_blocks(raw_response) if strip_custom_model_think_enabled() else raw_response
    return response, raw_response
