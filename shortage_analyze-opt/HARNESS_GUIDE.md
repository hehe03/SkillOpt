# 新 harness 接手指南

本文档面向新的 Agent harness，例如 Nga、Codex、opencode 或其它支持调用自身大模型的 Agent。读完后应能继续运行 `shortage_analyze` 的 SkillOpt 优化，并避免误读原始数据或测试集标签。

## 任务目标

使用 SkillOpt 优化处理后的初始 skill：

```text
shortage_analyze-opt/shortage_analyze-init/initial_skill.md
```

原始目录：

```text
shortage_analyze-opt/shortage_analyze
```

只作为 process 阶段构建初始 skill 和比较优化前后效果的来源，不参与训练过程，不要修改。

优化完成后的 skill 和脚本放在：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/best_kill.md
shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

## 必须遵守的边界

1. 不要修改 `shortage_analyze-opt/shortage_analyze/`。
2. `shortage_analyze-opt/train` 只能读取 `shortage_analyze-opt/processed` 和 `shortage_analyze-opt/shortage_analyze-init`。
3. 训练过程不能读取 `data.xlsx`、原始全量数据、测试集标签或 `shortage_analyze/references`。
4. 可以读取原始数据的脚本只放在 `shortage_analyze-opt/process`，例如数据预处理和训练后测试集比较。
5. target skill 执行不要逐样本调用 LLM。当前机制是先生成或复用 Python 规则脚本，再用脚本批量预测。

默认训练配置必须保持：

```yaml
evaluation:
  eval_test: false

env:
  data_path: ""
  allow_test_labels: false
  skill_init: shortage_analyze-opt/shortage_analyze-init/initial_skill.md
  initial_skill_path: shortage_analyze-opt/shortage_analyze-init/initial_skill.md
  initial_script_path: shortage_analyze-opt/shortage_analyze-init/analyze_shortage.py
```

## 先阅读的文件

```text
shortage_analyze-opt/README.md
shortage_analyze-opt/HARNESS_GUIDE.md
shortage_analyze-opt/train/configs/default.yaml
shortage_analyze-opt/train/train_shortage_analyze.py
shortage_analyze-opt/train/shortage_analyze_skillopt/harness_chat.py
shortage_analyze-opt/train/shortage_analyze_skillopt/adapter.py
shortage_analyze-opt/train/shortage_analyze_skillopt/rollout.py
shortage_analyze-opt/train/shortage_analyze_skillopt/dataloader.py
shortage_analyze-opt/train/shortage_analyze_skillopt/evaluator.py
shortage_analyze-opt/shortage_analyze-init/initial_skill.md
shortage_analyze-opt/shortage_analyze-init/analyze_shortage.py
```

重点确认：

- `dataloader.py` 不允许训练流程读取带标签 test split。
- `adapter.py` 会拒绝训练配置中的 `env.data_path` 和 `evaluation.eval_test=true`。
- `rollout.py` 使用 `generated_script` 机制执行预测。
- 初始脚本和候选脚本都应提供 `predict_labels(features)` 和 `format_prediction(labels)`。

## 接手前检查

新 harness 接手后，先检查现成产物：

```powershell
Test-Path .\shortage_analyze-opt\processed\shortage_analyze_split\train\items.json
Test-Path .\shortage_analyze-opt\processed\shortage_analyze_split\val\items.json
Test-Path .\shortage_analyze-opt\processed\shortage_analyze_split\test\items.json
Test-Path .\shortage_analyze-opt\shortage_analyze-init\initial_skill.md
Test-Path .\shortage_analyze-opt\shortage_analyze-init\analyze_shortage.py
```

如果以上结果都为 `True`，直接跳到“运行优化”。不要重复执行 `prepare_skillopt_data.py` 或 `build_initial_skill.py`。

只有在 processed split 缺失时，才执行数据处理；只有 `shortage_analyze-init` 缺失或用户明确要求重建时，才构建初始 SkillOpt skill。

## 当前目录约定

