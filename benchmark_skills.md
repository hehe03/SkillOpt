# SkillOpt Benchmark Skill 中文翻译

本文档对 `ckpt/` 中 GPT-5.5 优化后的 benchmark skill，以及 `skillopt/envs/*/skills/initial.md` 中对应初始 skill 做中文翻译。英文专有名词、路径、命令、标签和代码片段保持原样。

## ALFWorld

来源：

- 初始：`skillopt/envs/alfworld/skills/initial.md`
- 优化后：`ckpt/alfworld/gpt5.5_skill.md`

### 初始 Skill 翻译

# ALFWorld 具身 Agent Skill

## 概览

此 skill 用于指导 agent 在 ALFWorld 文本具身环境中行动。Agent 必须通过房间导航、物体交互和使用电器来完成家庭任务。每一步动作必须从系统提供的 admissible action list 中选择。

**输出格式**：始终先输出 `<think>...</think>` 作为推理，然后输出 `<action>...</action>` 作为所选动作。

## 任务类型

| 类型               | 目标                 | 关键步骤                                                 |
| ---------------- | ------------------ | ---------------------------------------------------- |
| Pick & Place     | 将物体 X 放入/放到容器 Y    | 找到 X -> 拿起 X -> 前往 Y -> 将 X 放入/放到 Y                  |
| Pick Two & Place | 将两个 X 实例放入/放到 Y    | 找到 X1 -> 拿起 -> 放置 -> 找到 X2 -> 拿起 -> 放置               |
| Examine in Light | 在 desklamp 下检查物体 X | 找到 X -> 拿起 X -> 找到 desklamp -> 使用 desklamp           |
| Clean & Place    | 清洁物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 sink -> 清洁 X -> 前往 Y -> 放置 X      |
| Heat & Place     | 加热物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 microwave -> 加热 X -> 前往 Y -> 放置 X |
| Cool & Place     | 冷却物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 fridge -> 冷却 X -> 前往 Y -> 放置 X    |

## 通用原则

1. **分解任务**：将目标解析为有序子目标，例如定位、获取、转换状态、交付。先完成当前子目标，再进入下一个。
2. **系统化探索**：每个表面和容器只搜索一次后再考虑回访。关闭的容器，如 drawers、cabinets、fridge，要先打开再判断为空。
3. **立即拿取**：当所需物体可见且可拿到时，离开前立即拿起。
4. **先转换再放置**：如果任务要求清洁、加热或冷却，要先在对应电器处完成状态转换，再前往最终目的地。
5. **直接交付**：一旦持有所需物体，无论是否已转换状态，都应直接前往目标容器并放置。
6. **跟踪进度**：内部记录仍需找到并放置的物体数量。只有计数归零后才停止搜索。
7. **避免循环**：不要连续重复同一个动作超过两次。如果卡住，移动到其他未探索位置。
8. **只选择 admissible actions**：始终从 admissible action list 中选动作，不要编造动作。

## 常见错误

- **重复访问已搜索位置**：记录已检查过的表面和容器，不要重复检查。
- **忽略可见物体**：如果目标物体出现在 observation 中，立即拿起。
- **跳过状态转换**：如果任务要求清洁、加热或冷却，不要在未转换前把物体放到目的地。
- **过早终止**：除非所有目标条件已确认满足，否则不要停止 episode。
- **动作循环**：反复 toggle 或 examine 同一物体会浪费步数。应转向新位置。

### 优化后 Skill 翻译

# ALFWorld 具身 Agent Skill

## 概览

此 skill 用于指导 agent 在 ALFWorld 文本具身环境中行动。Agent 必须通过房间导航、物体交互和使用电器来完成家庭任务。每一步动作必须从系统提供的 admissible action list 中选择。

**输出格式**：始终先输出 `<think>...</think>` 作为推理，然后输出 `<action>...</action>` 作为所选动作。

## 任务类型

| 类型               | 目标              | 关键步骤                                   |
| ---------------- | --------------- | -------------------------------------- |
| Pick & Place     | 将物体 X 放入/放到容器 Y | 找到 X -> 拿起 X -> 前往 Y -> 将 X 放入/放到 Y    |
| Pick Two & Place | 将两个 X 实例放入/放到 Y | 找到 X1 -> 拿起 -> 放置 -> 找到 X2 -> 拿起 -> 放置 |

### Pick Two 物体记账

对于 `pick_two_obj_and_place`，一旦某个目标容器实例已打开或可用，就选定它作为目标并记住。两个物体实例都应放入同一个已记住的容器。放置第一个物体后，不要再把它拿出来；如果第二个物体之前已经见过，应直接回到记住的位置，而不是随机搜索。如果两个物体不慎被分开放入不同容器，应把它们合并到选定的目标容器。

| 类型                      | 目标                 | 关键步骤                                                  |
| ----------------------- | ------------------ | ----------------------------------------------------- |
| Examine in Light        | 在 desklamp 下检查物体 X | 找到 X -> 拿起 X -> 找到 desklamp -> 使用 desklamp            |
| Examine in Light detail | 最终交互               | 当你拿着 X 且 desklamp 可见时，使用 desklamp；不要先尝试把 X 放到 lamp 上。 |
| Clean & Place           | 清洁物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 sink -> 清洁 X -> 前往 Y -> 放置 X       |
| Heat & Place            | 加热物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 microwave -> 加热 X -> 前往 Y -> 放置 X  |
| Cool & Place            | 冷却物体 X 并放入/放到 Y    | 找到 X -> 拿起 X -> 前往 fridge -> 冷却 X -> 前往 Y -> 放置 X     |

## 通用原则

