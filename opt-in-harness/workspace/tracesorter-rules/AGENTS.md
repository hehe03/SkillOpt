# tracesorter-rules 对话式使用指南

本文件适用于 `tracesorter-rules/` 目录。目标是让用户通过自然语言对话使用本项目，而不是自己在 PowerShell 中运行命令。

## 核心原则

- 用户只需要提供 trace 文件夹、`metadata.csv`、是否需要验证集、目标指标或输出偏好。
- Agent 负责在后台运行预处理、评估、prompt 生成、规则优化和结果验证。
- 除非用户明确要求展示命令，否则不要把一串命令当作主要答案；应直接执行并用中文汇报结果。
- 运行 Python 前遵循仓库根目录要求，使用 `conda run -n llm python ...` 或已激活的 `llm` 环境，并设置 UTF-8 输出，避免 Windows 中文乱码。
- 本目录不得依赖原 TraceSorter 项目路径或导入原项目代码。
- 防标签泄露：不要用 `Get-Content`、编辑器读取、复制粘贴或总结用户的 `metadata.csv`。Agent 只能把 metadata 路径传给脚本，由脚本内部加载。
- 默认预处理必须使用 `label_policy=train_val`，把 `train/val` 标签写入 `items.json`，用于训练反思和 selection/gate；不要把 `test` 标签写入任何可被 Agent 阅读的中间文件，包括嵌套的 `metadata.label`。

## 用户自然语言意图映射

当用户说“把我的 trace 数据处理成可优化格式”时：

1. 读取用户给出的 trace 文件夹和 metadata 路径。
2. 运行 `scripts/prepare_data.py`。
3. 如果用户说“不需要验证集”“数据少”“只分训练和测试”，使用 `--no-val`。
4. 如果 metadata 有 split 列，优先按 metadata 切分；否则使用 ratio 切分。
5. 保持默认 `--label-policy train_val`，让 `train/val` 可评估，避免 `test` 标签落盘；`test` 中的 `metadata.label` 也必须清洗。
6. 汇报生成的 split 目录、各 split 数量和可见标签分布，不汇报隐藏标签分布。

当用户说“评估当前规则”时：

1. 运行 `scripts/eval_skill.py`。
2. 默认评估 `test`；如果用户要优化过程反馈，则评估 `train` 或 `val`。
3. 如果评估 split 没有可见标签，只汇报预测数量和输出路径，不声称有 precision/recall/f1。
4. 如果用户要求用隐藏测试标签计算最终指标，运行 `scripts/score_predictions.py`，只输出聚合指标，不输出逐条真实标签。

当用户说“对测试集输出标签/预测标签”时：

1. 运行 `scripts/predict_skill.py`。
2. 默认使用 `split=test`。
3. 只输出 `predicted_label`、分数和命中规则；不要读取 metadata，也不要输出真实标签。
4. 如果用户在对齐原项目 `run_rule_test.py` 默认规则加权结果，优先加 `--no-group-cap`，因为原项目默认是简单权重累加。

当用户说“用当前对话/你自己/当前 Agent 优化规则”时：

1. 运行 `scripts/optimize_rules.py --llm-provider harness` 生成 `harness_task.md` 和 `rule_optimization_prompt.md`。
2. Agent 自己读取生成的 `harness_task.md` 或 `rule_optimization_prompt.md`。
3. Agent 用当前对话大模型生成新的 JSON 规则响应，写入 `harness_response.md`。
4. 运行 `scripts/apply_llm_response.py`，把响应转换成新的 skill Markdown。
5. 用 `scripts/eval_skill.py` 在指定 split 上评估新 skill。
6. 汇报优化前后指标对比、输出文件路径和主要规则变化。

## 默认路径约定

- 初始 skill：`tracesorter-rules/skills/initial.md`
- 用户数据预处理输出：`tracesorter-rules/data/user_split`
- 对话式优化输出：`tracesorter-rules/outputs/harness_round_<N>`
- 优化后 skill：`tracesorter-rules/outputs/harness_round_<N>/optimized.md`
- 隐藏测试标签聚合指标：`tracesorter-rules/outputs/<run>/private_metrics.json`

## 输出要求

- 最终回答用中文。
- 优先给出结果和文件路径，再简要解释过程。
- 如果没有足够信息，最多问 1 到 3 个必要问题，例如 trace 文件夹路径、metadata 路径、是否保留验证集。
- 不要要求用户自己运行命令，除非用户明确表示要手动操作。
