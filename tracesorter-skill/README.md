# tracesorter-skill

`tracesorter-skill` 用于优化自然语言形式的 trace 分类 skill。它和 `tracesorter-rules` 分开维护：

```text
tracesorter-skill/   自然语言判别准则，由 SkillOpt 优化
tracesorter-rules/   JSON 规则集、规则引擎和规则预测脚本
```

## 为什么单独建目录

基于规则的优化关注：

- `rules`
- `weight`
- `threshold`
- `group_cap`
- `feature`

自然语言 skill 优化关注：

- goodcase/badcase 的定义。
- 判别流程。
- 证据优先级。
- 冲突处理。
- 反复出现的 FP/FN 错误模式。
- 结构化输出格式。

这两条路线的优化对象不同，放在不同目录里更清晰。

## 初始 Skill

初始 skill 位于：

```text
tracesorter-skill/skills/trace_classifier_initial.md
```

它要求模型读取一个 Agent trace，并输出：

```json
{
  "label": "goodcase",
  "confidence": 0.0,
  "reasons": [],
  "evidence": [],
  "risk_signals": []
}
```

## 适合 SkillOpt 的原因

这个 skill 是自然语言策略文档，SkillOpt 可以通过 rollout 和反思持续改进：

- 哪些失败证据应该更强。
- 哪些中间错误不应导致误杀。
- 如何处理 final answer 与 error text 的冲突。
- 如何从误判样本中追加错误模式记忆。

相比直接优化 JSON 规则，这种形式更接近 SkillOpt 的原生能力。

## 后续建议

下一步可以为本目录补充独立的 SkillOpt adapter，让训练流程变成：

```text
trace + 当前 skill
-> LLM 分类输出 JSON
-> 和 train/val 标签比较
-> SkillOpt 根据误判改写 skill
-> val gate 选择最佳 skill
-> test 盲测
```

如果最终仍需要规则化部署，可以把优化后的自然语言 skill 再蒸馏成 `tracesorter-rules` 可执行的 JSON 规则。
