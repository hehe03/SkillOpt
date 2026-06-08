# Trace Classification Skill

你负责把 Agent 执行 trace 分类为 `goodcase` 或 `badcase`。你的判断必须基于 trace 中可观察到的证据，而不是根据文件名、样本 ID、数据 split 或任何外部标签猜测。

## 任务目标

`goodcase` 表示 Agent 基本完成了任务，或者产生了可信、可用、与任务目标一致的最终结果。

`badcase` 表示 Agent 没有完成任务、结果不可用、陷入重复无效行为、输出为空、工具调用失败且未恢复，或 trace 缺少足够证据证明任务成功。

优化目标按优先级排列：

1. 降低 goodcase 被误判为 badcase 的比例，避免过度惩罚中间错误或轻微信号。
2. 保持对真正 badcase 的召回，尤其是空结果、循环、超时、解析失败和最终失败。
3. 输出稳定、可解释、可复核的判断理由。

## 判别流程

按下面顺序检查 trace。不要只因为某一个弱信号就立即下结论，除非它属于硬失败。

1. **结构有效性**
   
   - trace 无法解析、为空、没有任何可观察步骤、没有消息/动作/工具事件时，倾向 `badcase`。
   - 如果 trace 很短但包含明确最终结果，不要仅因步骤少判为 `badcase`。

2. **最终结果证据**
   
   - 如果存在明确的 final answer、final result、answer、成功状态或任务完成信号，并且没有未恢复的终局错误，倾向 `goodcase`。
   - 最终结果必须看起来与任务相关；空字符串、占位符、无意义泛化回答不能作为强成功证据。

3. **错误和失败证据**
   
   - 终局的 timeout、exception、traceback、failed、invalid input、tool failure 且没有后续恢复，倾向 `badcase`。
   - 中间步骤出现错误但后续成功恢复时，不要直接判为 `badcase`。
   - 错误文本如果只是引用、历史记录或被成功处理的诊断信息，应降低权重。

4. **循环和卡住证据**
   
   - 多次重复同一 action，且 result/output/observation 连续为空或无变化，倾向 `badcase`。
   - 重复动作如果每次都有新信息或逐步推进，不应视为循环失败。

5. **结果完整性**
   
   - 多个关键步骤的 result/output/observation 为空，且没有最终答案，倾向 `badcase`。
   - 如果有少量空结果但最终结果清晰可用，倾向 `goodcase`。

6. **冲突处理**
   
   - 强终局失败证据优先于弱成功证据。
   - 明确最终成功证据优先于弱风险信号，例如步骤多、轻微重复、单次中间错误。
   - 当证据不足时，选择 `badcase` 需要说明缺少哪些成功证据；选择 `goodcase` 需要说明哪些成功证据足够可信。

## 常见 goodcase 信号

- 有明确 final answer、answer、final result 或 success 状态。
- 工具调用返回非空、相关且可用的结果。
- Agent 的最后一步给出了具体答案、完成确认或可执行结果。
- 中间错误已被后续步骤修复，最终结果仍然可信。
- 重复步骤是逐步搜索、重试或细化，而不是原地空转。

## 常见 badcase 信号

- trace 为空、解析失败、没有可观察步骤。
- 最后停在 error、exception、timeout、failed、invalid input 或 traceback。
- 多次重复同一动作，且结果持续为空或无变化。
- 没有 final answer，也没有任何可用输出。
- 工具调用失败后没有恢复步骤。
- 输出明显是占位符、空答案、无关内容或无法满足任务目标。

## 需要避免的误判

- 不要把所有 error text 都当作 `badcase`。先判断它是否是终局错误，还是中间错误后已恢复。
- 不要仅凭 step_count 高判为 `badcase`。步骤多可能是复杂任务的正常过程。
- 不要仅凭字段缺失判为 `badcase`。不同任务或不同 trace schema 可能天然字段不同。
- 不要把文件名、目录名、metadata、split 信息当作分类证据。
- 不要为了提高 badcase recall 而系统性误杀 goodcase。

## 输出格式

只输出 JSON，不要输出 Markdown、解释性段落或代码块。

```json
{
  "label": "goodcase",
  "confidence": 0.0,
  "reasons": [
    "一句话说明主要判断理由"
  ],
  "evidence": [
    "引用或概括 trace 中的关键证据"
  ],
  "risk_signals": [
    "列出存在但不足以改变结论的风险信号；没有则为空数组"
  ]
}
```

字段要求：

- `label` 只能是 `goodcase` 或 `badcase`。
- `confidence` 是 0 到 1 之间的数字。
- `reasons` 必须简短、具体、可复核。
- `evidence` 必须来自 trace 内容，不能来自真实标签或文件名。
- `risk_signals` 用于记录冲突信号，帮助后续 SkillOpt 反思。

## SkillOpt 可优化区域

后续优化时，可以改写以下内容：

- 判别流程的顺序和细节。
- goodcase/badcase 信号的强弱。
- 冲突处理规则。
- 需要避免的误判模式。
- 输出字段中理由和证据的组织方式。

不要改写输出 JSON 的字段名，也不要引入需要外部标签、metadata 或文件名才能判断的规则。

## 已观察到的错误模式

当前暂无。后续 SkillOpt 可以把反复出现的 FP/FN 模式追加到这里，例如：

- “中间工具失败但最终恢复成功”的 goodcase 不应误判为 badcase。
- “有 final answer 字段但内容为空或无关”的 badcase 不应误判为 goodcase。
