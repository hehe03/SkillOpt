# SkillOpt 文档综合说明

本文档综合整理 `docs/` 目录下全部 Markdown 文档，覆盖项目定位、安装运行、训练循环、配置、Skill Document、扩展接口、CLI/API 参考、本地 smoke test 和贡献流程。命令、路径、配置键、类名、API 名称和英文专有名词保留原文。

## 阅读范围

本次综合整理覆盖以下文档：

- `docs/index.md`
- `docs/guide/installation.md`
- `docs/guide/first-experiment.md`
- `docs/guide/training-loop.md`
- `docs/guide/dl-analogy.md`
- `docs/guide/configuration.md`
- `docs/guide/skill-document.md`
- `docs/guide/new-benchmark.md`
- `docs/guide/new-backend.md`
- `docs/guide/local-env-smoke.md`
- `docs/reference/config.md`
- `docs/reference/cli.md`
- `docs/reference/api.md`
- `docs/contributing.md`

## 项目定位

SkillOpt 的核心目标是：像训练神经网络一样训练 Agent 的自然语言 skill 文档，但不更新模型权重。被优化的对象不是 parameter tensor，而是 Markdown 格式的 **Skill Document**。

项目使用循环式优化：

```text
rollout -> reflect -> aggregate -> select -> update -> gate
```

其中：

- `target` model 使用当前 skill 执行任务。
- `optimizer` model 分析运行轨迹，提出 skill edit patches。
- 系统合并、筛选并应用 edits。
- validation gate 在 selection split 上验证新 skill，决定 accept/reject。
- epoch 边界还会执行 `slow_update` 和 `meta_skill`，用于长期经验沉淀与跨 epoch 策略记忆。

## 深度学习类比

SkillOpt 文档反复使用 deep learning 类比来解释框架：

| Deep Learning        | SkillOpt                   | 含义                               |
| -------------------- | -------------------------- | -------------------------------- |
| Model weights        | Skill document             | 被优化的主体                           |
| Forward pass         | Rollout                    | target model 使用当前 skill 执行任务     |
| Loss / evaluator     | Task evaluator             | 对任务执行结果打分                        |
| Backpropagation      | Reflect                    | optimizer 分析轨迹并产生 edit patches   |
| Gradients            | Edit patches               | 对 skill 的候选修改                    |
| Gradient aggregation | Patch aggregation          | 合并语义相近 edits                     |
| Gradient clipping    | Edit selection             | 限制每步最多应用多少 edits                 |
| Learning rate        | `optimizer.learning_rate`  | 每步最大 edit 数                      |
| LR scheduler         | `optimizer.lr_scheduler`   | edit budget 衰减策略                 |
| SGD step             | Skill update               | 将 edits 应用到 Markdown             |
| Validation set       | Selection split            | gate 用来判断是否接受更新                  |
| Epoch                | Epoch                      | 多步训练后执行 slow update / meta skill |
| Momentum             | Slow update                | epoch 边界纵向比较和指导                  |
| Meta-learning        | Meta skill                 | 跨 epoch 的 optimizer 策略记忆         |
| Batch size           | `train.batch_size`         | 每次 rollout 的任务数量                 |
| Data parallelism     | `gradient.analyst_workers` | 并行 reflection worker             |
| Checkpointing        | Skill snapshots            | 每步保存 skill 版本                    |

文档给出的经验是：

- `cosine` 通常优于 `constant`。
- 中等 `learning_rate` 更稳，过小学习慢，过大容易噪声大。
- `slow_update` 有助于减少 catastrophic forgetting。
- `meta_skill` 让 optimizer 带着跨 epoch 策略记忆继续反思。
- batch size 不是越大越好，因为 API 成本和收益存在边际递减。
- skill 通常比神经网络收敛更快，2-4 个 epoch 往往已经足够。

## 安装与环境

基础要求：

- Python 3.10+
- 至少一个模型后端凭据，例如 Azure OpenAI、OpenAI、Anthropic 或本地 Qwen

快速安装：

```bash
git clone https://github.com/microsoft/SkillOpt.git
cd SkillOpt
pip install -e .
```

