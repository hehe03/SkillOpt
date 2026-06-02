# 新 harness 接手指南

本文档面向新的 Agent harness（例如 Codex、opencode 或其它支持调用自身大模型的 Agent）。目标是让新 harness 读完后知道如何使用本目录中的脚本继续优化 `shortage_analyze`，并避免误读原始数据或测试集标签。

## 任务目标

使用 SkillOpt 优化原始 skill：

```text
shortage_analyze-opt/shortage_analyze
```

原始 skill 是基于规则的多标签分类任务。每个样本可能命中多个 L2 标签，例如：

```text
用量异常、基线异常、补库供应不及时
```

训练 gate 的主指标仍是样本级 accuracy：预测标签集合必须与 gold 标签集合完全一致才算正确。优化反思阶段会额外使用 `missing_labels`、`extra_labels` 和逐标签 TP/FN/FP 细节，帮助分析单个标签规则。

## 必须遵守的边界

1. 不要修改 `shortage_analyze-opt/shortage_analyze/`。
   这是原始 skill，包含原始 `SKILL.md`、`references/rules.md` 和 `scripts/analyze_shortage.py`。

2. 训练流程不能读取原始 Excel。
   `shortage_analyze-opt/train` 只能读取 `shortage_analyze-opt/processed` 中已经处理好的 split，以及 `shortage_analyze-optimized/init` 中的初始 skill/脚本。

3. 优化过程不能读取测试集标签。
   `train/configs/default.yaml` 中应保持：

```yaml
evaluation:
  eval_test: false

env:
  data_path: ""
  allow_test_labels: false
```

4. 可以读取原始数据的代码只放在 `shortage_analyze-opt/process`。
   数据预处理、训练后测试集准确率比较、最终导出都属于 process 阶段，不属于 train 阶段。

5. 执行 target skill 时不要逐样本调用 LLM。
   当前机制是先生成或复用 Python 规则脚本，再用脚本执行预测。

## 接手后先阅读这些文件

新 harness 开始执行前，先阅读：

```text
shortage_analyze-opt/README.md
shortage_analyze-opt/HARNESS_GUIDE.md
shortage_analyze-opt/train/configs/default.yaml
shortage_analyze-opt/train/train_shortage_analyze.py
shortage_analyze-opt/train/shortage_analyze_skillopt/adapter.py
shortage_analyze-opt/train/shortage_analyze_skillopt/rollout.py
shortage_analyze-opt/train/shortage_analyze_skillopt/dataloader.py
shortage_analyze-opt/train/shortage_analyze_skillopt/evaluator.py
shortage_analyze-opt/shortage_analyze-optimized/init/initial_skill.md
shortage_analyze-opt/shortage_analyze-optimized/init/analyze_shortage.py
```

重点确认：

- `dataloader.py` 不允许训练流程读取带标签 test split。
- `adapter.py` 会拒绝训练配置中的 `env.data_path` 和 `evaluation.eval_test=true`。
- `rollout.py` 使用 `generated_script` 机制执行预测。
- 初始脚本和候选脚本都应提供 `predict_labels(features)` 和 `format_prediction(labels)`。

## 当前目录约定

```text
shortage_analyze-opt/
  shortage_analyze/                  # 原始 skill，不修改
  process/                           # 可读取原始数据的数据处理/评估/导出脚本
  processed/                         # 已处理 split 和评估输出
  train/                             # SkillOpt 训练入口和 adapter
  shortage_analyze-optimized/
    init/
      initial_skill.md               # SkillOpt 初始规则文档
      analyze_shortage.py            # 初始规则对应的快速预测脚本
    best/
      best_kill.md                   # 训练后导出的最优 skill
      scripts/analyze_shortage.py    # 训练后导出的最优规则脚本
```

## 数据处理

如果 processed split 尚未生成，运行：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/process/prepare_skillopt_data.py
```

该脚本默认读取：

```text
D:\code\github\hehe03\data.xlsx
```

并输出：

```text
shortage_analyze-opt/processed/shortage_analyze_split/
  train/items.json
  val/items.json
  test/items.json
  split_manifest.json
```

注意：`test/items.json` 在默认训练配置中不带标签，训练阶段也不会读取 test labels。

## 生成初始 SkillOpt skill

如果 `initial_skill.md` 不存在或需要重建，运行：

```powershell
conda run -n llm python shortage_analyze-opt/process/build_initial_skill.py
```

该脚本只读取：

```text
shortage_analyze-opt/shortage_analyze/SKILL.md
shortage_analyze-opt/shortage_analyze/references/rules.md
```

输出：

```text
shortage_analyze-opt/shortage_analyze-optimized/init/initial_skill.md
```

## 运行优化

正式运行前建议使用新的 `out_root`，不要复用旧目录：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py `
  --config shortage_analyze-opt/train/configs/default.yaml `
  --cfg-options env.out_root=shortage_analyze-opt/train/outputs/shortage_analyze_<harness_name>_v1
```

示例：

```powershell
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py `
  --config shortage_analyze-opt/train/configs/default.yaml `
  --cfg-options env.out_root=shortage_analyze-opt/train/outputs/shortage_analyze_opencode_v1
```

短实验可以覆盖 epoch 或 batch 配置，例如只跑较少 step；如果要手动停在某一步，必须等该 step 已写入 `history.json` 后再停止训练进程。

