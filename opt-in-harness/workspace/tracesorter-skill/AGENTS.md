# tracesorter-skill 对话式使用指南

本目录用于自然语言 `trace classification skill` 的优化实验，和根目录下的 `tracesorter-rules/` 分开。

## 定位

- `tracesorter-skill/`：优化自然语言 trace 分类准则，让 SkillOpt 改进判别策略、证据优先级和错误模式记忆。
- `tracesorter-rules/`：优化 JSON 规则集、规则权重、阈值和规则过滤策略。

## 使用原则

- 用户通过自然语言提供数据路径、目标指标和优化偏好，Agent 负责执行准备、评估、反思和写回。
- 本目录的 skill 不应直接依赖 `tracesorter-rules` 的规则引擎。
- 本目录的 skill 可以引用 trace 内容、模型输出、误判样本和错误模式，但不要读取或利用测试集真实标签。
- 如果需要最终测试指标，只能通过聚合评分脚本或外部评估流程计算，不要把测试集逐条真实标签放进优化 prompt。

## 默认文件

- 初始自然语言 skill：`tracesorter-skill/skills/trace_classifier_initial.md`
- 后续优化输出建议放在：`tracesorter-skill/outputs/`

## Agent 输出要求

- 最终回答用中文。
- 优先说明优化后的 skill 路径、评估结果和下一步建议。
- 不要把本目录和 `tracesorter-rules/` 的用途混在一起。