可选依赖：

```bash
pip install -e ".[alfworld]"
pip install -e ".[claude]"
pip install -e ".[qwen]"
pip install -e ".[webui]"
pip install -e ".[dev]"
pip install -e ".[alfworld,claude,qwen,webui,dev]"
```

环境变量配置：

```bash
cp .env.example .env
```

常见凭据：

```ini
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

验证安装：

```bash
python -c "import skillopt; print('SkillOpt ready!')"
```

## 首次实验

文档推荐从 SearchQA 开始，因为它是较轻量的 benchmark。

常见 benchmark 难度与时长：

| Benchmark | 难度     | 典型耗时    |
| --------- | ------ | ------- |
| SearchQA  | Easy   | 约 30 分钟 |
| DocVQA    | Medium | 约 2 小时  |
| ALFWorld  | Hard   | 约 3 小时  |

查看配置：

```bash
cat configs/searchqa/default.yaml
```

训练：

```bash
python scripts/train.py --config configs/searchqa/default.yaml
```

评估 best skill：

```bash
python scripts/eval_only.py \
  --config configs/searchqa/default.yaml \
  --skill outputs/searchqa/<run_id>/skills/best_skill.md
```

WebUI：

```bash
pip install -e ".[webui]"
python -m skillopt_webui.app
```

然后打开：

```text
http://localhost:7860
```

## 训练循环详解

### 1. Rollout

`target` model 使用当前 skill document 作为 prompt 执行任务。每个任务会产生：

- prediction / response
- trajectory / conversation
- hard score
- soft score
- 可选的 failure reason 和任务上下文

类比 forward pass：

```python
predictions = model(input, skill_document)
scores = evaluate(predictions, ground_truth)
```

### 2. Reflect

`optimizer` model 分析失败或成功轨迹，产生结构化 edit patches。文档描述两种分析风格：

- Shallow：独立分析每条轨迹。
- Deep：跨多个失败样本找系统性问题。

类比 backpropagation：

```python
gradients = loss.backward()  # -> edit patches
```

### 3. Aggregate

合并语义上相似的 edit patches，避免冗余、重复或冲突修改。

### 4. Select

对 edits 排名，并根据 `optimizer.learning_rate` 截断最大应用数量。这相当于 gradient clipping。

支持的 scheduler：

- `cosine`
- `linear`
- `constant`
- `autonomous`

### 5. Update

将选中的 edits 应用到 skill document，生成新的候选 skill。

### 6. Gate

在 selection split 上评估候选 skill。只有当验证效果满足 gate 条件时，更新才被接受。

### Epoch 边界机制

`slow_update`：从第 2 个 epoch 开始，系统会在相同样本上比较上一 epoch skill 与当前 skill，将样本归类为 improved、regressed、persistent_fail、stable_success 等，然后生成高层 guidance 并注入 skill，减少遗忘。

`meta_skill`：跨 epoch 累积 optimizer 侧的策略记忆。每个 epoch 结束时，optimizer 反思 epoch 间变化，生成紧凑策略 notes，后续 reflection 会把它作为额外上下文。

## Skill Document

Skill Document 是 Markdown 文件，是 Agent 的“prompt weights”。它用自然语言编码任务策略，而不是用浮点参数编码知识。

典型结构：

```markdown
# Task Strategy

## General Approach
- Break complex problems into sub-steps
- Always verify intermediate results

## Common Patterns
- When you see X, try approach Y
- Avoid Z because it leads to errors

## Edge Cases
- If the input contains A, handle it specially by...
- Watch out for B -- it requires C

## Output Format
- Always include reasoning before the answer
- Format numbers with proper units
```

训练过程中，Skill Document 通过 edit patches 变化：

- Additions：加入从失败轨迹发现的新规则。
- Modifications：细化已有但不充分的规则。
- Deletions：删除持续导致错误的规则。

初始 skill 可以是：

- Empty skill：从零开始学习。
- Seed skill：给定领域先验，加速收敛。
- Pre-trained skill：从相近 benchmark 迁移。

文档中提到可通过 YAML 配置初始 skill；当前仓库实践中通常使用：

```yaml
env:
  skill_init: skillopt/envs/searchqa/skills/initial.md
