---
name: agentevals-default-trace-judge
description: 使用 AgentEvals 内置 trajectory accuracy 默认 prompt，将 Agent trace 分类为 goodcase 或 badcase。适用于用户要求 AgentEvals 默认 prompt judge、默认轨迹评估、默认 LLM-as-Judge、或基于默认 prompt 执行 trace 分类时。
---

# AgentEvals 默认 Prompt Trace Judge

本 skill 用于让 Agent 直接按照 AgentEvals 的默认 trajectory accuracy prompt 对 Agent trace 做 `goodcase` / `badcase` 分类。所有判断必须基于 prompt 完成，不使用规则脚本、关键词匹配或启发式批处理替代模型判断。

## AgentEvals 默认 Prompt

对每条待评估 trace，使用以下 prompt 结构。将其中的“待评估轨迹”替换为当前 trace 的消息化轨迹内容。

你是一个专业数据标注员。

你的任务是评估一个 AI Agent 内部轨迹的准确性。

一个准确的轨迹应当满足：

- 步骤之间逻辑合理。
- 展现出清晰的推进过程。
- 相对高效，虽然不要求完美高效。

首先，通过查看输入来理解轨迹的目标；如果输入不存在，则从第一条消息的内容中推断目标；同时查看最后一条消息的输出。

理解目标后，根据该轨迹是否有助于实现这个目标来评分。

请评估以下轨迹：

待评估轨迹

## 分类映射

- 如果模型认为轨迹准确、合理地完成或推进了任务，判为 `goodcase`。
- 如果模型认为轨迹不准确、逻辑断裂、没有有效推进、没有产生可用结果、或明显偏离任务目标，判为 `badcase`。
- 如果模型内部使用布尔分数，则 `score=true` 对应 `goodcase`，`score=false` 对应 `badcase`。
