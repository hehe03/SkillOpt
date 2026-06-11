# searchqa opt-in workspace

这个 workspace 复用 `skillopt/envs/searchqa` 的数据格式、评估指标和反思主流程，同时把 rollout 的目标模型调用接到 `opt-in-harness`：

- `model.target: harness-default`：通过 `env.agent_backend` 调用 harness 默认模型，例如 `nga`。
- `model.target: <custom name>`：直接调用 `opt-in-harness/train/custom_model.py` 中同名自定义模型。
- optimizer 侧仍由 `opt-in-harness/train/train_in_harness.py` 统一接管。

训练入口：

```powershell
conda run -n llm python .\opt-in-harness\train\train_in_harness.py --config .\opt-in-harness\workspace\searchqa\configs\default.yaml
```

原始数据可以是单个 JSON/JSONL 文件，也可以是目录，例如：

```text
opt-in-harness/workspace/searchqa/data/raw/searchqa/
  train.jsonl
  dev.jsonl
  test.jsonl
```

当文件名或父目录包含 `train`、`dev`/`val`、`test` 时，`prepare_data.py` 会自动推断 split。否则按 `--split-ratio` 随机划分。

每条样本至少包含：

```json
{
  "id": "sample-1",
  "question": "...",
  "context": "...",
  "answers": ["..."]
}
```

可先用 `process/prepare_data.py` 切分数据到 `data/default_split/train|val|test/items.json`：

```powershell
conda run -n llm python .\opt-in-harness\workspace\searchqa\process\prepare_data.py --input .\opt-in-harness\workspace\searchqa\data\raw\searchqa --output-dir .\opt-in-harness\workspace\searchqa\data\default_split --split-ratio 70:10:0
```

`--split-ratio` 支持两类写法：

- `8:1:1`：权重模式，使用全部数据。
- `70:10:0`：百分比模式，只使用 80% 数据，剩余 20% 记录为 `unused`，不进入训练/验证/测试 split。
