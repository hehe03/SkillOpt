# tracesorter-rules 最小闭环

`tracesorter-rules` 是一个放在当前 `SkillOpt` 仓库下的自包含规则分类小项目，用于把 trace 判定为 `goodcase` 或 `badcase`。它不依赖原始 TraceSorter 项目，也不从 `D:\code\github\hehe03\skills-repo\TraceSorter` 导入任何代码。

## 目标

- 固定一份初始规则，作为 SkillOpt 可改写的初始 skill。
- 本目录内部完成数据读取、特征抽取、规则匹配、分类和指标计算。
- 让后续 SkillOpt 优化直接作用在规则 JSON 上，暂时跳过“规则生成算法”的设计。

## 目录结构

```text
tracesorter-rules/
|-- README.md
|-- skills/
|   `-- initial.md
|-- data/
|   `-- sample_split/
|       |-- train/items.json
|       |-- val/items.json
|       `-- test/items.json
|-- scripts/
|   `-- eval_skill.py
`-- tracesorter_rules/
    |-- data.py
    |-- evaluator.py
    |-- features.py
    |-- rule_engine.py
    `-- skill.py
```

## 数据格式

每个 split 下放一个 `items.json` 或 `items.jsonl`。最小字段如下：

```json
[
  {
    "id": "case_001",
    "label": "goodcase",
    "trace": {
      "steps": [
        {"action": "search", "result": "found evidence"}
      ],
      "final_answer": "answer"
    }
  }
]
```

`label` 只能是 `goodcase` 或 `badcase`。`trace` 可以是对象、数组或 JSON 字符串。

## 从 trace 文件夹预处理

如果你的原始数据是一个 trace 文件夹和一个 `metadata.csv`，可以先运行预处理脚本生成 split 数据。

`metadata.csv` 至少需要包含：

```csv
name,label
case_001.json,goodcase
case_002.json,badcase
```

推荐额外包含 `split` 列：

```csv
name,label,source,split
case_001.json,goodcase,my_source,train
case_002.json,badcase,my_source,test
```

`name` 必须和 trace 文件名一致。`label` 支持 `good`、`bad`、`goodcase`、`badcase` 等写法。

### 防止测试集标签泄露

在 Agent 对话环境中，推荐让 Agent 只把 `metadata.csv` 的路径传给脚本，不直接读取 CSV 内容。预处理脚本默认使用：

```text
--label-policy train_val
```

这表示：

- `train/items.json` 会写入 `label`，用于规则优化。
- `val/items.json` 会写入 `label`，用于 SkillOpt selection/gate 或规则选择。
- `test/items.json` 不会写入 `label`，即使 `metadata.csv` 里有测试标签。
- `test` split 中嵌套的 `metadata.label` 也会被清洗，避免从 metadata 副本泄露。
- `split_manifest.json` 只记录可见标签分布，不记录隐藏的测试标签分布。

注意：如果 trace 文件名本身包含 `good`、`bad` 等标签语义，文件名仍可能泄露标签。真实盲测数据应避免这种命名，或后续增加匿名 ID 映射。

如果需要最终测试指标，可以让脚本内部读取 metadata 并只输出聚合指标：

```powershell
python .\tracesorter-rules\scripts\score_predictions.py `
  --predictions .\tracesorter-rules\outputs\eval_initial_test\predictions.json `
  --metadata .\metadata.csv `
  --split test `
  --output .\tracesorter-rules\outputs\eval_initial_test\private_metrics.json
```

`score_predictions.py` 不会输出逐条真实标签，只输出 `precision/recall/f1/accuracy` 等聚合结果。

按 metadata 中的 `train/val/test` 切分：

```powershell
python .\tracesorter-rules\scripts\prepare_data.py `
  --trace-path .\tracesorter-rules\data\sample_raw\traces `
  --metadata .\tracesorter-rules\data\sample_raw\metadata.csv `
  --out-dir .\tracesorter-rules\outputs\prepared_with_val
```

不启用验证集，只输出 `train/` 和 `test/`：

```powershell
python .\tracesorter-rules\scripts\prepare_data.py `
  --trace-path .\tracesorter-rules\data\sample_raw\traces `
  --metadata .\tracesorter-rules\data\sample_raw\metadata.csv `
  --out-dir .\tracesorter-rules\outputs\prepared_no_val `
  --no-val
```

如果 `metadata.csv` 没有 `split` 列，或 split 不完整，默认 `--split-mode auto` 会改用分层比例切分。也可以显式指定：

```powershell
python .\tracesorter-rules\scripts\prepare_data.py `
  --trace-path .\your_traces `
  --metadata .\metadata.csv `
  --out-dir .\tracesorter-rules\data\my_split `
  --split-mode ratio `
  --ratios 0.8,0.2 `
  --no-val
```

## 运行方式

按照仓库约定，运行 Python 前先激活 `llm` conda 环境：

```powershell
conda activate llm
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

评估示例数据：

```powershell
python .\tracesorter-rules\scripts\eval_skill.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split val `
  --out-root .\tracesorter-rules\outputs\eval_initial_val
