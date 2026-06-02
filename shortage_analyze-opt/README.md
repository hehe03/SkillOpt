# shortage_analyze 的 SkillOpt 优化流程

本目录把原始 skill、训练前后处理、SkillOpt 训练和优化产物分开管理，目的是避免优化过程读取 `data.xlsx` 或测试集标签。

如果要交给新的 Agent harness（例如 Codex、opencode 或其它 Agent）继续运行，请先让它阅读 [HARNESS_GUIDE.md](HARNESS_GUIDE.md)。

## 目录约定

- `shortage_analyze/`：原始 skill，只作为 process 阶段的来源，不修改，不参与训练过程。
- `shortage_analyze-init/`：处理后的初始 SkillOpt skill 和对应初始脚本，是训练阶段的初始输入。
- `shortage_analyze-optimized/`：优化完成后的 skill 和对应脚本。
- `process/`：训练前数据处理、初始 skill 构建、训练后导出和测试集比较。这里可以读取原始数据或测试集标签。
- `processed/`：处理后的 train/val/test split 和离线评估输出。
- `train/`：SkillOpt 训练入口、配置和 `shortage_analyze` adapter。训练流程只读取 `processed` split 和 `shortage_analyze-init`。

## 接手前检查

新的 Agent harness 接手时先检查下面文件：

```text
shortage_analyze-opt/processed/shortage_analyze_split/train/items.json
shortage_analyze-opt/processed/shortage_analyze_split/val/items.json
shortage_analyze-opt/processed/shortage_analyze_split/test/items.json
shortage_analyze-opt/shortage_analyze-init/initial_skill.md
shortage_analyze-opt/shortage_analyze-init/analyze_shortage.py
```

如果这些文件都存在，就不需要重复执行数据处理或初始 skill 构建，直接从“运行 SkillOpt 优化”开始。只有 split 缺失时才执行第 1 步；只有 `shortage_analyze-init` 缺失或明确需要重建时才执行第 2 步。

## 1. 处理数据

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

训练配置中 `test/items.json` 不应带可用于优化的测试标签；训练阶段也禁止读取原始 Excel。

## 2. 构建初始 SkillOpt skill

```powershell
conda run -n llm python shortage_analyze-opt/process/build_initial_skill.py
```

该脚本只在 process 阶段读取原始 skill 目录：

```text
shortage_analyze-opt/shortage_analyze/SKILL.md
shortage_analyze-opt/shortage_analyze/references/rules.md
```

输出：

```text
shortage_analyze-opt/shortage_analyze-init/initial_skill.md
```

初始快速脚本放在：

```text
shortage_analyze-opt/shortage_analyze-init/analyze_shortage.py
```

`initial_skill.md` 是自包含规则文档，不要求 Agent 再调用原始 skill 或 `references/`。

## 3. 运行 SkillOpt 优化

```powershell
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py --config shortage_analyze-opt/train/configs/default.yaml
```

关键配置：

- `model.backend: agent_harness`：LLM 调用交给当前 Agent/harness 自带大模型。
- `model.optimizer/target: harness-default`：使用当前 harness 默认模型，不额外配置 LLM key。
- `env.skill_init`、`env.initial_skill_path` 指向 `shortage_analyze-init/initial_skill.md`。
- `env.initial_script_path` 指向 `shortage_analyze-init/analyze_shortage.py`。
- `env.data_path: ""`、`evaluation.eval_test: false`、`env.allow_test_labels: false`：训练过程不读取 `data.xlsx` 或测试集标签。

训练阶段 target 执行采用“先生成/复用 Python 规则脚本，再程序执行预测”的机制：

- 初始 skill 直接使用 `shortage_analyze-init/analyze_shortage.py`。
- 后续候选 skill 按 skill hash 缓存脚本到 `<out_root>/generated_scripts/<hash>/analyze_shortage.py`。
- 只有当前 skill 没有脚本时，才调用当前 Agent harness 自带模型生成一次脚本。
- 训练样本预测、样本级 accuracy、`missing_labels`、`extra_labels` 和逐标签 TP/FN/FP 细节都会写入 rollout 轨迹。

## 4. 导出优化结果

训练完成后运行：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py
```

默认会将：

```text
shortage_analyze-opt/train/outputs/shortage_analyze/best_skill.md
```

导出为：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/best_kill.md
shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

脚本生成同样使用 `train/shortage_analyze_skillopt/harness_chat.py` 的 `run_agent_chat(...)`，不会再固定要求 Codex CLI。

只导出 best skill、不生成脚本：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py --script-mode skip
```

## 5. 比较优化前后测试集准确率

```powershell
conda run -n llm python shortage_analyze-opt/process/compare_test_accuracy.py
```

比较脚本属于 process 阶段，可以读取原始全量数据中的测试集标签。默认比较：

```text
优化前：shortage_analyze-opt/shortage_analyze/scripts/analyze_shortage.py
优化后：shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

输出：

```text
shortage_analyze-opt/processed/eval/test_accuracy_compare.json
```