```text
shortage_analyze-opt/
  shortage_analyze/                  # 原始 skill，不修改，不作为训练输入
  shortage_analyze-init/             # 处理后的初始 SkillOpt skill
    initial_skill.md
    analyze_shortage.py
  shortage_analyze-optimized/        # 训练后导出的优化产物
    best/
      best_kill.md
      scripts/analyze_shortage.py
  process/                           # 可读取原始数据的预处理/评估/导出脚本
  processed/                         # 已处理 split 和评估输出
  train/                             # SkillOpt 训练入口和 adapter
```

## 数据处理

如果 processed split 尚未生成，才运行：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/process/prepare_skillopt_data.py
```

默认读取：

```text
D:\code\github\hehe03\data.xlsx
```

默认输出：

```text
shortage_analyze-opt/processed/shortage_analyze_split/
  train/items.json
  val/items.json
  test/items.json
  split_manifest.json
```

`test/items.json` 在默认训练配置中不带可用于优化的测试标签。

## 构建初始 SkillOpt skill

如果 `shortage_analyze-init/initial_skill.md` 或 `shortage_analyze-init/analyze_shortage.py` 不存在，或用户明确要求重建，才运行：

```powershell
conda run -n llm python shortage_analyze-opt/process/build_initial_skill.py
```

该脚本属于 process 阶段，会读取：

```text
shortage_analyze-opt/shortage_analyze/SKILL.md
shortage_analyze-opt/shortage_analyze/references/rules.md
```

输出：

```text
shortage_analyze-opt/shortage_analyze-init/initial_skill.md
```

注意：训练阶段不再读取 `shortage_analyze-opt/shortage_analyze`。

## 使用 Agent 自带模型

默认配置使用：

```yaml
model:
  backend: agent_harness
  optimizer: harness-default
  target: harness-default
  optimizer_backend: agent_harness
  target_backend: agent_harness