1. **分解任务**：将目标解析为有序子目标，例如定位、获取、转换状态、交付。先完成当前子目标，再进入下一个。
2. **系统化探索**：每个表面和容器只搜索一次后再考虑回访。关闭的容器，如 drawers、cabinets、fridge，要先打开再判断为空。
- 先搜索语义上最可能的位置，再系统扩大范围：食物通常在 fridges、countertops 或 dining tables；餐具、厨具在 countertops、dining tables、stoveburners、cabinets 或 drawers；办公/卧室物品在 desks、shelves、dressers、sidetables 或 drawers；newspapers 在 coffeetables、sidetables、sofas 或 tvstands；洗漱/清洁用品在 sinks、bathroom counters、shelves、carts 或 cabinets 附近。
- 对 bread、mugs、cups、plates、bowls、utensils 等便携厨房目标，早期检查更广泛的开放表面：一两个 countertops 为空后，先尝试 dining tables 或其他开放表面，再打开大量 cabinets/drawers。对小型办公/卧室目标，在 drawers 与 exposed desks、shelves、sidetables、dressers 之间交替，而不是先穷尽 drawers。
- 维护一个持久的 **searched set**，记录精确容器实例，例如 `drawer 1`、`shelf 3`、`countertop 2`。一旦 observation 显示该位置没有目标物体，就标记为 searched，之后不要再称它为“未探索”。
  - 如果当前优先类别中的所有位置都已搜索，**扩大到任意未访问的 admissible `go to ...` 位置**，不要重启同一序列。必要时广泛搜索表面、家具、容器和电器。
  - 如果可见物体本身是可打开或类似容器的对象，如 box，且 opening/examining 是 admissible，应在离开前检查。
3. **立即拿取**：当所需物体可见且可拿到时，离开前立即拿起。
- 只拿取精确请求的物体类型。类似或相关物体，如任务要求 mug 时看到 cup、要求 knife 时看到 spoon、要求 pan 时看到 pot，都是干扰项；保持原位，并将该位置标记为已搜索目标。
4. **先转换再放置**：如果任务要求清洁、加热或冷却，要先在对应电器处完成状态转换，再前往最终目的地。
- 在拿到目标物体前，不要反复访问 sink、microwave、fridge 或最终目的地。如果提前找到电器，记住其位置，然后继续搜索未访问的物体位置，直到获得目标物体。
- 当直接的工具/电器命令可用时立即使用，例如 `clean X with sinkbasin`、`heat X with microwave`、`cool X with fridge` 或 `use desklamp`。除非所需动作不可用或打开是搜索/放置所必需，否则不要浪费步骤打开、关闭、toggle 或 examine 电器。
5. **直接交付**：一旦持有已转换或未转换的目标物体，直接前往目标容器并放置。
- 记住已知目的地容器，取到/转换后直接返回同一实例。如果目的地同时也是语义上可能的来源位置，应尽早检查/打开，而不是等到穷尽搜索后：食物可能已经在 fridge，utensils 可能在 diningtable，newspapers 可能在 sofa 上或附近，pick-two 任务中的目标 drawer 可以早打开。如果物体起始就在目的地但需要清洁、加热或冷却，应取出、转换，然后返回同一实例并放回。
6. **跟踪进度**：内部记录仍需找到并放置的物体数量。只有计数归零后才停止搜索。
7. **避免循环**：不要连续重复同一个动作超过两次。如果卡住，移动到其他未探索位置。
8. **只选择 admissible actions**：始终从 admissible action list 中选动作，不要编造动作。

## 常见错误

- **重复访问已搜索位置**：记录已检查过的表面和容器，不要重复检查。
- **忽略可见物体**：如果目标物体出现在 observation 中，立即拿起。
- **跳过状态转换**：如果任务要求清洁、加热或冷却，不要在未转换前把物体放到目的地。
- **过早终止**：除非所有目标条件已确认满足，否则不要停止 episode。
- **动作循环**：反复 toggle 或 examine 同一物体会浪费步数。应转向新位置。

### 困难搜索循环恢复

- **拿取前精确实例锁定排除**：某个 receptacle/surface 实例一旦被观察且不含目标物体，在仍处于搜索目标物体阶段时不要返回该精确实例。只有阶段变化，例如已拿着物体或需要最终交付，才是返回理由。
- **快速扩大阈值**：同一容器类别连续 3-4 次未命中后，切换到不同的可能类别或任意未访问 admissible location，不要继续或重启该类别，除非目标已在那里出现过。
- **不要因近期记忆重置搜索**：不要因为某位置最近几次 observation 没出现，就说它“未搜索”。searched set 对整个 episode 全局有效。
- **有限类别穷尽**：如果小类别的所有可见实例都已检查一次，例如所有 stoveburners、diningtables、countertops 或 shelves，就把该类别标记为对象搜索已穷尽，不要开始第二轮。记住一个可用目的地实例，然后搜索其他容器类别。
- **未访问优先于可能但已搜索**：多次未命中后，优先任何 admissible 的未访问 `go to`、`open` 或 `examine` 目标，而不是回访语义上可能但已搜索的位置。
- **拿取前的目的地表面**：如果目的地容器也是可能的来源位置，拿取前每个实例最多检查一次。如果没有目标，记住它作为最终目的地，但在目标已转换且准备放置前，停止把它当作搜索目标。
- **厨房物体 fallback**：对 cookware 和 dishware，明显的 burners/tables/counters 检查一轮后，扩大到未搜索的 cabinets、drawers、shelves、sinkbasins 以及其他厨房储物/表面，而不是在明显位置之间循环。

### 严格搜索账本动作过滤

每次空手搜索动作前，应用以下硬过滤：

1. 如果所需目标物体可见，立即拿取。
2. 否则选择一个当前 object-search 阶段尚未观察过内容的精确 receptacle/surface/container 实例。
3. 拒绝任何针对已观察且缺少目标的精确实例的 `go to`、`examine` 或 `open` 动作，即使它语义上可能、位置近、最近被提到，或属于最终目的地类型。
4. 如果所有可能实例都被账本拒绝，就扩大到任意未访问位置/类别，而不是从已搜索类别的实例 1 重新开始。

searched ledger 会跨越 inventory checks、电器访问、pick-two 任务中第一个物体放置，以及放下无关已检查物体/容器等事件保留。这些事件都不是从头重新扫描 shelves、drawers、cabinets、tables、counters 或 destination receptacles 的许可。

### 目的地作为来源时的锁定排除

当最终 receptacle 类型也是合理来源位置时，拿取前每个可见 destination 实例最多检查一次。如果缺少目标，就记住一个可用目的地实例，并将该精确实例从 object search 中锁定排除，直到你拿着所需物体准备交付。仍然空手时，不要在 destination instances 与其他已搜索 source instances 之间来回切换。

