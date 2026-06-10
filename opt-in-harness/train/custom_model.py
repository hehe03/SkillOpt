from __future__ import annotations

import json
from collections.abc import Callable, Iterable

from aigc import UniAIGC


CustomModelFn = Callable[[str], str]


def call_optimizer_model(prompt: str) -> str:
    """接入优化模型，输入为 harness 已装配完成的完整 prompt。"""
    llm = UniAIGC()
    return str(llm.client_glm5(prompt) or "").strip()


def call_target_model(prompt: str) -> str:
    """接入执行/评判模型，输入为 harness 已装配完成的完整 prompt。"""
    llm = UniAIGC()
    return str(llm.client_glm5(prompt) or "").strip()


def _iter_sse_lines(response) -> Iterable[str]:
    if isinstance(response, str):
        yield from response.splitlines()
        return
    if hasattr(response, "iter_lines"):
        for line in response.iter_lines():
            yield line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
        return
    for line in response:
        yield line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)


def _extract_stream_delta(chunk_data: dict) -> str:
    choices = chunk_data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] or {}
    if isinstance(choice.get("delta"), dict):
        return str(choice["delta"].get("content") or "")
    if choice.get("content") is not None:
        return str(choice.get("content") or "")
    if isinstance(choice.get("message"), dict):
        return str(choice["message"].get("content") or "")
    return ""


def call_stream_model(prompt: str) -> str:
    """接入流式模型，边打印 chunk，边累计并返回完整响应。"""
    llm = UniAIGC()
    response = llm.client_glm5(prompt)
    chunks: list[str] = []
    for line_str in _iter_sse_lines(response):
        line_str = line_str.strip()
        if not line_str:
            continue
        if line_str.startswith("data:"):
            line_str = line_str[5:].strip()
        if line_str in {"[DONE]", "DONE"}:
            break
        try:
            chunk_data = json.loads(line_str)
        except json.JSONDecodeError:
            continue
        choice = (chunk_data.get("choices") or [{}])[0] or {}
        finish_reason = choice.get("finishReason") or choice.get("finish_reason")
        if finish_reason in {"END", "stop"}:
            break
        delta_content = _extract_stream_delta(chunk_data)
        if delta_content:
            chunks.append(delta_content)
            print(delta_content, end="", flush=True)
    if chunks:
        print(flush=True)
    return "".join(chunks).strip()


CUSTOM_MODELS: dict[str, CustomModelFn] = {
    # Use the same names in config:
    # model:
    #   optimizer: my-optimizer
    #   target: my-target
    "my-optimizer": call_optimizer_model,
    "my-target": call_target_model,
    "my-stream-target": call_stream_model,
    "my-stream": call_stream_model,
}


def call_custom_model(prompt: str, model: str = "", stage: str = "") -> str:
    """Dispatch a fully assembled prompt to a user-provided model.

    Args:
        prompt: Complete prompt constructed by the harness.
        model: Name from config model.optimizer/model.target.
        stage: Calling stage, such as optimizer or target.

    Returns:
        The model's final text response.
    """
    func = CUSTOM_MODELS.get(model)
    if func is None:
        known = ", ".join(sorted(CUSTOM_MODELS)) or "<none>"
        raise ValueError(
            f"Unknown custom model {model!r} at stage {stage!r}. "
            f"Add it to CUSTOM_MODELS in opt-in-harness/train/custom_model.py. Known: {known}"
        )
    return func(prompt)
