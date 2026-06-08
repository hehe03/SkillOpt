# shortage_analyze workspace

本 workspace 是 `shortage_analyze` 的 SkillOpt 优化工程。公共训练入口在 `opt-in-harness/train/`，本目录只保存该 skill 的配置、数据、初始 skill、训练期适配层、训练前后处理脚本和输出。

## 目录职责

```text
shortage_analyze/
  configs/default.yaml              # SkillOpt 配置，声明 adapter_module/adapter_class
  data/shortage_analyze_split/      # 已处理好的 train/val/test split
  init-skill/
    initial_skill.md                # 已融合原始规则的初始 Skill 文档
    analyze_shortage.py             # 初始规则对应的快速预测脚本
  process/
    prepare_skillopt_data.py        # 读取原始 Excel，生成 split 数据
    build_initial_skill.py          # 从规则文本构建 initial_skill.md
    finalize_optimized_skill.py     # 导出 best skill，并生成最终预测脚本
    compare_test_accuracy.py        # 训练后比较优化前后测试集准确率
  train/
    adapter.py                      # SkillOpt EnvAdapter
    evaluator.py                    # 多标签评估和错误明细
    rollout.py                      # 当前 Skill -> Python 脚本 -> 批量预测
    tests/                          # 局部测试；harness_chat_test.py 是文件协议 demo
  outputs/                          # 每次训练 run 和最终导出结果
```

## 训练输入

优化前默认已经完成数据处理和 split 构建。训练入口直接读取：

```text
configs/default.yaml
data/shortage_analyze_split/train/items.json
data/shortage_analyze_split/val/items.json
init-skill/initial_skill.md
init-skill/analyze_shortage.py
train/adapter.py
train/evaluator.py
train/rollout.py
```

## 运行顺序

已有 split 数据和初始 skill 时，直接运行优化：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPT_IN_HARNESS_AGENT_BACKEND = "nga"

conda run -n llm python opt-in-harness/train/train_in_harness.py `
  --config opt-in-harness/workspace/shortage_analyze/configs/default.yaml
```

训练结束后导出最终 skill：

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/finalize_optimized_skill.py `
  --skillopt-output opt-in-harness/workspace/shortage_analyze/outputs/shortage_analyze_<YYYYMMDD_HHMMSS>
```

训练后比较测试集准确率：

```powershell
conda run -n llm python opt-in-harness/workspace/shortage_analyze/process/compare_test_accuracy.py
```

## 应用到新 skill 时的可复用点

`shortage_analyze/train/adapter.py`、`evaluator.py` 和 `rollout.py` 可以作为新 skill 的参考，但不建议直接放到公共 `opt-in-harness/train/`。新 skill 应在自己的 `workspace/<skill_name>/train/` 下实现同名职责，并在配置中通过 `env.adapter_module` 指向自己的 adapter。

`shortage_analyze` 的 split 是标准 `items.json` 格式，因此 dataloader 已复用公共 `opt-in-harness/train/split_items_loader.py`。

`train/tests/harness_chat_test.py` 不是训练流程依赖项，只是验证 Nga 文件协议的示例。新 skill 不需要复制它，除非也想保留一个本地 harness smoke test。