### Pick-Two 阶段记忆

放置第一个物体后，不要开始全新的房间/类别搜索。如果另一个所需实例之前已经见过，直接返回记住的来源位置拿第二个。如果未记住第二个实例，则沿用现有未搜索位置账本继续，而不是回访第一个放置前已经检查过的位置。

### Slow Update 翻译

保留成功模式：当精确请求的物体可见时，立即拿取；一旦正确命令 admissible，就执行所需的 clean/heat/cool/use 动作；然后直接交付到记住的目的地。

把工具位置当作工具，而不是反复搜索目标。如果 sinkbasin、fridge、microwave、desklamp 或 destination receptacle 已经检查过，且空手时不含目标，就记住它以备后用，但在持有所需物体或准备放置/使用前不要回访。

对每个编号类别使用 next-unsearched-instance 指针。如果离开 cabinets、drawers、shelves、countertops 或 stoveburners 后稍后返回该类别，应从尚未观察过的最低精确实例继续；绝不从实例 1 重启，也绝不回访已观察且缺少目标的实例。

对 pan-to-stoveburner 任务，按节省步数的顺序搜索：先快速检查 stoveburners 一轮，只为找 pan 或记住空目的地，然后在交付前离开 stoveburners。接着检查 countertops/islands 和 sinkbasins。然后按数字顺序优先检查 cabinets，打开每个 closed cabinet 并观察内容，再检查低收益 drawers。不要放弃 cabinet 搜索去回访已搜索的 stoveburners、countertops 或 drawers。

对 kettle/teapot clean-and-place 任务，检查明显 countertops/islands 后，检查 stoveburners 和 sinkbasins 一次，再按数字顺序检查 cabinets。如果若干 cabinets 为空，继续检查下一个未搜索 cabinet，或扩大到未访问 shelves/carts/dining tables；不要返回已搜索 countertops。记住一个打开/为空的 cabinet 作为最终目的地，但不要持续把已搜索 cabinets 当作搜索目标。

对 dishsponge clean-and-place 任务，检查 sinkbasin 和附近 countertops 一次，然后搜索未访问 cabinets、drawers、shelves、carts 和其他储物/表面。因为 sink 之后用于清洁，第一次访问后记住它；不要因为 sponge 可能在附近，就空手返回 sink。因为 shelf 是目的地，检查一次后记住可用 shelf；如果某 shelf 没有 sponge，继续只搜索未访问 shelves 或其他未访问位置，直到找到 sponge。

当步数预算紧张且仍然空手时，优先任何未访问 admissible location，而不是任何已搜索的可能位置。位置语义上可能、稍后有用或最近被提到，都不能成为拿取前重新扫描它的理由。

不要让扩大阈值导致类别重启。扩大意味着移动到不同未访问类别，或继续某个有希望储物类别的下一个未搜索实例；绝不意味着循环回已观察的精确实例。

## DocVQA

来源：

- 初始：`skillopt/envs/docvqa/skills/initial.md`
- 优化后：`ckpt/docvqa/gpt5.5_skill.md`

### 初始 Skill 翻译

# DocVQA Skill

## 视觉证据纪律

- 回答前仔细阅读文档。
- 优先选择能够回答问题的最小精确文本片段。
- 当附近有多个相似字符串时，选择周围标签或版式最匹配问题的那个。

## 精确答案纪律

- 尽可能从文档中精确复制姓名、数字和日期。
- 优先直接抽取，而不是改写。
- 最终作答前，将答案与附近替代项比较，保留证据支持最强的精确片段。

### 优化后 Skill 翻译

# DocVQA Skill

## 视觉证据纪律

- 回答前仔细阅读文档。
- 优先选择能够回答问题的最小精确文本片段。
- 对询问数值、计数、页码、日期或图表读数的问题，只返回被请求的值片段；除非问题明确要求，否则省略附近标签、类别名、单位或解释性文字。
- 当附近有多个相似字符串时，选择周围标签或版式最匹配问题的那个。

## 精确答案纪律

- 尽可能从文档中精确复制姓名、数字和日期。
- 对姓名和引用短语，保留文档的精确拼写和标点；当可见文本提供时，不要替换相似字母，也不要改变直/弯引号、空格或括号。
- 优先直接抽取，而不是改写。
- 最终作答前，将答案与附近替代项比较，保留证据支持最强的精确片段。

## 结构化版式查找

- 对表格，先找到问题中命名的行或条目，再读取所请求列、表头、日期或类别下的值；只回答该单元格。
- 对表单、收据或带标签字段，定位问题提到的精确角色、主体或字段标签，然后复制同一行、框、区块或紧邻字段中的填写值。
- 对目录、索引、编号或项目符号列表，匹配被请求的标题、条目或编号点，再沿同一行或列表项找到关联值；不要取附近其他项目的值。

## 锚定手写/邻近文本

- 对带有锚定词的手写、列表或表格问题，先定位锚定词，再检查同一行、同一列或附近边距中的紧邻文本。如果可辨认，提供证据最强的邻近片段，而不是留空。

## LiveMathematicianBench

来源：

- 初始：`skillopt/envs/livemathematicianbench/skills/initial.md`
- 优化后：`ckpt/livemath/gpt5.5_skill.md`

### 初始 Skill 翻译

# Live Mathematical MCQ Heuristics

## 选项比较

- 提交前比较所有选项。正确选项通常是问题所能支持的最强陈述，而相近干扰项可能更弱、过强，或遗漏等号情形。
- 跟踪精确定量词，例如 "there exists"、"for every"、"if and only if" 和 "exactly when"。

## 定理级精度

- 检查选项是否通过删除刻画、等号子句或完整等价性来弱化结论。
- 检查选项是否通过升级正则性、移除尺度限制，或把存在命题改成全称命题来夸大定理。

## 假设

- 仔细验证假设和定义域。干扰项常保留定理形状，但改变必要假设。
- 特别注意等号情形、极值条件，以及结果适用于整个族还是只适用于受限子族。

## 最终答案

- 最终答案只输出单个选项标签。

### 优化后 Skill 翻译

# Live Mathematical MCQ Heuristics

## 选项比较

### 关于更强结果的元选项

