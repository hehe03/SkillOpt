from __future__ import annotations

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