```

质量指标包括：

- validation score
- test score
- skill length
- edit acceptance rate

最佳实践：

- 有领域知识时优先提供 seed skill。
- 使用 `cosine` LR schedule。
- 启用 `use_slow_update: true`。
- 启用 `use_meta_skill: true`。

## 配置体系

SkillOpt 使用 YAML 配置，并支持继承和覆盖。

目录结构：

```text
configs/
├── _base_/
│   └── default.yaml
├── searchqa/
│   └── default.yaml
├── docvqa/
│   └── default.yaml
└── alfworld/
    └── default.yaml
```

benchmark config 继承 `_base_/default.yaml`，再覆盖特定参数。

### Model

```yaml
model:
  backend: azure_openai
  optimizer: gpt-5.5
  target: gpt-5.5
  optimizer_backend: openai_chat
  target_backend: openai_chat
  reasoning_effort: medium
```

含义：

- `optimizer` 用于 reflection、slow update 等优化环节。
- `target` 用于 rollout 执行任务。
- `optimizer_backend` 与 `target_backend` 可以不同。

支持的 backend 包括：

- `openai_chat`
- `claude_chat`
- `qwen_chat`
- `minimax_chat`
- `codex_exec`
- `claude_code_exec`

### Training

```yaml
train:
  num_epochs: 4
  batch_size: 40
  accumulation: 1
  seed: 42
```

含义：

- `num_epochs`：训练轮数。
- `batch_size`：每 step 的任务数。
- `accumulation`：梯度/patch 累积轮数。
- `seed`：随机种子。

### Gradient / Reflection

```yaml
gradient:
  minibatch_size: 8
  merge_batch_size: 8
  analyst_workers: 16
  max_analyst_rounds: 3
  failure_only: false
```

含义：

- `minibatch_size`：每次 reflection 分析的轨迹数。
- `merge_batch_size`：patch merge 的批大小。
- `analyst_workers`：并行 reflection worker。
- `failure_only`：是否只分析失败样本。

### Optimizer

```yaml
optimizer:
  learning_rate: 4
  min_learning_rate: 2
  lr_scheduler: cosine
  skill_update_mode: patch
  use_slow_update: true
  slow_update_samples: 20
  use_meta_skill: true
  longitudinal_pair_policy: mixed
```

含义：

- `learning_rate`：每步最多应用多少 edits。
- `min_learning_rate`：scheduler 衰减后的最小 edit budget。
- `lr_scheduler`：`constant` / `linear` / `cosine` / `autonomous`。
- `skill_update_mode`：`patch` / `rewrite_from_suggestions` / `full_rewrite_minibatch`。
- `use_slow_update`：epoch 边界纵向比较和 guidance。
- `use_meta_skill`：跨 epoch 策略记忆。
- `longitudinal_pair_policy`：`mixed` / `changed` / `unchanged`。

### Evaluation

```yaml
evaluation:
  use_gate: true
  eval_test: true
```

含义：

- `use_gate`：是否启用 validation gate。
- `eval_test`：训练结束后是否跑 test evaluation。

### Environment

```yaml
env:
  name: searchqa
  split_mode: ratio
  split_ratio: "2:1:7"
  data_path: ""
  split_dir: ""
  skill_init: ""
  exec_timeout: 120
  out_root: ""
```

含义：

- `env.name`：benchmark 名称。
- `split_mode`：`ratio` 或 `split_dir`。
- `split_ratio`：自动切分比例，格式为 train:val:test。
- `data_path`：原始数据路径。
- `split_dir`：已有 train/val/test split 目录。
- `skill_init`：初始 skill 路径。
- `exec_timeout`：单任务超时秒数。
- `out_root`：输出目录。

### CLI 覆盖

文档给出两类覆盖方式。推荐使用 `--cfg-options`：

```bash
python scripts/train.py \
  --config configs/searchqa/default.yaml \
  --cfg-options optimizer.learning_rate=16 optimizer.lr_scheduler=linear