- 将 “one of the remaining options is correct, but a stronger result can be proven” 这类选项视为严肃候选，尤其当问题询问最强陈述时。
- 如果某个具体选项为真，但你的定理或推导给出了严格更强且未被精确列出的结论，应选择元选项，而不是较弱的具体陈述。
- 当选项按强度嵌套时，回答前明确排序：例如 finite-time blowup 强于仅仅 “not globally bounded”；positive stable growth 强于普通 unboundedness；更尖锐的常数、速率、例外集合界、端点包含或完整等价性，强于较弱的渐近版本。
- 提交前比较所有选项。正确选项通常是问题所能支持的最强陈述，而相近干扰项可能更弱、过强，或遗漏等号情形。
- 跟踪精确定量词，例如 "there exists"、"for every"、"if and only if" 和 "exactly when"。

## 定理级精度

- 除非定理明确证明，否则不要加入 converse、realization 或 classification claim。诸如 “conversely,”、 “every such parameter occurs,”、 “if and only if,” 或 “exactly all” 的说法，会把单向蕴含加强过头。
- 检查选项是否通过删除刻画、等号子句或完整等价性来弱化结论。
- 检查选项是否通过升级正则性、移除尺度限制，或把存在命题改成全称命题来夸大定理。

## 假设

### 精确条件和阈值

- 对 biconditional/equivalence 问题，拒绝仅必要或仅充分的条件。更宽泛的条件，例如 modulo 一个除数而非完整 modulus 的同余，通常更弱且不等价，除非定义域坍缩了额外情形。
- 对 threshold conditions，验证精确符号和端点：区分 \(\mu_0\) 与 \(-\mu_0\)、`<` 与 `\le`，以及等号情形属于正、零还是负参数区域。
- 当选项在 “for every” 与 “for sufficiently large”、局部与全局定义域、严格与非严格不等式、常数依赖性之间变化时，按逻辑强度排序，并匹配被证明的最尖锐版本。
- 仔细验证假设和定义域。干扰项常保留定理形状，但改变必要假设。
- 特别注意等号情形、极值条件，以及结果适用于整个族还是只适用于受限子族。

## 最终答案

- 最终答案只输出单个选项标签。

## 精确范围和定量表述

- 区分全局结论与局部化或完备化后的结论。经 localization、completion 或在每个 prime/scale 上成立的等价性，通常弱于无条件限定的等价性。
- 在 estimate-heavy 选项中，比较每个定量细节：指数、导数指标范围、常数及其参数依赖、log 因子、加性项、单边与双边记号，以及 pointwise 与 uniform convergence。

## OfficeQA

来源：

- 初始：`skillopt/envs/officeqa/skills/initial.md`
- 优化后：`ckpt/officeqa/gpt5.5_skill.md`

### 初始 Skill 翻译

# OfficeQA Skill

## 检索纪律

- 先缩小到最可能的候选文件，再阅读长段落。
- 优先使用包含问题中精确实体、时期、指标或表格概念的定向搜索词。
- 找到有希望的匹配后，只阅读小范围上下文，并验证其是否匹配请求的年份、口径和单位。

## 证据纪律

- 做任何算术前，先从检索文本中抽取精确值。
- 跟踪每个操作数的时期、单位和语义角色，避免混入附近的代理值。
- 如果问题要求转换后或派生数量，只有在确认每个操作数后才计算。

## 最终答案纪律

- 最终作答前，最后一次对检索证据做一致性检查。
- 从已检查值复制最终答案，而不是从未验证的中间猜测复制。

### 优化后 Skill 翻译

# OfficeQA Skill

## 检索纪律

- 当需要外部官方时间序列 observation 时，一旦识别出来源，应优先使用该来源的 series/data-download/table page。如果精确日期或猜测值搜索返回空结果，停止重复；扩大到官方 series name/code 加 `data` 或 `download`，并使用表格值。
- 将提供的/oracle 解析页面视为主要证据：如果其中包含相关表格和时期，先直接抽取，再搜索缺失的续页、缺失时期或页面中没有的官方实际值。
- 先缩小到最可能的候选文件，再阅读长段落。
- 优先使用包含问题中精确实体、时期、指标或表格概念的定向搜索词。
- 找到有希望的匹配后，只阅读小范围上下文，并验证其是否匹配请求的年份、口径和单位。
- 如果请求日期范围超出提供的/oracle 页面，先枚举所需时期，并验证证据中每个时期都存在。不要基于不完整台账计算或凭记忆填补缺失时期；应检索续页、相邻期刊或包含缺失日期/修订值的同表后续期。

## 证据纪律

- 做任何算术前，先从检索文本中抽取精确值。
- 跟踪每个操作数的时期、单位和语义角色，避免混入附近的代理值。
- 对 Treasury financing narratives，计算前给每个金额标注交易角色：offered amount、tenders/subscriptions received、tenders accepted、competitive/noncompetitive accepted、foreign 或 Government-account exchange tenders、refunding 和 **new cash** 不可互换。
- 货币或尺度转换前，先建立方向台账：源表单位、源货币、汇率方向（foreign currency per U.S. dollar 表示除以汇率；U.S. dollars per foreign unit 表示乘以汇率），以及请求的最终单位。
- 对表格，根据行标签和精确列标题对齐值，而不是只看接近程度；注意 continued 或 unlabeled columns、脚注、相邻金额列与百分比列、fiscal-year 与 calendar-year 区块，以及不同年份块下重复的月份行。
- 如果问题要求转换后或派生数量，只有在确认每个操作数后才计算。
- 对派生比较，保留问题措辞隐含的方向和符号：“change from A to B” 表示 B minus A；“former than latter” 表示 former minus latter；“share accounted for by X” 表示 X 除以指定 total；成对 “gap” 问题需要先计算每行内部差值再排序。
- 对统计、回归、相关性和增长率问题，计算前写出公式台账：确认精确 series/endpoints、有序向量、经过区间，以及请求约定，例如 continuously compounded rate、CAGR、Pearson correlation 或 OLS index/year choice。
- 对多阶段问题，如果一个表先决定另一个查找所用的时期/实体，要先用证据固定该派生 key，再只针对精确 month/year/reporting date/entity 检索第二个指标。
- 对 inclusive time-series ranges，建立覆盖每个请求月/年的 period-by-period ledger，每个时期恰好一次，并保留 calendar 与 fiscal 口径、end-of-month 或 end-of-fiscal-month 状态、源单位和指定调整。
- 对时间序列窗口上的统计变换，精确确认端点包含/排除；趋势回归适当使用连续时间索引；计算 median 前排序；对 logarithmic growth 使用 `ln(final/initial)` 后再转换为请求的百分比格式。