## Agent 自带模型的使用方式

默认配置使用：

```yaml
model:
  backend: codex
  optimizer_backend: openai_chat
  target_backend: codex_exec
```

在本任务中，“使用 Agent 自带大模型”的含义是：

- SkillOpt 优化器侧的 LLM 调用由当前 Agent/harness 处理。
- target skill 预测阶段不逐样本调用 LLM。
- 只有当某个 skill 版本没有对应 Python 脚本时，才调用当前 Agent/harness 的模型生成一次脚本。

当前 Codex 实现中，相关适配点在：

```text
shortage_analyze-opt/train/shortage_analyze_skillopt/adapter.py
shortage_analyze-opt/train/shortage_analyze_skillopt/rollout.py
```

如果新 harness 不是 Codex，不要改变“先生成脚本，再程序执行预测”的机制；只替换调用 Agent 自身模型的命令适配层。尤其要检查 `rollout.py` 中候选脚本生成逻辑是否仍然能调用当前 harness。

## target 执行机制

训练期间 target 预测流程如下：

1. 初始 skill 使用：

```text
shortage_analyze-opt/shortage_analyze-optimized/init/analyze_shortage.py
```

2. 每个候选 skill 根据 skill 内容计算 hash。

3. 如果该 hash 没有缓存脚本，则调用 Agent 自身模型生成：

```text
<out_root>/generated_scripts/<skill_hash>/analyze_shortage.py
```

4. 训练样本预测通过脚本执行：

```python
predict_labels(features)
format_prediction(labels)
```

5. 预测结果写入 rollout 目录，供 SkillOpt 反思和 gate 使用。

判断机制是否正确生效，可以看 `results.jsonl` 中是否包含：

```json
{
  "executor": "generated_script",
  "script_path": "..."
}
```

如果看到逐样本 LLM 对话或长时间每条样本都调用模型，说明机制被破坏，需要先修复再继续训练。

## 如何查看进度

假设输出目录是：

```text
shortage_analyze-opt/train/outputs/shortage_analyze_opencode_v1
```

查看完成到第几步：

```powershell
Get-Content .\shortage_analyze-opt\train\outputs\shortage_analyze_opencode_v1\runtime_state.json -Encoding UTF8
```

核心字段：

```json
{
  "last_completed_step": 2,
  "current_score": 0.7083333333333334,
  "best_score": 0.7083333333333334,
  "best_step": 0
}
```

查看每步结果：

```powershell
Get-Content .\shortage_analyze-opt\train\outputs\shortage_analyze_opencode_v1\history.json -Encoding UTF8
```

重点字段：

- `rollout_hard`：当前 batch 上当前 skill 的样本级 accuracy。
- `n_patches`：本步反思得到的 patch 数。
- `candidate_hash`：候选 skill 的 hash，也是候选脚本缓存目录名。
- `selection_hard`：候选 skill 在 selection set 上的 accuracy。
- `action`：`accept`、`reject` 或 `skip_no_patches`。
- `best_score`：当前最优 selection accuracy。
- `best_step`：当前最优 skill 来自哪一步。

查看是否结束：

```powershell
Test-Path .\shortage_analyze-opt\train\outputs\shortage_analyze_opencode_v1\summary.json
```

`summary.json` 存在且训练进程已退出，表示完整 run 结束。

查看训练进程：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*shortage_analyze_opencode_v1*' } |
  Select-Object ProcessId,Name,CommandLine
```

## 如何解释结果

完整 run 结束后看：

```text
<out_root>/summary.json
<out_root>/history.json
<out_root>/runtime_state.json
<out_root>/best_skill.md
```

如果某一轮 `selection_hard` 低于当前 `current_score`，SkillOpt 会 `reject`，最优 skill 不会更新。这是正常行为。

如果 `best_step = 0`，表示没有任何候选超过初始 skill，最终 best 仍为初始 skill。

## 导出优化结果

完整训练结束后，将 best skill 和对应脚本落地：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py `
  --skillopt-output shortage_analyze-opt/train/outputs/shortage_analyze_<harness_name>_v1
```

默认输出：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/best_kill.md
shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

如果只想复制 best skill，不生成脚本：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py `
  --skillopt-output shortage_analyze-opt/train/outputs/shortage_analyze_<harness_name>_v1 `
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

可以直接把下面这段发给新 harness：

```text
请在 D:\code\github\hehe03\SkillOpt 仓库中优化 shortage_analyze-opt/shortage_analyze。

开始前请完整阅读：
- shortage_analyze-opt/HARNESS_GUIDE.md
- shortage_analyze-opt/README.md
- shortage_analyze-opt/train/configs/default.yaml
- shortage_analyze-opt/train/shortage_analyze_skillopt/adapter.py
- shortage_analyze-opt/train/shortage_analyze_skillopt/rollout.py

要求：
1. 不要修改 shortage_analyze-opt/shortage_analyze。
2. 训练流程不能读取 data.xlsx，不能读取测试集标签。
3. 使用 SkillOpt 优化。
4. 使用当前 harness 自带大模型，不额外配置 LLM key。
5. target 执行必须先生成/复用 Python 规则脚本，再用脚本预测；不要逐样本调用 LLM。
6. 使用新的 out_root，不要复用旧输出目录。
7. 运行中报告每步 rollout_hard、selection_hard、action、best_score、best_step。
```