```

输出文件：

- `predictions.json`：逐条预测、命中规则和特征快照。
- `failure_cases.json`：误判样本，适合交给 SkillOpt 做反思。
- `eval_summary.json`：`badcase_precision`、`badcase_recall`、`badcase_f1` 和 `accuracy`。

如果没有启用 `val/`，评估时直接选择 `train` 或 `test`：

```powershell
python .\tracesorter-rules\scripts\eval_skill.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\outputs\prepared_no_val `
  --split test `
  --out-root .\tracesorter-rules\outputs\eval_initial_test
```

## 对测试集输出预测标签

如果只需要给 test 样本打标签，不需要计算指标，使用：

```powershell
python .\tracesorter-rules\scripts\predict_skill.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\my_split `
  --split test `
  --out-root .\tracesorter-rules\outputs\predict_test
```

如果要更接近原项目 `run_rule_test.py` 的简单权重累加逻辑，可以关闭 `group_cap`：

```powershell
python .\tracesorter-rules\scripts\predict_skill.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\my_split `
  --split test `
  --out-root .\tracesorter-rules\outputs\predict_test_no_group_cap `
  --no-group-cap
```

输出文件：

- `predictions.csv`：便于人工查看，包含 `id`、`predicted_label`、`bad_score`、`good_score`、`reason`。
- `predictions.json`：完整命中规则详情，规则投票标签字段名为 `rule_label`，避免和真实标签混淆。
- `prediction_summary.json`：预测数量和 good/bad 分布。

该脚本不读取 `metadata.csv`，也不输出真实测试标签。

`eval_skill.py` 也支持同样的 `--no-group-cap` 参数，便于对有标签 split 做对比实验。

## SkillOpt 优化入口形态

`skills/initial.md` 中的 JSON 代码块就是待优化对象：

```json
{
  "bad_threshold": 0.6,
  "good_threshold": 0.5,
  "rules": []
}
```

后续接入 SkillOpt 时，建议限制优化范围：

- 可以修改 `bad_threshold` 和 `good_threshold`。
- 可以新增、删除或改写 `rules`。
- 可以调整规则的 `weight`、`group`、`group_cap` 和条件。
- 不要让 SkillOpt 修改本目录下的 Python 评估代码，先保持闭环稳定。

### 导入已有生成规则

如果你已经有规则生成脚本产出的 JSON，例如 `{"rules": [...]}`，可以导入成待优化 skill：

```powershell
python .\tracesorter-rules\scripts\import_rules.py `
  --rules-json .\path\to\labeled_rules.json `
  --out-skill .\tracesorter-rules\skills\generated_initial.md
```

导入后，把 `generated_initial.md` 当作优化入口即可。

本项目会兼容原规则生成脚本中的常见规则字段：

- 额外元数据字段：`layer`、`component`、`feature_group`、`source_method` 会被保留，但分类时不会强依赖。
- 条件字段：支持 `all`、`any`、`feature`、`op`、`value`。
- 分数字段：支持 `weight`、`group`、`group_cap`。
- 规则标签：支持 `label=goodcase/badcase`。

特征抽取已补齐常见生成规则会引用的字段，例如：

- `repeated_action_count`
- `empty_result_count`
- `text_chars`
- `unique_action_ratio`
- `field_nonempty_ratio:<path>`
- `field_number_mean:<path>`
- `field_text:<path>`
- `field_exists:<path>`

## 无 API 的 LLM 优化

本项目支持两种无 API 配置的 LLM 接入方式。

### 推荐：自然语言对话使用

如果你正在 Codex、OpenCode 或其他 Agent/Harness 对话环境中使用本项目，推荐直接用自然语言提出需求，例如：

```text
请用 tracesorter-rules 处理 D:\my_data\traces 和 D:\my_data\metadata.csv，不要验证集，然后用当前对话模型优化规则。
```

此时 Agent 应该自动完成：

1. 预处理 trace 文件夹和 `metadata.csv`。
2. 按你的要求生成 `train/test` 或 `train/val/test`。
3. 评估初始规则。
4. 生成规则优化 prompt。
5. 使用当前对话 harness 的大模型产出新规则。
6. 写回新的 skill。
7. 再评估并汇报优化前后指标。

也就是说，下面的命令行说明主要是给 Agent 或需要手动调试时参考；正常使用时，你不需要自己复制这些命令。

### 方式一：自行实现 llm_generate

空白函数位于：

```text
tracesorter_rules/llm.py
```

函数签名：

```python
def llm_generate(prompt: str) -> str:
    return ""
```

你可以在这里接入任意模型、内部网关或本地服务。输入是完整 prompt，返回值是 LLM 原始响应文本。响应中必须包含一份 JSON 规则对象，格式与 `skills/initial.md` 中的 JSON 一致。

调用示例：

```powershell
python .\tracesorter-rules\scripts\optimize_rules.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split train `
  --work-dir .\tracesorter-rules\outputs\opt_custom_round1 `
  --out-skill .\tracesorter-rules\outputs\opt_custom_round1\optimized.md `
  --llm-provider custom