## 最终答案纪律

- 最终作答前，强制匹配请求的单位和格式：按需转换 thousands/millions/billions 或完整 nominal dollars，然后严格应用 no-comma、fixed-decimal、whole-number 或 nearest-tenth/thousandth 格式。
- 最终作答前，最后一次对检索证据做一致性检查。
- 从已检查值复制最终答案，而不是从未验证的中间猜测复制。

## 统计和时间序列计算检查

- 计算任何统计量前，写出预期公式和分母约定。如果 prompt 明确说 **population standard deviation**，除以 `n`；如果说 **sample**，除以 `n-1`；如果 z-score 是把一个 observation 与一小组比较月份/时期对比且未说明 population 约定，则用比较集的 **sample** standard deviation 估计离散度。中间操作数、加权平均、logs、汇率转换或标准差不要在最终请求舍入前提前舍入。
- 对长 inclusive ranges，先枚举预期 observation 数量和首末时期，再验证台账恰好有该数量。排除 totals、cumulative-to-date columns、comparable-period columns、estimates，以及请求 calendar/fiscal range 之外的额外 latest-month columns。
- 当页面包含多个标签相近的邻近 section 时，只使用标题和行标签精确匹配请求指标的 section；如果请求的 measure/table title 缺失或只部分显示，不要从第一个可见表格计算。
- 对 Treasury security quotations，遵守表格报价口径。如果表格说明价格小数是 32nds，则将 `99.27` 转成 `99 + 27/32`，不要当作十进制 `99.27`。如果任务要求使用 period-specific exchange rates 在目标货币中平滑、平均或预测，除非 prompt 明确说在源货币中计算并只转换最终结果，否则先将每期 observation 转成目标货币。

## 更严格的最终格式

- 精确匹配任何请求的输出模板。除非 prompt 明确要求单位词或解释文本，否则只返回数值或请求列表；不要附加 `million`、`dollars`、`percent` 或 `percentage points` 等词。只有在 prompt 要求货币格式输出或答案格式明显需要时，才包含符号/逗号。

## SearchQA

来源：

- 初始：`skillopt/envs/searchqa/skills/initial.md`
- 优化后：`ckpt/searchqa/gpt5.5_skill.md`

### 初始 Skill 翻译

# Question Answering Skill

尚未学习到规则。规则会通过 reflection process 添加。

### 优化后 Skill 翻译

# Question Answering Skill

尚未学习到规则。规则会通过 reflection process 添加。

## 简洁答案归一化

- 优先最短且无歧义、能直接满足问题的答案。除非问题特别要求完整官方名称，或描述词对识别实体是必要的，否则不要包含通用描述词、法律后缀或扩展正式名称。
- 如果答案出现在更长的描述短语中，删除那些只是重复 clue 所请求类型或修饰语的词。对短答案 trivia，返回有区分度的核心实体或中心词，而不是角色头衔、产品风味形容词或地点/设施类型词；即便这些词属于更完整的官方短语，除非明确要求完整官方名称。
- 对 place/name-etymology 问题，如果询问 “the name” 或 “the word” 表示某含义，回答有区分度的名称/单词本身，而不是带通用类型标签的更大短语。
- 对自然地理特征，如果 `Lake`、`River`、`Bay`、`Gorge`、`Mount` 或 `Island` 等传统 feature designators 是专名的一部分或匹配请求特征类型，应保留。不要为了简洁把 `Lake Okeechobee`、`Tampa Bay` 或 `Olduvai Gorge` 缩短成有歧义的 base name。
- 对 companies、brands 和 organizations，如果常用有区分度名称足够，就回答该名称；除非明确要求，否则省略 `Company`、`Corporation`、`Inc.` 等附加词。
- 当精确变体不同时，保留最强证据支持的答案表面形式：拼写、大小写、标点和词序可能重要。如果直接 title/snippet/answer field 给出预期形式，不要替换为等价官方/常用变体，例如另一拼写或倒置的机构名。
- 复制标题或引用名时，保留证据中的普通 ASCII 标点，尤其是直 apostrophe (`'`)。除非证据明确显示该风格化形式，否则不要替换成 typographic curly quotes/apostrophes。
- 对 nicknames、epithets、saints 和 quoted titles，精确复制支持的表面形式，包括空格、大小写和 `St.` 等常规缩写。不要把风格化或引用形式规范成小写词典词或扩展拼写。
- 对 trivia 或 crossword-style clues 中的人名答案，优先使用有证据支持的常规姓名。只有当 clue/source 明确期待短形式时，才只使用姓、名或 saint/regnal name；否则使用最强证据或 answer field 中的 canonical full personal name，尤其当单独 given name 有歧义时。
- 返回 clue 所期待的语法基本形式。不要仅因 crossword source 将共享姓名或类别复数化，就添加复数 `s`；如果 clue 列出共享 first name 的人，回答单数 given name。
- 对 common-noun category answers，即使 clue 为语法使用 `these`、`those`、`places` 或 `items` 等复数词，trivia/crossword-style clues 默认回答单数字典 headword。只有当术语本身天然复数，或 answer field/source 明确给出复数短语时才使用复数。
- 对“被替代、被另一系统/物品代替或取代”的 common-noun clues，回答被替代事物的宽泛 headword，除非 clue 或 answer field 需要限制性修饰语。不要仅因解释上下文出现就添加 `letter`、`regular` 或 `standard` 等形容词。
- 对使用 `this` 或 `that` 的填空或定义类 clue，提供可独立存在的 noun phrase。避免使用源文本中依赖上下文的代词或所有格；必要时使用自然冠词，如回答 `the highest point`，而不是 `its highest point`。

## 基于上下文的证据匹配

