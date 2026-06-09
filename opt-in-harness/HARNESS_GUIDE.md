# harness 优化运行指南

本文档面向 Codex、Nga、opencode 或其它 Agent harness。它只说明如何在已经准备好的 `workspace/<skill_name>/` 上运行 SkillOpt 优化；新 skill 和数据如何准备，请先阅读 `opt-in-harness/SKILL_PREP_GUIDE.md`。

## 前提

待优化 workspace 已经包含：

```text
opt-in-harness/workspace/<skill_name>/configs/default.yaml
opt-in-harness/workspace/<skill_name>/data/<split_name>/train/items.json
opt-in-harness/workspace/<skill_name>/data/<split_name>/val/items.json
opt-in-harness/workspace/<skill_name>/init-skill/initial_skill.md
opt-in-harness/workspace/<skill_name>/train/adapter.py
opt-in-harness/workspace/<skill_name>/train/evaluator.py
opt-in-harness/workspace/<skill_name>/train/rollout.py
```

如果该 skill 使用脚本化 rollout，还应有：

```text
opt-in-harness/workspace/<skill_name>/init-skill/<initial_executor>.py
opt-in-harness/workspace/<skill_name>/train/prompts/script_codegen.md
```

配置中的关键字段为：

```yaml
env:
  name: <skill_name>
  workspace_root: opt-in-harness/workspace/<skill_name>
  adapter_module: opt-in-harness/workspace/<skill_name>/train/adapter.py
  adapter_class: <AdapterClassName>
  skill_init: opt-in-harness/workspace/<skill_name>/init-skill/initial_skill.md
  split_mode: split_dir
  split_dir: opt-in-harness/workspace/<skill_name>/data/<split_name>
  data_path: ""
  out_root: ""
  agent_backend: nga   # 可选：指定使用 custom_model / nga / opencode / codex
```

`env.out_root` 通常保持为空，由训练入口自动生成时间戳目录。
`env.agent_backend` 可直接在配置中指定 harness 后端；如果未填写，则可通过环境变量 `OPT_IN_HARNESS_AGENT_BACKEND` 指定，或由入口自动检测。

## harness 调用入口

通用调用函数位于：

```text
opt-in-harness/train/harness_chat.py
run_agent_chat(...)
```

路由顺序：

1. 如果配置了 `OPT_IN_HARNESS_AGENT_COMMAND_JSON` 或 `OPT_IN_HARNESS_AGENT_COMMAND`，使用自定义 harness 命令。
2. 如果配置文件中写了 `env.agent_backend: custom_model`，或环境变量 `OPT_IN_HARNESS_AGENT_BACKEND=custom_model`，使用本地 Python 自定义模型函数。
3. 如果配置文件中写了 `env.agent_backend: nga`，或环境变量 `OPT_IN_HARNESS_AGENT_BACKEND=nga`，使用 Nga CLI。
4. 如果配置文件中写了 `env.agent_backend: opencode`，或环境变量 `OPT_IN_HARNESS_AGENT_BACKEND=opencode`，使用 opencode CLI。
5. 如果配置文件中写了 `env.agent_backend: codex`，或环境变量 `OPT_IN_HARNESS_AGENT_BACKEND=codex`，使用 Codex CLI。
6. 如果未设置或为 `auto`，依次检测 Nga、opencode、Codex。
7. 如果都不可用，直接报错。

### 自定义 Python 模型

如果希望直接在代码中接入自己的模型，可在配置中指定：

```yaml
env:
  agent_backend: custom_model
```

默认会调用：

```text
opt-in-harness/train/custom_model.py
call_custom_model(prompt: str) -> str
```

该函数收到的是 harness 已经装配完成的完整 prompt，返回值必须是模型最终文本响应。默认函数体为空，需要自行填入真实模型调用。

也可以指定其它模块或函数：

```yaml
env:
  agent_backend: custom_model
  custom_model_module: path/to/my_model.py
  custom_model_function: call_custom_model
```

### Nga

推荐直接在 workspace 配置中指定：

```yaml
env:
  agent_backend: nga
```

也可以用 PowerShell 环境变量临时覆盖：

```powershell
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"
$env:NGA_CLI_BIN = "C:\Users\<user>\OCHOME\nga.cmd"
```

如果 Nga 已在 `PATH`、`OCHOME` 或默认 `~/OCHOME` 中，可不设置 `NGA_CLI_BIN`。

调用协议：

```text
nga run <instruction> --file <absolute_prompt_path>
```

训练过程会把完整 prompt 写入：

```text
<out_root>/llm-files/prompt_nga_<stage>_step_<n>.md
```

响应从 `stdout` 获取，并保存为：

```text
<out_root>/llm-files/response_nga_<stage>_step_<n>.txt
```

### Codex

Codex 分支使用 stdin 传入完整 prompt，并通过 `--output-last-message` 获取最终回答。无需文件附件。

### opencode

opencode 分支保留兼容。如果当前代理不允许文件上传，`opencode run --file` 可能出现 `proxy_uploadNotAllowed`，这时建议切换到 Nga 或自定义 harness 命令。

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
conda run --no-capture-output -n llm python opt-in-harness/train/train_in_harness.py `
  --config opt-in-harness/workspace/<skill_name>/configs/default.yaml
```

`train_in_harness.py` 会自动设置 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`，通常不需要在命令行里手动 export 或设置 `$env:`。

如果配置文件没有写 `env.agent_backend`，也可以在运行前临时指定：

```powershell
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"
```

默认输出目录：

```text
opt-in-harness/workspace/<skill_name>/outputs/<skill_name>_<YYYYMMDD_HHMMSS>/
```

每次 LLM 调用都会写入该 run 下的 `llm-files/`，文件名带 `step_0001`、`step_0002` 等后缀。

## 训练输出

典型 run 目录包含：

```text
llm-files/              # harness prompt/response
generated_scripts/      # 可选，当前 skill 转换出的预测脚本
steps/                  # 每步中间结果
best_skill.md           # 当前 run 的最佳 skill
history.json            # step 历史
runtime_state.json      # 运行状态
summary.json            # 总结
```

判断是否结束：

```powershell
Test-Path .\opt-in-harness\workspace\<skill_name>\outputs\<run>\summary.json
```

## 给新 harness 的最短提示

```text
本仓库是 Microsoft SkillOpt。请使用 opt-in-harness 中的通用流程优化指定 workspace。
先阅读 opt-in-harness/HARNESS_GUIDE.md；如果 workspace 尚未准备好，先阅读 opt-in-harness/SKILL_PREP_GUIDE.md。
使用 harness 自带大模型，优先设置 OPT_IN_HARNESS_AGENT_BACKEND=nga。
也可以在配置文件中设置 env.agent_backend: nga。
运行入口是 opt-in-harness/train/train_in_harness.py。
配置文件是 opt-in-harness/workspace/<skill_name>/configs/default.yaml。
训练输出放在 opt-in-harness/workspace/<skill_name>/outputs/<skill_name>_<time>。
```
