# 新 skill 和数据准备指南

本文档用于把一个新 skill 和它的原始数据处理成 `opt-in-harness` 可以优化的状态。完成本文档后，再交给新的 harness 阅读 `HARNESS_GUIDE.md` 开始训练。

## 目标结构

为每个待优化 skill 新建一个 workspace：

```text
opt-in-harness/workspace/<skill_name>/
  configs/default.yaml
  data/<split_name>/
    train/items.json
    val/items.json
    test/items.json
  init-skill/
    initial_skill.md
    <initial_executor>.py        # 可选，脚本化 rollout 时需要
  process/
    prepare_data.py              # 建议命名，可按项目改名
    finalize_optimized_skill.py  # 可选
    compare_test_accuracy.py     # 可选
  train/
    adapter.py
    evaluator.py
    rollout.py
    prompts/
      analyst_error.md
      analyst_success.md
      script_codegen.md          # 可选，脚本化 rollout 时需要
    __init__.py
  outputs/
```

## 第一步：整理初始 skill

把原始 skill 中真正指导执行的规则合并成：

```text
init-skill/initial_skill.md
```

要求：

- `initial_skill.md` 应是 SkillOpt 优化的起点，内容要自洽。
- 如果原始 skill 只是“调用某个脚本”的壳，而真正规则在 `references/` 或代码里，应把规则文字融合进 `initial_skill.md`。
- 不要只保留原始 skill 摘要；要保留会影响预测或决策的细节。
- 如果训练执行采用“Skill 文档转脚本再批量预测”，还要放一个初始执行脚本，例如 `init-skill/analyze.py`，作为初始 skill 的快速执行基线和接口参考。

## 第二步：预处理原始数据

原始 Excel、CSV、数据库、trace 文件等由 `process/` 下脚本处理。推荐写成：

```text
process/prepare_data.py
```

预处理脚本负责：

1. 读取原始数据。
2. 清洗、归一化字段。
3. 切分 train/val/test。
4. 写出标准 split。

训练阶段不再做原始数据解析，不为每个原始格式写 DataLoader。也就是说，优先保留“预处理成标准格式”的模式，而不是让训练期 dataloader 继续理解 Excel、CSV 或业务目录结构。

标准 split 目录：

```text
data/<split_name>/
  train/items.json
  val/items.json
  test/items.json
```

每个 `items.json` 是 JSON 数组。推荐字段：

```json
{
  "id": "sample_001",
  "features": {
    "字段A": "xxx",
    "字段B": 123
  },
  "ground_truth": "训练或验证标签",
  "task_type": "可选子任务名",
  "metadata": {
    "可选诊断字段": "..."
  }
}
```

字段约定：

- `id`：样本唯一标识，建议必须有。
- `features`：业务输入字段容器，不同 skill 可以完全不同。
- `ground_truth`：训练和验证评分用答案。
- `task_type`：可选，用于分子任务统计或代表性样本选择。
- `metadata`：可选，只放训练分析需要的辅助信息。

如果数据已处理成这个格式，训练代码可以直接复用公共 `StandardItemsDataLoader`，不需要新建 `train/dataloader.py`。

### 类别不平衡数据

如果任务标签明显不平衡，例如 `goodcase` / `badcase`、正例 / 负例、通过 / 失败样本数量差异较大，需要同时处理 split 和训练 batch：

- 预处理按比例切分 `train/val/test` 时，应优先按 `ground_truth` 或原始标签做分层切分，避免某个 split 缺少少数类。
- 分层切分只保证整体 split 的标签分布，不保证每个训练 batch 内类别均衡。
- 训练适配代码应为该 skill 增加 balanced batch sampler。推荐在 `adapter.py` 中继承 `StandardItemsDataLoader`，覆盖 `build_train_batch()`；如训练 loop 使用整 epoch 规划，也同时覆盖 `plan_train_epoch()`。
- balanced sampler 默认应只影响训练 batch；`val` / `test` 评估 batch 应保持原始分布和稳定顺序。
- 少数类样本不足以填满 batch 配额时，可以按固定 seed 有放回采样，保证每个 batch 都能看到少数类错误模式。
- 建议把开关写入 `configs/default.yaml`，例如 `balanced_train_batches: true` 和 `balance_labels: goodcase,badcase`，便于后续关闭或调整。

## 第三步：编写训练适配代码

### `train/adapter.py`

`adapter.py` 是必须文件。它负责把该 skill 接到 SkillOpt 的 `EnvAdapter` 生命周期：

- 初始化 dataloader。
- 构造 train/eval batch。
- 调用 `rollout()` 执行当前 skill。
- 调用 `reflect()` 分析结果并产出 patch。
- 提供 `get_task_types()`。

标准 split 数据可直接使用：

```python
from split_items_loader import StandardItemsDataLoader
```

如果训练标签不平衡，不要直接使用公共 loader 的默认训练抽样。公共 `StandardItemsDataLoader` 会随机打乱 `train_items` 后截取 batch，不做类别均衡；应在当前 skill 的 `adapter.py` 中增加任务专属 loader，例如：