- 首先识别问题中最有区分度的词：专名、日期、标题、引用短语、不寻常词、角色、关系和类别描述。
- 优先选择多个有区分度 clue terms 同时出现的 passages 或 document titles，尤其是措辞直接重复或接近改写问题的证据。
- 将 document titles 视作有用证据：答案常在 title 中命名，而 snippet 确认 clue facts。
- 不要假设 document title 本身就是答案。如果请求类型不同于 title entity，把 title 当上下文，并从 snippet 或 clue relationship 中抽取匹配类型的实体。
- 对 `known as`、`called`、`defined as` 或 category/type clues，选择最强 matching title/snippet 或 scraped answer field 中明确使用的 canonical term，不要从 clue wording 中发明相关派生词或近义词。若多个候选都合理，优先证据直接陈述请求关系并重复最多有区分度 clue facts 的候选。
- 忽略只匹配通用词的噪声结果；优先证据直接把 clue facts 连接到某个具体实体的结果。

## Clue 解释和答案类型

- 对 Jeopardy-style 措辞，如 `this man`、`this group`、`this film`、`this country`、`this system`、`he` 或 `his wife`，先推断预期答案类型再选择答案。
- 用该预期类型验证候选：回答 clue 请求的简洁 person、place、title、organization、object、term 或 phrase。
- 附着在请求类型上的修饰语是硬过滤条件，不是背景信息：如 dates、`largest`、`-letter-named`、`1978 remake`、`hot dog brand`、`dual throne` 或 `on this company’s board` 等约束，都必须与候选匹配。
- 对 books、films、plays、songs、poems 等 creative works 相关 clue，先判断问题问的是作品本身、创作者、表演者/演员、角色、引用来源还是场景。`wrote`、`directed`、`stars`、`played`、`set in` 等动词，以及 `he` 或 `her` 等代词，通常决定目标。
- 对带 `this`、`these` 或 `one of these` 等 placeholder 的填空式 clue，将每个候选代回 clue，选择能让完整短语、标题或事实读起来正确的简洁答案。
- 对只是示例或以逗号、斜杠或 `or` 分隔名称的简短 clue，推断连接它们的共享类别、类别层级或同义词，然后回答该简洁 common term。
- 对 crossword-style clues，将括号数字或指定字母数视为答案长度硬约束，并省略会违反长度的通用标签。对 `X, or what Y does` 这类双定义 clue，选择同时满足两个含义的单词，并保留所需屈折形式。
- 如果 clue 引用了不可用图片或链接，如 `seen here`、`pictured` 或括号视觉提示，依赖文本 clue 和上下文推断答案；不要把缺失图片视为必要证据。
- 如果多个 snippets 支持同一实体，用这种相互印证来选择答案的 canonical/common form。

## Trivia / Jeopardy Snippet 格式

- 检索到的 trivia snippets 可能包含 scraped 格式中的 clue 和 answer，例如 `CATEGORY | clue | answer`、`clue. ANSWER` 或 `right:` 标签。
- 当问题文本匹配这种 snippet 中的 clue 时，抽取 answer field 或相邻 answer name，而不是 category 或整个 clue 句子。

## 常见 Clue 陷阱

- 注意反向关系：如果 clue 说 `His third wife was Jiang Qing`，请求答案是丈夫，而不是 Jiang Qing。
- 更一般地，保留 clue 中的关系方向：`A is evidence of this B`、`A is related to this language` 或 `home to these characters` 问的是关系目标，不是 clue 中已经命名的实体。
- 当 clue 说 examples、models、breeds、members 或 items `include`、`like` 或 `such as` 某些命名实体时，把这些名称作为请求父类或实体的证据。回答 `this` 请求的总体 brand、animal、category、place 或 term，而不是已经给出的示例之一。
- 如果问题给出 quotation 或 phrase 的开头，回答上下文中精确缺失的后续内容。
- 对 song、poem、nursery-rhyme 或 quotation clues，先判断问题是在问 quote 中缺失的 word/phrase，还是相关 creator、performer 或 work；用代词和 answer-type signals 选择正确目标。
- 当 clue 要求受约束形式，例如 first name、abbreviation、acronym 或 lyric word，返回该精确形式，而不是更完整的人名、标题或解释；保留作为请求形式一部分的常规标点或拼写。
- 如果 clue 包含 wordplay、quotation marks 或 puns，将它们作为提示，但答案应是真实且有证据支持的实体。
- 如果 clue 包含 quoted title、quoted narration or lyric、named event、slogan 或其他有区分度短语，但询问相关 `this` entity，应把 quote 或 name 作为证据来识别被请求的 person、work、place、group、category、source 或 term；除非 clue 明确询问它，否则不要返回 quoted anchor。

## SpreadsheetBench

来源：

- 初始：`skillopt/envs/spreadsheetbench/skills/initial.md`
- 优化后：`ckpt/spreadsheetbench/gpt5.5_skill.md`

### 初始 Skill 翻译

# Spreadsheet Manipulation Skill (xlsx)

## 概览

此 skill 指导 agent 使用 Python 操作 Excel (`.xlsx`) 电子表格。

**主要库**：`openpyxl` 用于保持结构地读写，`pandas` 用于数据转换。不要使用任何其他第三方库。

## 通用工作流

1. **探索** 输入文件：列出 sheets，检查 headers，检查尺寸。
2. 编写 `solution.py`，在顶部定义 `INPUT_PATH` 和 `OUTPUT_PATH`。
3. 执行 `python solution.py` 并验证输出文件已创建。
4. 确认目标 cells/range 包含预期值。

## 库选择

| 使用场景                                | 库                           |
| ----------------------------------- | --------------------------- |
| 保留 formulas、formatting、named ranges | `openpyxl`                  |
| 批量数据转换、聚合、排序                        | `pandas` -> 用 `openpyxl` 写回 |
| 简单单元格读写                             | `openpyxl`                  |

**警告**：`pandas.to_excel()` 会静默破坏现有 formulas 和 named ranges。写回包含公式的电子表格时，始终使用 `openpyxl.save()`。

## `solution.py` 模板

```python
import openpyxl
import pandas as pd

INPUT_PATH  = "..."   # set to the actual input path
OUTPUT_PATH = "..."   # set to the actual output path

wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"]

# --- perform manipulation ---

wb.save(OUTPUT_PATH)
```

