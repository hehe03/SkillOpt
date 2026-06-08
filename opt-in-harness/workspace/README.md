# workspace 接入规范

`opt-in-harness/workspace/` 下每个一级目录对应一个待优化 skill。公共训练入口只负责加载配置和调用 SkillOpt；具体任务的数据格式、预测执行、评分方式和训练前后处理都应放在各自 workspace 内。

## 推荐目录

```text
workspace/<skill_name>/
  configs/default.yaml          # 该 skill 的 SkillOpt 配置
  data/                         # 已处理好的 split 数据，以及训练后评估输出
  init-skill/                   # 初始 Skill 文档；如需程序执行，也放初始预测脚本
  process/                      # 训练前/训练后脚本
  train/                        # 训练期适配层，默认消费已处理 split
  outputs/                      # 每次优化 run 的输出
```

## 新 skill 必备文件

最小可训练集合：

```text
workspace/<skill_name>/configs/default.yaml
workspace/<skill_name>/data/<split_name>/train/items.json
workspace/<skill_name>/data/<split_name>/val/items.json
workspace/<skill_name>/init-skill/initial_skill.md
workspace/<skill_name>/train/adapter.py
workspace/<skill_name>/train/evaluator.py
workspace/<skill_name>/train/rollout.py
workspace/<skill_name>/train/__init__.py
```

如果数据就是标准 split 格式，`adapter.py` 可以直接复用公共：

```python
from split_items_loader import StandardItemsDataLoader
```

只有当 split 文件不是 `items.json`，或样本需要额外归一化时，才需要在该 skill 自己的 `train/` 下新增 dataloader。

如果还要在训练后做测试集准确率比较，再准备：

```text
workspace/<skill_name>/data/<split_name>/test/items.json
workspace/<skill_name>/process/compare_*.py
```

如果目标 skill 在训练阶段需要用程序快速执行，而不是让 LLM 逐条阅读样本，还需要：

```text
workspace/<skill_name>/init-skill/<initial_executor>.py
```

并在 `rollout.py` 中实现“当前 Skill 文档 -> 可执行程序 -> 批量预测”的逻辑，或复用当前 skill 的实现方式。

## 配置要求

`configs/default.yaml` 至少需要声明这些 `env` 字段：

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
```

当前 `opt-in-harness` 默认优化前已经完成数据处理和 split 构建，因此 `data_path` 应保持为空，训练入口只使用 `split_dir`。训练入口会把 `out_root` 自动补成：

```text
workspace/<skill_name>/outputs/<skill_name>_<YYYYMMDD_HHMMSS>/
```

## 必备脚本职责

`train/adapter.py`：
连接 SkillOpt 和该任务，负责创建 dataloader、构造训练/验证样本、调用 rollout、调用 reflect，并提供任务专属的反思 prompt。

`opt-in-harness/train/split_items_loader.py`：
读取标准 `train/items.json`、`val/items.json`、`test/items.json`，返回 SkillOpt 可消费的 batch。标准格式的新 skill 可直接复用。

`workspace/<skill_name>/train/dataloader.py`：
可选。只有当该 skill 的 split 格式不是标准 `items.json`，或需要额外样本归一化时才需要。

`train/evaluator.py`：
把预测和 gold label 转成指标。多标签任务可同时输出样本级正确性和标签级缺失/多余信息，供 reflect 分析。

`train/rollout.py`：
执行当前 skill 并产出每个样本的 prediction/result。可以是 LLM 执行，也可以是“先生成脚本再批量执行”的程序执行模式。

`process/prepare_*.py`：
训练前数据处理脚本，负责生成训练入口直接消费的 split 数据。

`process/finalize_*.py`：
训练后导出脚本。把某次 run 的 `best_skill.md` 落成最终 skill，并按需要生成最终预测脚本。

`process/compare_*.py`：
训练后评估脚本，用于比较优化前后准确率。

`train/tests/`：
只放该 skill 适配层的局部测试或 harness 文件协议 demo，不是接入新 skill 的必需目录。

## 训练输入约定

训练入口默认读取：

- `configs/default.yaml`
- `data/<split_name>/train/items.json`
- `data/<split_name>/val/items.json`
- `init-skill/initial_skill.md`
- `init-skill/<initial_executor>.py`，仅当 rollout 需要程序执行
- `train/` 下该 skill 的适配代码
