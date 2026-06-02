# shortage_analyze 的 SkillOpt 优化流程

本目录把原始 `shortage_analyze` skill、SkillOpt 训练流程、训练前后处理流程分开，避免优化过程读取原始 Excel 或测试集标签。

## 目录约定

- `shortage_analyze/`：原始 skill，不修改。其 `references/rules.md` 和 `scripts/analyze_shortage.py` 是原始规则来源。
- `process/`：训练前数据处理、生成 SkillOpt 初始 skill、训练后导出和测试比较。这里可以读取原始数据或最终测试标签。
- `processed/`：训练 split 和离线评估输出。
- `train/`：SkillOpt 训练入口、配置和 `shortage_analyze` adapter。训练流程只读取 `processed` split 和 `shortage_analyze-optimized/init/initial_skill.md`。
- `shortage_analyze-optimized/init/initial_skill.md`：由原始 skill 和详细规则生成的 SkillOpt 优化基线。
- `shortage_analyze-optimized/init/analyze_shortage.py`：`initial_skill.md` 对应的初始快速预测脚本。
- `shortage_analyze-optimized/best/best_kill.md`：训练结束后落地的优化后 skill。
- `shortage_analyze-optimized/best/scripts/analyze_shortage.py`：训练结束后由优化后规则生成的快速预测脚本。

## 1. 处理数据

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda run -n llm python shortage_analyze-opt/process/prepare_skillopt_data.py
```

默认读取 `D:\code\github\hehe03\data.xlsx`，输出：

```text
shortage_analyze-opt/processed/shortage_analyze_split/
  train/items.json  # 带标签，用于优化
  val/items.json    # 带标签，用于 gate/selection
  test/items.json   # 不带标签，优化过程不可读取测试答案
  split_manifest.json
```

## 2. 生成 SkillOpt 初始 skill

```powershell
conda run -n llm python shortage_analyze-opt/process/build_initial_skill.py
```

该脚本只读取原始：

- `shortage_analyze/SKILL.md`
- `shortage_analyze/references/rules.md`

并生成：

```text
shortage_analyze-opt/shortage_analyze-optimized/init/initial_skill.md
```

这个文件把详细业务规则合并成可被 SkillOpt 优化的自包含规则文档，不再要求 Agent 调用原始脚本。

## 3. 运行 SkillOpt 优化

```powershell
conda run -n llm python shortage_analyze-opt/train/train_shortage_analyze.py --config shortage_analyze-opt/train/configs/default.yaml
```

默认配置：

- `env.skill_init` 指向 `shortage_analyze-optimized/init/initial_skill.md`。
- `env.split_dir` 指向 `processed/shortage_analyze_split`。
- `env.data_path` 为空，训练流程不会读取 `data.xlsx`。
- `evaluation.eval_test: false` 且 `env.allow_test_labels: false`，优化过程不会读取测试集标签。
- `env.out_root` 固定为 `shortage_analyze-opt/train/outputs/shortage_analyze`。
- 训练 gate 的最终指标是样本级 accuracy：预测标签集合必须与 gold 标签集合完全一致才算正确；反思阶段会额外看到 `missing_labels`、`extra_labels` 和逐标签 TP/FN/FP 细节，用于优化单个 L2 选项规则。

训练阶段的目标执行不再让 LLM 逐条阅读理解样本，而是先把当前 skill 版本转换成 Python 规则脚本，再用脚本批量预测：

- 初始 skill 直接使用 `shortage_analyze-optimized/init/analyze_shortage.py`。
- 后续每个候选 skill 会按 skill hash 缓存在 `env.out_root/generated_scripts/<hash>/analyze_shortage.py`。
- 只有“当前 skill 版本还没有脚本”时，才调用 Agent 自带模型生成一次脚本。
- 预测值、样本级 accuracy 和逐标签 FP/FN 细节仍写入 rollout 轨迹，供 SkillOpt 反思和 gate 使用。

LLM 调用通过训练入口转到 Agent 自带模型：优化侧 `openai_chat` 会被包装到 Codex CLI；目标预测阶段只在需要生成新脚本时使用 Agent 模型。

## 4. 导出优化结果和快速脚本

训练完成后运行：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py
```

默认会：

1. 将 `shortage_analyze-opt/train/outputs/shortage_analyze/best_skill.md` 复制到：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/best_kill.md
```

2. 使用 Codex CLI 读取 `best_kill.md`，生成优化规则对应的快速脚本：

```text
shortage_analyze-opt/shortage_analyze-optimized/best/scripts/analyze_shortage.py
```

如果只想先落地 skill，不生成脚本，可加：

```powershell
conda run -n llm python shortage_analyze-opt/process/finalize_optimized_skill.py --script-mode skip
```

## 5. 比较优化前后测试集准确率

```powershell
conda run -n llm python shortage_analyze-opt/process/compare_test_accuracy.py
```

默认比较：

- 优化前：`shortage_analyze/scripts/analyze_shortage.py`
- 优化后：`shortage_analyze-optimized/best/scripts/analyze_shortage.py`

输出：

```text
shortage_analyze-opt/processed/eval/test_accuracy_compare.json
```