```python
class BalancedSkillDataLoader(StandardItemsDataLoader):
    def build_train_batch(self, batch_size: int, seed: int, **kwargs) -> BatchSpec:
        # 按 ground_truth 分桶，按配置比例抽样；少数类不足时用固定 seed 有放回采样。
        ...

    def plan_train_epoch(self, *, epoch: int, steps_per_epoch: int, accumulation: int, batch_size: int, seed: int, **kwargs):
        # 如果训练 loop 走 epoch planner，也要让每个 planned batch 使用同一套 balanced sampler。
        ...
```

该 sampler 应保持可配置，并在样本桶缺失时退回普通随机抽样，避免小样本或单标签数据直接失败。

如果 adapter 位于 `workspace/<skill_name>/train/adapter.py`，通常需要把公共 train 加入 `sys.path`：

```python
from pathlib import Path
import sys

COMMON_TRAIN_ROOT = Path(__file__).resolve().parents[3] / "train"
if str(COMMON_TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_TRAIN_ROOT))
```

### `train/evaluator.py`

`evaluator.py` 是必须文件，负责把单个样本的预测和 `ground_truth` 转成 SkillOpt 使用的结果字段。

至少应能产出：

```python
{
  "hard": 0 或 1,
  "soft": 0.0 到 1.0,
  "prediction": "...",
  "gold_answer": "..."
}
```

如果是多标签任务，建议同时输出缺失标签、多余标签、逐标签对比等诊断字段，供 reflect prompt 使用。

### `train/rollout.py`

`rollout.py` 是必须文件，负责执行当前 skill 并批量返回结果。

常见两种模式：

1. **LLM 直接执行**

   对每个样本，把 `skill_content` 和 `features` 发给目标模型，让模型返回答案，再用 `evaluator.py` 评分。

2. **脚本化执行**

   先让 harness 把当前 `skill_content` 转成 Python 脚本，然后用脚本批量预测。适合规则分类、表格规则、可程序化决策等任务。

   这种模式通常需要：

   ```text
   init-skill/<initial_executor>.py
   train/prompts/script_codegen.md
   ```

`rollout.py` 返回给 SkillOpt 的每条结果至少包含：

```python
{
  "id": "...",
  "hard": 0 或 1,
  "soft": 0.0 到 1.0
}
```

其它字段可以按任务需要加入，用于 reflect 分析。

### `train/prompts/*.md`

建议把任务专属 prompt 放到文件中，而不是写在 Python 字符串里：

```text
train/prompts/analyst_error.md
train/prompts/analyst_success.md
train/prompts/script_codegen.md
```

其中：

- `analyst_error.md`：失败样本分析 prompt。
- `analyst_success.md`：成功样本保留/泛化 prompt。
- `script_codegen.md`：脚本化 rollout 的代码生成 prompt，可选。

## 第四步：编写配置

`configs/default.yaml` 至少包含：

```yaml
_base_: ../../../../configs/_base_/default.yaml

model:
  backend: agent_harness
  optimizer: harness-default
  target: harness-default
  optimizer_backend: agent_harness
  target_backend: agent_harness

train:
  num_epochs: 2
  train_size: 0
  batch_size: 8
  seed: 42

gradient:
  minibatch_size: 4
  merge_batch_size: 4
  analyst_workers: 1
  failure_only: false

evaluation:
  use_gate: true
  sel_env_num: 24
  test_env_num: 0
  eval_test: false

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
  balanced_train_batches: true   # 标签不平衡任务建议开启
  balance_labels: goodcase,badcase
```

如果使用脚本化 rollout，可继续添加该任务需要的字段，例如：

```yaml
  initial_skill_path: opt-in-harness/workspace/<skill_name>/init-skill/initial_skill.md
  initial_script_path: opt-in-harness/workspace/<skill_name>/init-skill/<initial_executor>.py
  script_cache_dir: ""
  script_codegen_timeout: 900
  script_codegen_model: harness-default
```

## 第五步：可选训练后脚本

如果需要把某次 run 的 `best_skill.md` 导出成最终 skill，写：

```text
process/finalize_optimized_skill.py
```

如果需要比较优化前后在测试集上的准确率，写：

```text
process/compare_test_accuracy.py
```

这些脚本属于训练后流程，不由 `train_in_harness.py` 自动调用。

## 完成检查

交给 harness 开始优化前，确认：

- `configs/default.yaml` 存在。
- `train/items.json` 和 `val/items.json` 可被读取。
- `init-skill/initial_skill.md` 存在且包含完整初始规则。
- `train/adapter.py` 能被 `env.adapter_module` 加载。
- `train/rollout.py` 返回结果包含 `id`、`hard`、`soft`。
- `train/evaluator.py` 的指标与目标任务一致。

然后让 harness 阅读：

```text
opt-in-harness/HARNESS_GUIDE.md
```