```

含义：

- `agent_harness` 表示 LLM 调用交给当前 Agent/harness，而不是 OpenAI、Azure 或固定 Codex 后端。
- `harness-default` 表示使用当前 harness 默认模型。
- `train_shortage_analyze.py` 会在运行时把这些占位值转换为 SkillOpt 内部兼容字段，并用 `run_agent_chat(...)` 接管实际 LLM 调用。
- 新 harness 不需要因为配置中出现 SkillOpt 内部兼容值而额外配置 LLM key。

统一入口：

```text
shortage_analyze-opt/train/shortage_analyze_skillopt/harness_chat.py
run_agent_chat(...)
```

自动路由顺序：

1. 如果配置了 `SHORTAGE_ANALYZE_AGENT_COMMAND_JSON` 或 `SHORTAGE_ANALYZE_AGENT_COMMAND`，使用自定义 harness 命令。
2. 如果 `SHORTAGE_ANALYZE_AGENT_BACKEND=nga`，使用 Nga CLI。
3. 如果 `SHORTAGE_ANALYZE_AGENT_BACKEND=opencode`，使用 opencode CLI。
4. 如果 `SHORTAGE_ANALYZE_AGENT_BACKEND=codex`，使用 Codex CLI。
5. 如果未设置或为 `auto`，依次检测 Nga、opencode、Codex。
6. 如果都不可用，直接报错并提示配置方式，不应卡在 Codex CLI。

### Nga

项目内置的 Nga 调用协议来自 `shortage_analyze-opt/train/harness_chat_test.py`：

```text
nga run <instruction> --file <absolute_prompt_path>
```

完整 prompt 写入 `<out_root>/llm-files/prompt_nga_<stage>_step_<n>.md`，Nga 从该文件读取请求并将回答输出到 `stdout`；训练流程再把回答保存到配对的 `response_nga_<stage>_step_<n>.txt`。

使用 Nga：

```powershell
$env:SHORTAGE_ANALYZE_AGENT_BACKEND = "nga"
```

如果 Nga 不在 PATH，可显式指定：

```powershell
$env:NGA_CLI_BIN = "C:\Users\<user>\OCHOME\nga.cmd"
```

代码也会自动检测 `$env:OCHOME`、`~/OCHOME/nga.cmd`、`nga.cmd`、`nga.exe` 和 `nga`。Nga 的工作目录默认固定为当前项目根目录，可通过 `SHORTAGE_ANALYZE_NGA_RUN_DIR` 覆盖。

### opencode

```powershell
$env:SHORTAGE_ANALYZE_AGENT_BACKEND = "opencode"
```

如果 opencode 不在 PATH：

```powershell
$env:OPENCODE_CLI_BIN = "C:\path\to\opencode.cmd"
```

Windows 下会优先检测 `opencode.cmd`，然后是 `opencode.exe` 和 `opencode`。

### 自定义 harness 命令

推荐 JSON 命令数组：

```powershell
$env:SHORTAGE_ANALYZE_AGENT_COMMAND_JSON = '["<harness-cli>", "<subcommand>", "--model", "{model}", "--prompt-file", "{prompt_file}", "--output-file", "{output_file}"]'
```

备选 shell 模板：

```powershell
$env:SHORTAGE_ANALYZE_AGENT_COMMAND = '<harness-cli> <subcommand> --model "{model}" --prompt-file "{prompt_file}" --output-file "{output_file}"'
```

可用占位符：

- `{prompt_file}`：包含完整 prompt 的 UTF-8 文本文件。
- `{output_file}`：harness 应写入最终回答的 UTF-8 文本文件。
- `{model}`：当前配置中的模型名，默认是 `harness-default`。
- `{stage}`：调用阶段，例如 `optimizer`、`target`、`script_codegen`。
- `{cwd}`：建议工作目录。

自定义 harness 默认必须使用文件协议，即命令中应包含 `{prompt_file}`。如果某个 harness 确实只能从 stdin 读取 prompt，需要显式设置：

```powershell
$env:SHORTAGE_ANALYZE_AGENT_USE_STDIN = "1"
```

这只是兼容兜底，不推荐作为默认方式。Codex 分支保持其原生 stdin 输入和 `--output-last-message` 输出方式不变。

## 运行优化

默认情况下不需要指定 `out_root`。训练入口会在开始优化时自动生成：

```text
shortage_analyze-opt/train/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>
```

其中 `shortage_analyze` 来自待优化 skill 的名称，时间戳来自启动训练的时间。

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py `
  --config shortage_analyze-opt/train/configs/default.yaml
```

如果需要手动覆盖输出目录，才额外指定 `env.out_root`：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py `
  --config shortage_analyze-opt/train/configs/default.yaml `
  --cfg-options env.out_root=shortage_analyze-opt/train/outputs/shortage_analyze_<harness_name>_v1
```

每个 run 的文件协议记录都放在：

```text
<out_root>/llm-files/
```

除 Codex 外，Nga、opencode 和自定义 harness 的 prompt/response 文件都会写到这里。每次 LLM 调用都会生成新的文件，文件名包含 `step_0001`、`step_0002` 等递增后缀，例如：

```text
prompt_optimizer_step_0001.md
response_optimizer_step_0001.txt
prompt_nga_script_codegen_step_0002.md
response_nga_script_codegen_step_0002.txt
prompt_opencode_script_codegen_step_0002.md
response_opencode_script_codegen_step_0002.txt
```

短实验可以覆盖 epoch 或 batch 配置。如果要手动停在某一步，必须等该 step 写入 `history.json` 后再停止训练进程。

## target 执行机制

训练期间 target 预测流程：

1. 初始 skill 使用：

```text
shortage_analyze-opt/shortage_analyze-init/analyze_shortage.py
```

2. 每个候选 skill 根据 skill 内容计算 hash。
3. 如果该 hash 没有缓存脚本，则调用当前 Agent harness 生成：

```text
<out_root>/generated_scripts/<skill_hash>/analyze_shortage.py
```

4. 训练样本预测通过脚本执行：

```python
predict_labels(features)
format_prediction(labels)
```

5. 预测结果写入 rollout 目录，供 SkillOpt 反思和 gate 使用。

判断机制是否生效，可以看 `results.jsonl` 中是否包含：

