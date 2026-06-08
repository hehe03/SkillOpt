# opt-in-harness

`opt-in-harness` 用于在 Agent harness 中运行 SkillOpt 优化。这里的 harness 指 Codex、Nga、opencode 或其它能调用自身大模型的 Agent 环境；优化过程不需要在项目中额外配置 LLM API key。

本目录面向多个待优化 skill。每个 skill 放在 `workspace/<skill_name>/` 下，自己管理配置、标准 split 数据、初始 skill、训练适配层和输出。

## 目录结构

```text
opt-in-harness/
  README.md                    # 本总览
  SKILL_PREP_GUIDE.md          # 新 skill 和数据预处理接入指南
  HARNESS_GUIDE.md             # harness 运行优化指南
  train/
    train_in_harness.py        # 通用 SkillOpt 入口
    harness_chat.py            # 通用 harness 调用层
    split_items_loader.py      # 标准 split/items.json loader
  workspace/
    <skill_name>/
      configs/default.yaml     # 该 skill 的优化配置
      data/                    # 已处理好的 split 数据和训练后评估输出
      init-skill/              # 初始 Skill 文档，以及可选初始执行脚本
      process/                 # 训练前/训练后处理脚本
      train/                   # 该 skill 的 adapter、rollout、evaluator、prompts
      outputs/                 # 每次优化 run 的输出
```

## 两个阶段

1. **准备阶段**

   阅读 [SKILL_PREP_GUIDE.md](D:/code/github/hehe03/SkillOpt/opt-in-harness/SKILL_PREP_GUIDE.md)，把新 skill 和原始数据整理成 `workspace/<skill_name>/` 下的待优化状态。

2. **优化阶段**

   阅读 [HARNESS_GUIDE.md](D:/code/github/hehe03/SkillOpt/opt-in-harness/HARNESS_GUIDE.md)，使用当前 Agent harness 自带大模型运行 SkillOpt。

## 标准数据格式

默认训练入口消费已经处理好的 split：

```text
workspace/<skill_name>/data/<split_name>/
  train/items.json
  val/items.json
  test/items.json
```

每个 `items.json` 是 JSON 数组。建议每条样本包含：

```json
{
  "id": "sample_001",
  "features": {
    "任意业务字段": "..."
  },
  "ground_truth": "训练或验证标签",
  "task_type": "可选子任务名"
}
```

不同 skill 的业务字段可以完全不同，统一之处只是 split 目录和少数字段约定。标准格式可直接复用 `opt-in-harness/train/split_items_loader.py`。

## 运行入口

准备完成后，优化命令统一为：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"

conda run -n llm python opt-in-harness/train/train_in_harness.py `
  --config opt-in-harness/workspace/<skill_name>/configs/default.yaml
```

没有显式指定 `env.out_root` 时，输出目录为：

```text
opt-in-harness/workspace/<skill_name>/outputs/<skill_name>_<YYYYMMDD_HHMMSS>/
```

典型输出包括：

```text
llm-files/              # harness prompt/response
generated_scripts/      # 可选，若该 skill 使用脚本化 rollout
steps/                  # 每步中间结果
best_skill.md           # 当前 run 的最佳 skill
history.json            # step 历史
runtime_state.json      # 运行状态
summary.json            # 训练总结
```

判断一次 run 是否结束：

```powershell
Test-Path .\opt-in-harness\workspace\<skill_name>\outputs\<run>\summary.json
```