## 输出要求

- 将结果保存到 `OUTPUT_PATH`。
- 不要硬编码行数或列字母；应遍历 workbook 中的实际行。
- 保留 instruction 未提及的 sheets 和 cells。

### 优化后 Skill 翻译

# Spreadsheet Manipulation Skill (xlsx)

## 概览

此 skill 指导 agent 使用 Python 操作 Excel (`.xlsx`) 电子表格。

**主要库**：`openpyxl` 用于保持结构地读写，`pandas` 用于数据转换。不要使用任何其他第三方库。

## 通用工作流

1. **探索** 输入文件：列出 sheets，检查 headers，检查尺寸。
- 检查 preview 之外的实际 workbook 数据，包括附近 rows/columns、sample outputs、formulas、labels、headers，以及 `Output`、`Manual Result` 或 `Desired...` 等 reference/example sheets。
- 将请求输出区域或相邻示例表中已有的填充 cells 视为边界情况和预期格式的语义示例，但仍要重新计算并写入完整请求目标范围。
  - 扫描 used range 中完整的 header groups，而不只看 row 1。表格可能从较晚 rows/columns 开始，顶部有 title rows，或同一 sheet 上有多个 source/result tables；使用附近 labels 和请求 output range 区分 sources 与 destinations。
  - 通过 header text、附近 labels 和 surrounding nonblank structure 定位 tables、fields 和 target ranges，而不是固定坐标。必要时从实际 cells 构建 header maps，例如 `{str(cell.value).strip(): cell.column}`。
2. 编写 `solution.py`，在顶部定义 `INPUT_PATH` 和 `OUTPUT_PATH`。
3. 执行 `python solution.py` 并验证输出文件已创建。
4. 确认目标 cells/range 包含预期值。

## 库选择

| 使用场景                                | 库                           |
| ----------------------------------- | --------------------------- |
| 保留 formulas、formatting、named ranges | `openpyxl`                  |
| 批量数据转换、聚合、排序                        | `pandas` -> 用 `openpyxl` 写回 |
| 简单单元格读写                             | `openpyxl`                  |

**警告**：`pandas.to_excel()` 会静默破坏现有 formulas 和 named ranges。写回包含公式的电子表格时，始终使用 `openpyxl.save()`。

**公式求值注意**：`openpyxl` 可以写公式，但**不会**计算公式或更新缓存结果。如果请求输出会按 cell values 检查，应在 Python 中计算结果并写入 literal values，除非用户明确要求 live formulas。当现有公式作为逻辑输入时，使用 `data_only=True` 加载第二个 workbook 读取 cached values，同时通过正常 workbook 保存修改：

```python
wb = openpyxl.load_workbook(INPUT_PATH)
wb_values = openpyxl.load_workbook(INPUT_PATH, data_only=True)
ws = wb["Sheet1"]
ws_values = wb_values["Sheet1"]
```

将 `write/fix a formula`、`SUMIFS/COUNTIFS`、`VBA` 或 `macro` 等措辞视为 spreadsheet logic 的描述，除非 deliverable 明确要求 live formula text、`.xlsm` 或保留 VBA project。对普通 `.xlsx` 输出，用 Python/openpyxl 实现等价逻辑，并将计算后的最终值写入请求 cells，使验证不依赖 Excel 重新计算或 macros。

当用户提供现有或损坏公式时，将它作为语义 specification：遵守其 referenced lookup ranges、criteria ranges、return ranges、aggregation intent 和 error-handling behavior，然后写入结果值，不要猜测不同 source columns 或留下未求值公式。

## `solution.py` 模板

```python
import openpyxl
import pandas as pd

INPUT_PATH  = "..."   # set to the actual input path
OUTPUT_PATH = "..."   # set to the actual output path

wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"]

# --- perform manipulation ---

wb.save(OUTPUT_PATH)
```

## 输出要求

- 将结果保存到 `OUTPUT_PATH`。
- 不要硬编码行数或列字母；应遍历 workbook 中的实际行。
- 保留 instruction 未提及的 sheets 和 cells。

## 匹配与目标范围卫生

