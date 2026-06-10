from __future__ import annotations
import json
from collections.abc import Callable
from aigc import UniAIGC

CustomModelFn = Callable[[str], str]


def call_optimizer_model(prompt: str) -> str:
    """Fill this function with your optimizer model invocation."""
    llm = UniAIGC()
    res = llm.client_glm5(prompt)
    return res


def call_target_model(prompt: str) -> str:
    """Fill this function with your target/execution model invocation."""
    llm = UniAIGC()
    res = llm.client_glm5(prompt)
    return res

def call_stream_model(prompt: str) -> str:
    """Fill this function with your target/execution model invocation."""
    llm = UniAIGC()
    response = llm.client_glm5(prompt)
    for line_bytes in response.iter_lines():
        if line_bytes:
            # 1. 将行 bytes 解码为字符串
            line_str = line_bytes.decode('utf-8')
            # 2. SSE 协议通常以 "data: " 开头，结尾可能是 [DONE]
            if line_str.startswith("data:"):
                content = line_str[5:]  # 截取 "data:" 后面的 JSON 字符串
                try:
                    # 3. 解析为 JSON 对象并打印内容
                    chunk_data = json.loads(content)
                    finishReason = chunk_data['choices'][0].get('finishReason', '')
                    if finishReason == 'END':
                        print('输出结束')
                        break
                    delta_content = chunk_data['choices'][0].get('content', '')
                    print(delta_content, end='', flush=True)  # 实现打字机效果
                except json.JSONDecodeError:
                    pass



CUSTOM_MODELS: dict[str, CustomModelFn] = {
    # Use the same names in config:
    # model:
    #   optimizer: my-optimizer
    #   target: my-target
    "my-optimizer": call_optimizer_model,
    "my-target": call_target_model,
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
