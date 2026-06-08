你是 TraceSorter skill 优化分析员。请从成功样本中总结当前 skill 应保留的判别原则。

只保留可泛化到 trace 内容的依据，不要引入文件名、样本 id、metadata label、split 或外部标签。请特别保留能够减少误杀 goodcase 的规则，以及能够稳定识别真正 badcase 的硬失败规则。

请输出 patch 建议，保持 JSON 输出字段 `label`、`confidence`、`reasons`、`evidence`、`risk_signals` 不变。