- 根据 instruction 和 examples 选择比较运算符：`begins with` 用 `startswith`，`contains/search/occurrence` 用 substring search，仅当暗示 whole-cell match 时才使用精确归一化相等。
- 为比较和数值解析创建小 helper functions。文本归一化时 trim、折叠重复 spaces/NBSPs，并 casefold；当名称或标签存在标点/空格不一致时，考虑 punctuation-insensitive keys。数值文本解析时移除逗号/货币符号，同时保留符号和小数点；跳过 `None`/blank 和 booleans，并有意识地处理 `"-"`、`"$"`、`"$0"`、blanks 和 numeric zero。
- 有意识地归一化 date keys：处理 `datetime`/`date` objects、Excel serial numbers 和 date-like strings，再按任务暗示粒度比较，如 exact date、month、month/year、fiscal period 或 year。对 workday/date-window 逻辑，在 Python 中计算范围，并按要求排除 weekends/holidays。
- 对 monthly 或 period summary grids，从所有来源规范化 period labels：sheet names、title text、row/column headers、`March` 等文本月份，以及实际 date cells。按 normalized period 加其他指定条件匹配 summaries，而不是按固定月份偏移或现有公式。
- 对 date ranges 和 rolling windows，根据措辞和 examples 推断 endpoint inclusivity。`X to Y`、`through`、`up to` 等短语，或 `2 to 5` 表示 `4 days` 之类示例，通常要求包含边界。
- 对 time extraction 或 time-threshold logic，将 `datetime`、`time`、Excel serial/fractional times 和 time-like strings 解析为真实 Python `time`/`datetime`。写入真实 time values，并设置 Excel `number_format`，例如 `hh:mm:ss AM/PM`；当结果应作为时间行为时，不要写文本子串。
- 对 joins、deduplication、grouping、interval lookups、lookup grids 和 ordered outputs，构建明确 normalized keys，涉及多个字段时使用 composite keys。除非明确要求排序，否则保留每组原始 source order。
- 对依赖其他 rows 或 lookup grids 的输出，先第一遍建立 normalized dictionaries/groups/range structures，再第二遍写结果。避免每行做嵌套全表扫描；拆分 delimited tokens 并忽略空 token；当任务提及时，将 `#N/A` 等错误字面量视作有意义 sentinel。
- 对 lookups、filters、joins 和 label/header matching，一致地归一化比较 keys：trim whitespace、明确跳过 blanks、适当使用 case-insensitive text matching，并一致处理 numeric-looking IDs，如 `330`、`330.0` 和 `"330"`。保持 numeric outputs 为数值；用 `number_format` 控制显示格式，除非明确要求文本，否则不要把数字转成字符串。
- 替换生成的 output area 时，只清除 instruction 指定的 target range，再写入新结果，避免 stale values/formulas 残留。除非明确要求，否则保留 formatting、column widths、borders、formulas 和无关 cells。
- 如果 instruction 包含 formatting changes，写入 values 后只对请求 cells/range 精确应用。使用 `openpyxl` styles 设置 fills、alignment、fonts、borders 和 number formats；必要时把 hex colors 转成 ARGB，例如 `#FFC000` -> `FFFFC000`。对 `format as text`，设置 `number_format = '@'`，并在预期 cell values 为文本时写入 string values。
- 当 instruction 命名 destination range 或 columns 时，直接把派生结果写到那里。除非明确要求结构变化，否则不要插入 rows/columns、迁移 source table 或排序/删除 source records。
- 对 filtered lists、summaries 和 aggregations，先在内存中收集全部 source records/results，保留所需顺序，再从第一个 output row 开始写，并清除 target columns 中新结果下方残留 cells。添加 rows 时，适当复制现有 template row 的 style/alignment/number format；删除 rows 时从底部向上删，避免 row-index shifts。
- 保留有意空白为空 cells (`None`)，不要写 placeholder text 或 `0`，除非任务指定。
- 对 numeric aggregation、crosstab、SUMIFS-like 和 INDEX/MATCH-style summary outputs，根据表格语义和 examples 推断 missing-match behavior：numeric summary grids 通常需要 literal `0` 表示无匹配记录，而 filtered lists 或 `show only once` 输出通常需要 blanks (`None`)。
- 对 blank-sensitive logic，如 `if input is blank, output blank`，当驱动输入本身可能是公式时用 `data_only=True` 评估，并对真正空白输出写 `None`，不要依赖新公式返回 `""`。

## 简单填充任务的鲁棒性

- 除非任务确实需要 unsupported workbook internals，否则优先使用简单、可审计的 row/column loops，而不是复杂 workbook XML parsing。返回前运行脚本一次，捕获 syntax/indentation errors，并验证代表性 target rows 确实已写入。

### Slow Update 翻译

当用户要求 formula、macro、VBA code 或修复 Excel formula 时，仍要交付完成后的 workbook state：在 Python 中计算预期结果，并将 literal final values 写入请求 cells。除非任务明确说输出必须包含 live formulas，否则不要写公式字符串。

写入后，重新加载或检查已保存 workbook，并验证每个请求/评估目标 cell 在期望值的地方包含 non-formula literal。如果某个目标 cell 意外仍是 `None`，完成前修复脚本。

将 workbook 中现有公式作为 examples/specifications，而不是输出。如果 cell 包含 `=A25` 或 INDEX/MATCH/SUMIFS 模式等 reference formula，解析它引用的 source cells/ranges/criteria，自己计算结果，并用 referenced 或 calculated value 覆盖 destination。

对 blank-sensitive formula tasks，显式计算分支：如果 driving source cell 真的为空，写 `None`；否则写实际结果，例如 `0`、`1`、category label 或 lookup value。不要依赖 `IF(...,"",...)` 公式稍后重新计算。

对 lookup/category tasks，通过 headers 和 nearby labels 同时定位 input rows 和 lookup table。支持 exact keys、numeric-looking keys 和 interval/range tables；然后填充每个有 driving input 的 destination row，而不只是第一个可见示例。

对 `every nth row` 或 OFFSET-style tasks，根据 examples 或 formulas 推断 source column、first source row 和 step，然后将实际 source values 作为 literals 复制到请求 output range。

对 schedule/calendar fill tasks，先从 schedule/template area 构建 cycle-day-to-periods mapping，再根据每行 cycle day 跨所有请求 class columns 填充 daily rows。保留 template 中显示的 repeated/double periods；不要在 schedule cells 中留下公式。

对第一行可用但后续行失败的 INDEX/MATCH 问题，将 row labels、column/year headers、region/type criteria 和 expense/category labels 视为 multi-key lookup。使用 source data table 中的值填充整个 result matrix；当 source cells 是公式时，使用 cached `data_only` values。

对 multi-step macro/VBA-style requests，实现 workbook 中每个明确操作，而不只是第一个删除/筛选步骤。保存前重新阅读 numbered requirements，并验证后续 computed columns、totals 和 derived fields，以及显眼的 filtered rows。

当 target range 包含 `Total`、`Grand Total`、`min`、`max`、constraints、headers 或 blank separators 等特殊 rows 时，不要把普通行逻辑盲目应用到这些 rows。按指示将 totals 计算为 aggregates，并保留 constraint/header/blank cells，除非明确要求修改。

对 residual-balancing tasks，将 data rows 与 min/max constraint rows 分开识别。正 residual 从 unit 1 向 unit 5 增加，且不超过 max values；负 residual 从 unit 5 向 unit 1 减少，且不低于 min values；只更新实际 data rows 中的 unit cells。

对 time-threshold rows，逐行判断它是 normal data row 还是 summary row。普通行使用 before/after threshold rule；如果 workbook labels 或 examples 表明 summary row 是 total，则 summary row 应聚合已计算的普通行结果。

保持 scripts 足够简单，确保能干净运行。避免不必要的动态代码生成，以及在 f-strings 中嵌入 regex expressions 的脆弱写法。始终执行最终 `solution.py`；修复任何 syntax、indentation 或 runtime error，然后验证代表性 target cells。

如果 workbook cells 包含任意 sample text，可能敏感或触发内容过滤，不要在回复中引用大量原始 cell 内容。用中性变量名在 Python 本地处理，只输出完成后的 script/workbook changes。
