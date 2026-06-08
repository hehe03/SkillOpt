# opt-in-harness

`opt-in-harness` 用于在 Agent harness 中运行 SkillOpt 优化。这里的“harness”指 Codex、Nga、opencode 或其它能调用自身大模型的 Agent 环境；优化过程不需要在项目中额外配置 LLM API key。

本目录不再只服务 `shortage_analyze`。多个待优化 skill 放在 `workspace/` 下，每个 skill 自己管理配置、数据、初始 skill 和训练输出。目前已接入训练流程的是 `workspace/shortage_analyze`。

## 目录结构

```text
opt-in-harness/
  train/                       # 通用 SkillOpt 训练入口、harness 调用和标准 split loader
  workspace/README.md          # 新 skill 接入规范
  workspace/
    shortage_analyze/
      configs/default.yaml     # shortage_analyze 优化配置
      data/                    # 已处理好的 split 数据和离线评估输出
      init-skill/              # 初始 SkillOpt skill 和初始规则脚本
      outputs/                 # 每次训练 run 的输出
      process/                 # shortage_analyze 专属的训练前/训练后处理脚本
      train/                   # shortage_analyze 专属 adapter、rollout 和评估逻辑
      README.md                # shortage_analyze workspace 说明
    tracesorter-rules/         # 暂不接入本训练入口
    tracesorter-skill/         # 暂不接入本训练入口
```

## shortage_analyze 当前约定

优化前默认已经完成数据处理和 split 构建。训练入口直接读取：

```text
opt-in-harness/workspace/shortage_analyze/configs/default.yaml
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/
opt-in-harness/workspace/shortage_analyze/init-skill/initial_skill.md
opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
opt-in-harness/workspace/shortage_analyze/train/adapter.py
opt-in-harness/workspace/shortage_analyze/train/evaluator.py
opt-in-harness/workspace/shortage_analyze/train/rollout.py
```

如果下面文件已经存在，就不需要重复执行数据处理或初始 skill 构建：

```text
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/train/items.json
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/val/items.json
opt-in-harness/workspace/shortage_analyze/data/shortage_analyze_split/test/items.json
opt-in-harness/workspace/shortage_analyze/init-skill/initial_skill.md
opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
```

## 运行优化

推荐在 `llm` 环境中运行：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"
$env:NGA_CLI_BIN = "C:\Users\<user>\OCHOME\nga.cmd"

conda run -n llm python opt-in-harness/train/train_in_harness.py `
  --config opt-in-harness/workspace/shortage_analyze/configs/default.yaml
```

没有显式指定 `env.out_root` 时，训练入口会自动创建：

```text
opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>/
```

其中：

- `llm-files/` 保存每次 harness 调用的 prompt 和 response。
- `generated_scripts/` 保存由当前 skill 生成的快速预测脚本。
- `steps/`、`history.json`、`summary.json` 等文件由 SkillOpt 训练过程生成。
- `best_skill.md` 是 SkillOpt 当前 run 内部选出的最佳 skill。

## 训练后导出

训练结束后，可将某次 run 的 `best_skill.md` 导出为优化后的 skill，并用 harness 生成对应脚本：

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/finalize_optimized_skill.py `
  --skillopt-output opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>
```

默认导出到：

```text
opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/best_kill.md
opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/scripts/analyze_shortage.py
```

## 测试集比较

测试集比较在训练后单独运行：

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/compare_test_accuracy.py
```

默认比较：

```text
优化前：opt-in-harness/workspace/shortage_analyze/init-skill/analyze_shortage.py
优化后：opt-in-harness/workspace/shortage_analyze/outputs/optimized/best/scripts/analyze_shortage.py
```

默认输出：

```text
opt-in-harness/workspace/shortage_analyze/data/eval/test_accuracy_compare.json
```

## 给新 harness

如果要让新的 Agent harness 接手，请先让它阅读：

```text
opt-in-harness/HARNESS_GUIDE.md
```