```

### 方式二：当前对话 Harness 接力

如果你在 Codex、OpenCode 或其他 Agent/Harness 对话环境中使用本项目，更通用的方式是使用 `harness` 模式。脚本会生成一个标准任务文件，当前对话里的 Agent 读取任务后，用 harness 自带的大模型生成规则响应，不需要在本项目中配置 API key。

生成 harness 任务：

```powershell
python .\tracesorter-rules\scripts\optimize_rules.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split train `
  --work-dir .\tracesorter-rules\outputs\opt_harness_round1 `
  --out-skill .\tracesorter-rules\outputs\opt_harness_round1\optimized.md `
  --llm-provider harness
```

脚本会生成：

```text
rule_optimization_prompt.md
harness_task.md
eval_current/predictions.json
eval_current/failure_cases.json
eval_current/eval_summary.json
```

当前对话 Agent 应读取 `harness_task.md`，把生成的 LLM 响应写入脚本提示的 `harness_response.md`。之后运行：

```powershell
python .\tracesorter-rules\scripts\apply_llm_response.py `
  --response .\tracesorter-rules\outputs\opt_harness_round1\harness_response.md `
  --out-skill .\tracesorter-rules\outputs\opt_harness_round1\optimized.md
```

这就是“当前对话 harness”模式：Python 不调用任何 API，也不绑定具体 CLI；生成规则的动作由当前对话中的 Agent/Harness 完成。

### 方式三：任意 CLI 模型命令

如果你的 harness 暴露了可命令行调用的模型入口，可以使用通用 `cli` 模式，不必限定为 Codex 或 OpenCode。

通用命令：

```powershell
python .\tracesorter-rules\scripts\optimize_rules.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split train `
  --work-dir .\tracesorter-rules\outputs\opt_cli_round1 `
  --out-skill .\tracesorter-rules\outputs\opt_cli_round1\optimized.md `
  --llm-provider cli `
  --llm-command your-agent-cli run "{prompt}"
```

`codex` 和 `opencode` 只是内置示例别名：

```text
codex    -> codex exec --skip-git-repo-check {prompt}
opencode -> opencode run {prompt}
```

如果你的本机命令不同，可以用 `--llm-command` 覆盖。支持三个占位符：

- `{prompt}`：把完整 prompt 作为命令参数。
- `{prompt_file}`：把 prompt 写入临时文件，并把文件路径传给命令。
- `{stdin}`：通过标准输入传递 prompt。

例如 Windows PowerShell 禁止执行 `opencode.ps1` 时，可以尝试显式使用 `.cmd`：

```powershell
python .\tracesorter-rules\scripts\optimize_rules.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split train `
  --work-dir .\tracesorter-rules\outputs\opt_opencode_round1 `
  --out-skill .\tracesorter-rules\outputs\opt_opencode_round1\optimized.md `
  --llm-provider opencode `
  --llm-command opencode.cmd run "{prompt}"
```

### 对话接力模式

如果只想生成 prompt，不生成 harness 任务文件，可以使用 `prompt_only`：

```powershell
python .\tracesorter-rules\scripts\optimize_rules.py `
  --skill .\tracesorter-rules\skills\initial.md `
  --split-dir .\tracesorter-rules\data\sample_split `
  --split train `
  --work-dir .\tracesorter-rules\outputs\opt_prompt_round1 `
  --out-skill .\tracesorter-rules\outputs\opt_prompt_round1\optimized.md `
  --llm-provider prompt_only
```

脚本会生成：

```text
rule_optimization_prompt.md
eval_current/predictions.json
eval_current/failure_cases.json
eval_current/eval_summary.json
```

把 `rule_optimization_prompt.md` 的内容交给当前对话 harness，让它输出 JSON 规则，再保存成新的 skill 即可。

## 支持的规则条件

每条规则支持 `all` 和 `any` 条件：

```json
{
  "id": "runtime_error_text",
  "label": "badcase",
  "weight": 0.7,
  "group": "error_signal",
  "group_cap": 0.8,
  "description": "Trace 中出现失败文本。",
  "all": [
    {"feature": "has_error_text", "op": "==", "value": true}
  ]
}
```

支持的操作符：

- `==`、`!=`
- `>`、`>=`、`<`、`<=`
- `contains`
- `regex`
- `truthy`
- `falsey`

## 内置特征

固定特征包括：

- `parse_error`
- `is_empty_trace`
- `has_steps`
- `step_count`
- `trace_text_chars`
- `has_error_text`
- `error_count`
- `result_count`
- `empty_result_ratio`
- `nonempty_result_ratio`
- `has_final_answer`
- `final_answer_count`
- `action_count`
- `unique_action_count`
- `max_consecutive_same_action`

还会自动生成一部分动态字段特征，例如：

- `field_exists:status`
- `field_text:status`
- `field_count:steps`
- `field_number:metrics.score`

这些特征会写入 `predictions.json`，方便 SkillOpt 根据误判样本新增规则。
