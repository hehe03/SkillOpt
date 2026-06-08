# 新 harness 接手指南

本文档面向 Codex、Nga、opencode 或其它 Agent harness。读完后，应能在 `opt-in-harness` 新结构下继续运行 SkillOpt 优化。

## 总体目标

使用当前 Agent harness 自带的大模型运行 SkillOpt，不在本项目中额外配置 LLM。当前已接入训练流程的 workspace 是：

```text
opt-in-harness/workspace/shortage_analyze/
```

其它 workspace，例如 `tracesorter-rules` 和 `tracesorter-skill`，暂时不要改动。

## 关键约束

1. `opt-in-harness/train` 只放通用训练入口和 harness 调用代码。
2. `opt-in-harness/train` 不放具体业务数据处理脚本，也不放具体 skill 的 adapter、rollout 或 evaluator。
3. `opt-in-harness/workspace/<skill>` 放待优化 skill 的配置、数据、初始 skill、输出、`process/` 和 `train/` 适配层。
4. 优化前默认已经完成数据处理和 split 构建。
5. 训练阶段使用 `data/shortage_analyze_split` 中的数据，以及 `init-skill` 中的初始 skill 和初始脚本。
6. 测试集比较在训练结束后由 `workspace/shortage_analyze/process/compare_test_accuracy.py` 单独运行。

## shortage_analyze 路径

必须存在：

```text
opt-in-harness/workspace/shortage_analyze/configs/default.yaml
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/train/items.json
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/val/items.json
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/test/items.json
opt-in-harness/workspace/shortage_analyze/init-skill/initial_skill.md
opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
opt-in-harness/workspace/shortage_analyze/train/adapter.py
opt-in-harness/workspace/shortage_analyze/train/evaluator.py
opt-in-harness/workspace/shortage_analyze/train/rollout.py
```

如果这些文件已存在，直接开始优化，不要重复执行数据处理或初始 skill 构建。

配置中的关键路径应为：

```yaml
env:
  name: shortage_analyze
  workspace_root: opt-in-harness/workspace/shortage_analyze
  adapter_module: opt-in-harness/workspace/shortage_analyze/train/adapter.py
  adapter_class: ShortageAnalyzeAdapter
  skill_init: opt-in-harness/workspace/shortage_analyze/init-skill/initial_skill.md
  split_mode: split_dir
  split_dir: opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split
  data_path: ""
  out_root: ""
  initial_skill_path: opt-in-harness/workspace/shortage_analyze/init-skill/initial_skill.md
  initial_script_path: opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
```

`env.data_path` 必须保持为空。`env.out_root` 通常也保持为空，由训练入口自动生成。

## Harness 调用

统一入口：

```text
opt-in-harness/train/harness_chat.py
run_agent_chat(...)
```

路由顺序：

1. 如果配置了 `OPT_IN_HARNESS_AGENT_COMMAND_JSON` 或 `OPT_IN_HARNESS_AGENT_COMMAND`，使用自定义 harness 命令。
2. 如果 `OPT_IN_HARNESS_AGENT_BACKEND=nga`，使用 Nga CLI。
3. 如果 `OPT_IN_HARNESS_AGENT_BACKEND=opencode`，使用 opencode CLI。
4. 如果 `OPT_IN_HARNESS_AGENT_BACKEND=codex`，使用 Codex CLI。
5. 如果未设置或为 `auto`，依次检测 Nga、opencode、Codex。
6. 如果都不可用，直接报错。

### Nga

Nga 调用协议：

```text
nga run <instruction> --file <absolute_prompt_path>
```

使用 Nga：

```powershell
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"
$env:NGA_CLI_BIN = "C:\Users\<user>\OCHOME\nga.cmd"
```

训练过程会把完整 prompt 写入：

```text
<out_root>/llm-files/prompt_nga_<stage>_step_<n>.md
```

Nga 从 `--file` 指向的文件读取 prompt，响应从 `stdout` 获取，并保存为：