```

也可以使用 legacy flat arguments，例如：

```bash
python scripts/train.py \
  --config configs/searchqa/default.yaml \
  --batch_size 20 \
  --num_epochs 1
```

## CLI 参考

训练：

```bash
python scripts/train.py --config <config.yaml> [overrides...]
```

常用参数：

| 参数              | 说明                |
| --------------- | ----------------- |
| `--config`      | YAML config 路径，必填 |
| `--cfg-options` | 覆盖任意配置项           |
| `--split_dir`   | 覆盖数据 split 目录     |
| `--out_root`    | 指定输出目录            |
| `--batch_size`  | 覆盖 batch size     |
| `--num_epochs`  | 覆盖 epoch 数        |

评估：

```bash
python scripts/eval_only.py --config <config.yaml> --skill <skill.md>
```

常用参数：

| 参数         | 说明                                 |
| ---------- | ---------------------------------- |
| `--config` | YAML config 路径                     |
| `--skill`  | 要评估的 skill document                |
| `--split`  | 评估 split，例如 `test`、`valid`、`train` |

WebUI：

```bash
python -m skillopt_webui.app [--port PORT] [--share]
```

## 输出结构

首次实验文档展示的典型输出结构如下：

```text
outputs/searchqa/<run_id>/
├── steps/
│   ├── step_0001/
│   │   ├── candidate_skill.md
│   │   ├── step_record.json
│   │   └── trajectory_digest.json
│   └── step_0002/
├── slow_update/
│   └── epoch_02/
├── meta_skill/
│   └── epoch_02/
├── skills/
│   └── step_0001.md
├── best_skill.md
├── history.json
└── config.yaml
```

实际仓库版本中还常见：

- `rollout/predictions/<task_id>/conversation.json`
- `target_system_prompt.txt`
- `target_user_prompt.txt`
- `patches/*.json`
- `candidate_skill.md`
- `step_record.json`
- `history.json`
- `best_skill.md`

## 新增 Benchmark

新增 benchmark 通常需要四部分：

1. `SplitDataLoader` subclass：负责读取 train/val/test 数据。
2. rollout helper：让 target model 执行任务，并对预测结果打分。
3. `EnvAdapter` subclass：把 loader、rollout、reflect 接入训练生命周期。
4. YAML config：声明 env name 和训练/优化参数。

### DataLoader

核心是实现 `load_split_items(split_path)`。如果支持 `split_mode="ratio"`，再实现 `load_raw_items(data_path)`。

示意：

```python
class DocFaithfulDataLoader(SplitDataLoader):
    def load_split_items(self, split_path: str) -> list[dict]:
        ...
```

每个 item 至少应该有稳定的 `id` 字段，其他字段由 benchmark 自己定义。

### Rollout helper

rollout 负责：

- 构造 target prompt。
- 调用 `skillopt.model.chat_target`。
- 解析 prediction。
- 计算 `hard` 和 `soft`。
- 返回 list[dict]。

返回 dict 的硬要求：

```python
{
    "id": "...",
    "hard": 0,
    "soft": 0.13
}
```

其他字段如 `predicted_answer`、`question`、`reference_text`、`fail_reason` 等会作为 extras 保留，供 reflection 使用。

### EnvAdapter

必须实现：

- `build_train_env`
- `build_eval_env`
- `rollout`
- `reflect`
- `get_task_types`

常见模式是 dataset-backed env 的 env manager 直接是 `list[dict]`。

`reflect()` 通常调用：

```python
run_minibatch_reflect(...)
```

并传入：

- rollout results
- current skill
- prediction_dir
- patches_dir
- analyst workers
- minibatch size
- edit budget
- prompt hooks

### 注册

根据 `docs/reference/api.md` 和 `docs/guide/new-benchmark.md`，当前更可信的注册位置是 `scripts/train.py` 中的 `_register_builtins()`：

```python
try:
    from skillopt.envs.docfaithful.adapter import DocFaithfulAdapter
    _ENV_REGISTRY["docfaithful"] = DocFaithfulAdapter
except ImportError:
    pass
```

注意：`docs/contributing.md` 中的 checklist 提到注册在 `skillopt/envs/__init__.py`，这与 API Reference / New Benchmark guide 不一致。综合源码和 reference 文档，应以 `scripts/train.py` 的 lazy registry 为准。

### Config

示例：

```yaml
_base_: ../_base_/default.yaml

model:
  reasoning_effort: medium

train:
  batch_size: 16
  accumulation: 1
  num_epochs: 4

gradient:
  minibatch_size: 8
  merge_batch_size: 8

optimizer:
  learning_rate: 4

env:
  name: docfaithful
  skill_init: skillopt/envs/docfaithful/skills/initial.md
  split_mode: split_dir
  split_dir: data/docfaithful_split
  workers: 4
  max_completion_tokens: 4096
  limit: 0
```

文档特别提醒：`_base_` 当前应写成字符串路径：

```yaml
_base_: ../_base_/default.yaml
```

不要写成 list 形式：

```yaml
_base_: ['../_base_/default.yaml']
```

## 本地 Smoke Test

为自定义环境接入真实模型或大数据集前，应先做轻量 smoke test，验证 plumbing：

- config loading
- adapter construction
- dataloader splits
- rollout output shape
- reflection patch shape
- merge/rank/update control flow
- artifact creation under `out_root`

建议步骤：

1. 准备 tiny fixture split。
2. 支持 offline mock mode，例如 `mock: true`。
3. 使用单步小配置。
4. 返回 optimizer JSON 前做 schema validation。
5. 从 py_compile 到 mock run 再到真实 tiny run，逐步增强。
6. 自定义环境保持隔离，避免影响内置 benchmark。

tiny config 示例：

```yaml
train:
  num_epochs: 1
  train_size: 3
  batch_size: 3

gradient:
  minibatch_size: 1
  merge_batch_size: 2
  analyst_workers: 1
  max_analyst_rounds: 1

optimizer:
  learning_rate: 1
  min_learning_rate: 1
  lr_scheduler: constant
  skill_update_mode: patch
  use_slow_update: false

evaluation:
  use_gate: true
  sel_env_num: 2
  test_env_num: 2
  eval_test: false

env:
  name: myenv
  out_root: outputs/myenv_tiny_mock
  mock: true
```

推荐检查：

```bash
python -m py_compile scripts/train.py skillopt/envs/myenv/adapter.py
python scripts/train.py --config configs/myenv/tiny_mock.yaml
python scripts/train.py --config configs/myenv/tiny.yaml
```

optimizer JSON 需要检查：

- response 是 JSON object。
- `edits` 是非空 list。
- 每个 edit 是 object。
- edit op 合法。
- `content` 或 `target` 等必需字段存在。
- ranking 的 `selected_indices` 存在、唯一、在范围内，且数量不超过 edit budget。

## API 参考

### `EnvAdapter`

定义位置：`skillopt/envs/base.py`。

作用：连接 trainer 与 benchmark / simulator / REST API 等环境。

必须实现：

```python
def build_train_env(self, batch_size: int, seed: int, **kwargs): ...
def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs): ...
def rollout(self, env_manager, skill_content: str, out_dir: str, **kwargs) -> list[dict]: ...
def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs) -> list[dict | None]: ...
def get_task_types(self) -> list[str]: ...
```

`rollout()` 返回的每个 dict 必须包含：

- `id`
- `hard`
- `soft`

`reflect()` 返回的每个 dict 通常包含：

- `patch`
- `source_type`: `failure` 或 `success`

### `BaseDataLoader` / `SplitDataLoader`

定义位置：`skillopt/datasets/base.py`。

`BaseDataLoader` 负责 batch planning：

```python
def build_train_batch(...)
def build_eval_batch(...)
```

`SplitDataLoader` 支持两种模式：

| `split_mode` | 说明                                     |
| ------------ | -------------------------------------- |
| `split_dir`  | 已有 `train/`、`val/`、`test/` 子目录         |
| `ratio`      | 从 raw dataset 按 `split_ratio` 生成 split |

### `BatchSpec`

表示 trainer 交给 adapter 的 batch 请求：

```python
@dataclass(slots=True)
class BatchSpec:
    phase: str
    split: str
    seed: int
    batch_size: int
    payload: object | None = None
    metadata: dict = field(default_factory=dict)
```

### `Edit` / `Patch`

定义位置：`skillopt/types.py`。

`EditOp`：

```python
Literal["append", "insert_after", "replace", "delete"]
```

`Patch` 是一组 edits，并可带 reasoning 和 ranking metadata。

### `RolloutResult`

trainer 会把 adapter 返回的 dict normalize 成 `RolloutResult`。硬要求仍是 `id`、`hard`、`soft`，额外字段进入 `extras`。

### `GateResult` / `GateAction`

定义位置：`skillopt/evaluation/gate.py`，表示 validation gate 的决策结果。

## 新增 Model Backend

`docs/guide/new-backend.md` 描述了一个基于 `ModelBackend` / `ModelResponse` 的新增 backend 流程：创建 `skillopt/model/your_backend.py`，实现 `generate()`，可选实现 `generate_with_tools()` 和 token counting，再在 registry 中注册，并通过 YAML 使用。

示意配置：

```yaml
model:
  backend: your_backend
  model_name: your-model-id
  temperature: 0.7
  max_tokens: 4096
```

凭据通过环境变量：

```bash
export YOUR_API_KEY="your-key"
```

不过 `docs/reference/api.md` 也说明：当前 model layer 实际通过 `model.optimizer_backend` 和 `model.target_backend` 选择后端，不是单纯通过 base-class registry 选择。支持的实际后端包括：

| Backend            | Optimizer | Target |
| ------------------ | --------- | ------ |
| `openai_chat`      | 支持        | 支持     |
| `claude_chat`      | 支持        | 支持     |
| `qwen_chat`        | 支持        | 支持     |
| `minimax_chat`     | 支持        | 支持     |
| `codex_exec`       | 不支持       | 支持     |
| `claude_code_exec` | 不支持       | 支持     |

因此新增 backend 时建议以当前源码 `skillopt/model/backend_config.py`、`skillopt/model/__init__.py` 和现有 backend 文件为准。

## 支持的 Benchmark

首页列出的 benchmark 包括：

- DocVQA
- ALFWorld
- OfficeQA
- SearchQA
- LiveMathBench / LiveMathematicianBench
- SWEBench
- 其他扩展 benchmark

对应 config 通常在：

```text
configs/<benchmark>/default.yaml
```

## 贡献流程

开发环境：

```bash
git clone https://github.com/microsoft/SkillOpt.git
cd SkillOpt
pip install -e ".[dev]"
```

Bug report 应包含：

- 复现步骤
- expected vs actual behavior
- 使用的 config，注意脱敏 API keys
- Python 版本和 OS

新增 benchmark checklist：

- data loader
- environment adapter
- config file
- registry
- docs update

新增 backend checklist：

- backend implementation
- backend registration
- `.env.example` 凭据说明
- docs update

文档使用 MkDocs Material：

```bash
pip install -e ".[docs]"
mkdocs serve
```

PR 流程：

1. fork repository
2. 创建 feature branch
3. 修改代码
4. 用现有 benchmark config 测试
5. 提交 PR，并写清楚说明

贡献默认采用 MIT License。

## 实践建议

- 如果只是使用内置 benchmark，优先从 `configs/searchqa/default.yaml` 或目标 benchmark 的默认 config 开始。
- 如果要调参，优先调 `batch_size`、`learning_rate`、`lr_scheduler`、`minibatch_size`、`analyst_workers`、`use_gate`、`use_slow_update`。
- 如果要扩展 benchmark，先写 tiny fixture 和 mock mode，再接真实模型。
- 如果要分析训练效果，重点看 `history.json`、`step_record.json`、`candidate_skill.md`、`best_skill.md`、`patches/*.json` 和 per-task `conversation.json`。
- 如果文档与源码有差异，应以源码和 `docs/reference/api.md` 的“Source of truth”说明为准。