```json
{
  "executor": "generated_script",
  "script_path": "..."
}
```

如果看到逐样本 LLM 对话或每条样本都调用模型，说明机制被破坏，应先修复再继续训练。

## 查看进度

假设输出目录是：

```text
shortage_analyze-opt/train/outputs/shortage_analyze_20260603_153000
```

查看完成到第几步：

```powershell
Get-Content .\shortage_analyze-opt\train\outputs\shortage_analyze_20260603_153000\runtime_state.json -Encoding UTF8
```

查看每步结果：

```powershell
Get-Content .\shortage_analyze-opt\train\outputs\shortage_analyze_20260603_153000\history.json -Encoding UTF8
```

重点字段：

- `rollout_hard`：当前 batch 上当前 skill 的样本级 accuracy。
- `n_patches`：本步反思得到的 patch 数。
- `candidate_hash`：候选 skill hash，也是候选脚本缓存目录名。
- `selection_hard`：候选 skill 在 selection set 上的 accuracy。
- `action`：`accept`、`reject` 或 `skip_no_patches`。
- `best_score`：当前最优 selection accuracy。
- `best_step`：当前最优 skill 来自哪一步。

检查是否结束：

```powershell
Test-Path .\shortage_analyze-opt\train\outputs\shortage_analyze_20260603_153000\summary.json
```

`summary.json` 存在且训练进程已退出，表示完整 run 结束。

## 导出优化结果

训练结束后：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py `
  --skillopt-output shortage_analyze-opt/train/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>
```

默认输出：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/best_kill.md
shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

如果只想复制 best skill，不生成脚本：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py `
  --skillopt-output shortage_analyze-opt/train/outputs/shortage_analyze_<YYYYMMDD_HHMMSS> `
  --script-mode skip
```

## 比较测试集准确率

测试集标签来自原始全量数据，比较动作属于 process 阶段。训练完成并导出 best 脚本后运行：

```powershell
conda run -n llm python shortage_analyze-opt/process/compare_test_accuracy.py
```

默认比较：

```text
优化前：shortage_analyze-opt/shortage_analyze/scripts/analyze_shortage.py
优化后：shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

输出：

```text
shortage_analyze-opt/processed/eval/test_accuracy_compare.json
```

## 推荐给新 harness 的启动提示

```text
请在 D:\code\github\hehe03\SkillOpt 仓库中继续优化 shortage_analyze。

开始前请完整阅读：
- shortage_analyze-opt/HARNESS_GUIDE.md
- shortage_analyze-opt/README.md
- shortage_analyze-opt/train/configs/default.yaml
- shortage_analyze-opt/train/shortage_analyze_skillopt/harness_chat.py
- shortage_analyze-opt/train/shortage_analyze_skillopt/adapter.py
- shortage_analyze-opt/train/shortage_analyze_skillopt/rollout.py

要求：
1. 不要修改 shortage_analyze-opt/shortage_analyze。
2. 训练从 shortage_analyze-opt/shortage_analyze-init/initial_skill.md 开始。
3. 如果 processed/shortage_analyze_split 和 shortage_analyze-init 已存在，不要重复执行数据处理或初始 skill 构建，直接开始优化。
4. 训练流程不能读取 data.xlsx、原始全量数据、测试集标签、shortage_analyze/references 或 shortage_analyze/scripts。
5. 使用 SkillOpt 优化。
6. 使用当前 harness 自带大模型，不额外配置 LLM key。所有训练中的 LLM 调用必须经过 train/shortage_analyze_skillopt/harness_chat.py 的 run_agent_chat(...)。
7. target 执行必须先生成或复用 Python 规则脚本，再用脚本预测；不要逐样本调用 LLM。
8. 默认使用自动生成的 out_root：shortage_analyze-opt/train/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>。
9. 非 Codex harness 默认使用文件协议；prompt/response 文件保存在 <out_root>/llm-files，文件名带 step 后缀。
10. 运行中报告每步 rollout_hard、selection_hard、action、best_score、best_step。
```