```text
<out_root>/llm-files/response_nga_<stage>_step_<n>.txt
```

### Codex

Codex 分支使用 stdin 传入完整 prompt，并通过 `--output-last-message` 获取最终回答。无需文件附件。

### opencode

opencode 分支仍保留兼容，但如果当前代理不允许文件上传，`opencode run --file` 可能出现 `proxy_uploadNotAllowed`。遇到这种情况，建议切换到 Nga 或自定义 harness 命令。

### 自定义 harness

推荐配置 JSON 命令数组：

```powershell
$env:OPT_IN_HARNESS_AGENT_COMMAND_JSON = '["<harness-cli>", "<subcommand>", "--prompt-file", "{prompt_file}", "--output-file", "{output_file}"]'
```

可用占位符：

- `{prompt_file}`：完整 prompt 文件。
- `{output_file}`：harness 应写入最终回答的文件。
- `{model}`：模型名，默认 `harness-default`。
- `{stage}`：调用阶段，例如 `optimizer`、`target`、`script_codegen`。
- `{cwd}`：建议工作目录。

## 运行优化

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"
$env:NGA_CLI_BIN = "C:\Users\<user>\OCHOME\nga.cmd"

conda run -n llm python opt-in-harness/train/train_in_harness.py `
  --config opt-in-harness/workspace/shortage_analyze/configs/default.yaml
```

默认输出目录：

```text
opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>/
```

每次 LLM 调用都写入该 run 下的 `llm-files/`，文件名带 `step_0001`、`step_0002` 等后缀。

## 训练如何执行目标 skill

`shortage_analyze` 目标执行不用 LLM 逐条阅读样本。流程是：

1. 初始 skill 使用 `init-skill/analyze_shortage.py`。
2. 每轮 SkillOpt 产生新 skill 后，训练流程先让 harness 把新规则文档生成 Python 脚本。
3. 之后用生成脚本对训练样本快速预测。
4. 预测结果和标签比较后进入 reflect 阶段。

生成脚本缓存位于：

```text
<out_root>/generated_scripts/
```

## 训练输出

典型 run 目录包含：

```text
llm-files/              # harness prompt/response
generated_scripts/      # 当前 skill 转换出的预测脚本
steps/                  # 每步中间结果
best_skill.md           # 当前 run 的最佳 skill
history.json            # step 历史
runtime_state.json      # 运行状态
summary.json            # 总结
```

判断是否结束：

```powershell
Test-Path .\opt-in-harness\workspace\shortage_analyze\outputs\<run>\summary.json
```

如果只想看前两步，可以读取 `history.json` 中前两个 step 的 accuracy、skill 路径和输出目录。

## 训练后导出

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/finalize_optimized_skill.py `
  --skillopt-output opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>
```

默认导出：

```text
opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/best_kill.md
opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/scripts/analyze_shortage.py
```

## 训练后测试集比较

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/compare_test_accuracy.py
```

默认读取：

```text
测试样本：opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/test/items.json
优化前脚本：opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
优化后脚本：opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/scripts/analyze_shortage.py
```

默认输出：

```text
opt-in-harness/workspace/shortage_analyze/data/eval/test_accuracy_compare.json
```

## 给新 harness 的最短提示

```text
本仓库是 Microsoft SkillOpt。请使用 opt-in-harness 中的流程优化 workspace/shortage_analyze。
先阅读 opt-in-harness/HARNESS_GUIDE.md 和 opt-in-harness/README.md。
优化前数据已处理为 split；训练使用 workspace/shortage_analyze/data/shortage_analyze_split 和 init-skill。
使用 harness 自带大模型，优先设置 OPT_IN_HARNESS_AGENT_BACKEND=nga。
运行入口是 opt-in-harness/train/train_in_harness.py。
配置文件是 opt-in-harness/workspace/shortage_analyze/configs/default.yaml。
训练输出放在 opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<time>。
```
