# SkillOpt Benchmark 优化修改报告

本文档概述每个 benchmark 从 `skillopt/envs/*/skills/initial.md` 到 `ckpt/*/gpt5.5_skill.md` 的主要修改点。重点描述优化后的 skill 新增了哪些约束、流程、错误恢复和任务特化策略。

## 总览

| Benchmark              | 初始状态              | 优化后核心变化                                                                           |
| ---------------------- | ----------------- | --------------------------------------------------------------------------------- |
| ALFWorld               | 已有完整任务类型和通用探索原则   | 增加精确实例搜索账本、目的地/工具锁定、pick-two 阶段记忆、困难搜索循环恢复和若干任务特化搜索顺序                             |
| DocVQA                 | 简短的视觉证据与精确抽取规则    | 增加值类问题最小答案、表格/表单/列表结构化定位，以及手写/邻近文本锚定                                              |
| LiveMathematicianBench | 通用 MCQ 定理精度与假设检查  | 增加“更强结果”元选项判断、嵌套强度排序、阈值端点和定量估计细节检查                                                |
| OfficeQA               | 基础检索、证据和最终答案纪律    | 扩展为官方数据源检索、完整时间范围台账、表格角色对齐、统计/汇率/时间序列计算和严格格式控制                                    |
| SearchQA               | 初始无 learned rules | 新增完整的短答案归一化、证据匹配、clue 类型推断、snippet 格式解析和常见 clue 陷阱处理                              |
| SpreadsheetBench       | 基础 Excel 操作工作流    | 增加 workbook 深度探索、公式求值策略、匹配/目标范围卫生、日期时间/lookup/aggregation 鲁棒性和任务特化 slow-update 经验 |

## ALFWorld

### 修改范围

ALFWorld 的初始 skill 已包含任务类型、分解目标、系统探索、状态转换、直接交付和避免循环等基本原则。优化后没有推翻原结构，而是在容易失败的“搜索循环”和“多阶段记忆”上加了更强的执行约束。

### 主要修改点

- 新增 `Pick Two Object Bookkeeping`：要求两个物体放入同一目标容器，放置第一个后不能移除；如果第二个物体已见过，应直接返回其记忆位置。
- 新增 `Examine in Light detail`：明确拿着目标物体且 desklamp 可见时直接 `use desklamp`，不要把物体放到 lamp 上。
- 扩展系统探索策略：从“每个位置搜索一次”细化为按语义可能性排序，并针对厨房、办公、卧室、报纸、洗漱清洁用品等类别给出优先位置。
- 新增持久 `searched set`：用 `drawer 1`、`shelf 3`、`countertop 2` 等精确实例记账，防止把已搜过的位置误认为未探索。
- 新增搜索扩大规则：同类位置多次未命中后，应切换到其他类别或任意未访问 admissible location，而不是重启原类别。
- 新增精确物体类型约束：只拿取任务请求的准确物体，避免 mug/cup、knife/spoon、pan/pot 等相似物体混淆。
- 新增工具位置处理：sink、microwave、fridge、desklamp 和最终目的地被找到后应记住，但拿到目标前不要反复访问。
- 新增直接命令优先：当 `clean X with sinkbasin`、`heat X with microwave`、`cool X with fridge` 或 `use desklamp` 可用时立即执行。
- 新增 `Hard Search-Loop Recovery`：包含拿取前实例锁定、3-4 次未命中后的快速扩大、全局搜索账本、防止有限类别重复搜索等。
- 新增 `Strict Search Ledger Action Filter`：每次空手搜索前先检查目标是否可见，再拒绝已观察且无目标的精确实例。
- 新增 `Destination-as-Source Lockout`：当最终容器也可能是来源时，拿取前每个目的地实例最多检查一次，之后锁定为交付目的地。
- 新增 `Pick-Two Phase Memory`：放置第一个物体后沿用已有搜索账本，不重新开始全局搜索。
- Slow update 增加任务特化策略：如 pan-to-stoveburner、kettle/teapot clean-and-place、dishsponge clean-and-place 的高效搜索顺序。

### 优化意图

优化重点是减少 ALFWorld 中最常见的无效行为：反复搜索同一实例、把工具地点当搜索地点、忘记已见过的第二个物体、在目的地和来源之间循环，以及在厨房任务中按低效顺序搜索。

## DocVQA

### 修改范围

DocVQA 初始 skill 只有通用视觉证据纪律和精确答案纪律。优化后新增了面向文档版式的结构化查找规则，并强化值类问题的答案边界。

### 主要修改点

- 新增值类答案边界：询问 value、count、page number、date 或 graph reading 时，只返回请求值，避免携带标签、单位或解释性文字。
- 新增精确保留表面形式：姓名和引用短语要保持文档中的拼写、标点、空格、括号和引号形式。
- 新增表格定位规则：先定位问题命名的行或条目，再读取目标列、表头、日期或类别下的单元格。
- 新增表单/收据字段规则：根据角色、主体或字段标签，在同一行、框、区块或相邻字段抽取填充值。
- 新增列表/目录/索引规则：匹配标题、条目或编号后，沿同一行或同一列表项读取关联值。
- 新增手写/邻近文本锚定：先定位 anchor term，再读同一行、列或附近边距中的可辨认文本。

### 优化意图

优化重点是解决 DocVQA 中“答案边界过宽”和“取错邻近字段”的问题，让模型先定位结构位置，再抽取最小值片段。

## LiveMathematicianBench

### 修改范围

初始 skill 已要求比较选项、注意 quantifiers、检查定理强弱和假设。优化后针对数学选择题中“哪个陈述最强/最精确”的陷阱做了更细粒度的逻辑排序。

### 主要修改点

- 新增 `Meta-Options About Stronger Results`：把“其他某选项正确但可证明更强结果”这类元选项纳入严肃候选。
- 新增强度排序：当选项嵌套时，显式比较 finite-time blowup、unboundedness、常数、速率、端点、等价性等强弱。
- 新增防止过度补全：除非定理明确证明，不要加入 converse、realization 或 classification claim。
- 新增 biconditional/equivalence 检查：拒绝仅必要或仅充分的条件。
- 新增阈值端点检查：区分 \(\mu_0\) 与 \(-\mu_0\)、`<` 与 `\le`，并判断等号情形属于哪一侧。
- 新增逻辑强度对比：比较 `for every` 与 `for sufficiently large`、local 与 global、strict 与 non-strict、常数依赖性。
- 新增全局/局部范围区分：localization、completion 或 prime/scale 上的等价通常弱于无条件全局等价。
- 新增 estimate-heavy 细节检查：指数、导数范围、常数依赖、log 因子、加性项、单边/双边记号、pointwise/uniform convergence。

### 优化意图

优化重点是减少数学 MCQ 中“选了真但不够强的选项”或“把单向定理误读为双向/分类定理”的错误，提高对精确假设、端点和定量措辞的敏感度。

## OfficeQA

### 修改范围

OfficeQA 初始 skill 只有基础检索和计算前证据确认。优化后显著扩展为适合官方报表、时间序列、金融财政数据和复杂统计问题的工作流。

### 主要修改点

- 新增官方时间序列检索策略：优先 official series/data-download/table page；精确日期搜索失败时扩大到 series name/code 加 `data` 或 `download`。
- 新增 oracle 页面优先级：如果提供的解析页面已有相关表格和时期，先抽取；只为缺失续页、缺失时期或缺失官方实际值搜索。
- 新增完整日期范围检查：先枚举所有请求时期，验证每个时期都有证据，避免用不完整 ledger 计算。
- 新增 Treasury financing 角色标注：区分 offered amount、tenders received、accepted、refunding、new cash 等不可互换金额。
- 新增汇率方向台账：记录源单位、源货币、汇率方向和最终单位，避免乘除方向错误。
- 新增表格对齐规则：按行标签和精确列标题对齐，警惕 continued columns、脚注、金额/百分比相邻列、财政年/日历年区块和重复月份。
- 新增派生比较方向：明确 B minus A、former minus latter、share = X / total，以及 gap 问题先算行内差值。
- 新增统计公式台账：确认 series/endpoints、ordered vector、intervals、CAGR、Pearson correlation、OLS 约定等。
- 新增多阶段查找：先固定第一个表推导出的 key，再用该精确 key 查第二个指标。
- 新增 inclusive time-series ledger：每个请求月/年恰好一次，并保留 calendar/fiscal、end-of-month、单位和调整。
- 新增时间序列统计细节：端点包含/排除、趋势回归索引、median 排序、logarithmic growth 使用 `ln(final/initial)`。
- 新增严格最终格式：按请求转换单位、控制小数/逗号/整数/nearest rounding，默认不附加单位词。
- 新增标准差约定：population 用 `n`，sample 用 `n-1`，未说明的小样本 z-score 比较用 sample standard deviation。
- 新增 Treasury security quotations 规则：32nds 报价如 `99.27` 应解析为 `99 + 27/32`。

### 优化意图

优化重点是把 OfficeQA 从“找到值后计算”升级为“检索来源、周期、表格角色、公式、单位、格式全链路可审计”，尤其防止金融/统计任务中的口径混淆、日期缺失、汇率方向错误和最终格式错误。

## SearchQA

### 修改范围

SearchQA 初始 skill 是空白占位，优化后新增大量短答案问答规则，覆盖答案归一化、证据匹配、clue 类型推断和 trivia/crossword/Jeopardy 风格陷阱。

### 主要修改点

- 新增简洁答案原则：优先最短无歧义答案，避免不必要的法律后缀、通用描述词、扩展正式名称。
- 新增短语裁剪规则：从长描述短语中剥离重复请求类型或 clue 修饰语的词，保留核心实体/headword。
- 新增地理特征例外：`Lake`、`River`、`Bay`、`Gorge` 等作为 proper name 或特征类型时应保留。
- 新增公司/组织名称规则：常用 distinctive name 足够时省略 `Company`、`Corporation`、`Inc.` 等。
- 新增表面形式保留：拼写、大小写、标点、词序和 ASCII apostrophe 可能影响答案，应按最强证据复制。
- 新增人名/昵称/圣徒/称号处理：根据 clue/source 选择短名或 canonical full personal name，并保留 `St.` 等常规缩写。
- 新增单复数和词形规则：common-noun category 默认单数字典 headword；不要因 clue 语法复数而随意加 `s`。
- 新增 context-grounded evidence matching：识别 distinctive terms，优先多 clue terms 共现的 passage/title，title 可作证据但不必然是答案。
- 新增 answer type 推断：对 `this man`、`this group`、`this film` 等 Jeopardy-style wording，先推断答案类型。
- 新增 creative works 判断：区分问作品、作者、演员、角色、引用来源还是场景。
- 新增 crossword-style 约束：字母数、双定义、屈折形式是硬约束。
- 新增 trivia snippet 解析：处理 `CATEGORY | clue | answer`、`clue. ANSWER`、`right:` 等 scraped 格式，抽取答案字段而非类别或整句。
- 新增常见 clue 陷阱：反向关系、examples/include 类问题、quotation continuation、song/poem/quote 目标类型、abbreviation/acronym/lyric word 等。

### 优化意图

优化重点是让 SearchQA 输出更贴近短答案评测的 gold span：既不能过长，也不能过度正规化；同时要利用 clue 类型和证据关系避免反向关系、示例关系和标题误判。

## SpreadsheetBench

### 修改范围

SpreadsheetBench 初始 skill 包含基础 Excel 操作流程、库选择和输出要求。优化后大幅补强实际 workbook 探索、公式求值、表格定位、数据类型归一化、目标范围清理和任务特化执行经验。

### 主要修改点

- 新增深度探索：检查 preview 之外的 rows/columns、sample outputs、formulas、labels、headers 和 `Output`、`Manual Result`、`Desired...` 等参考 sheet。
- 新增示例区域利用：把输出区或相邻示例表当作 edge cases 和格式线索，但仍重新计算完整目标范围。
- 新增结构定位：扫描完整 used range 和 header groups，不只看 row 1；用 header text、nearby labels 和 nonblank structure 定位 source/destination。
- 新增公式求值策略：`openpyxl` 不计算公式；若按值检查，应在 Python 中计算并写 literal values。用 `data_only=True` workbook 读取缓存值。
- 新增公式/宏语义解释：即使用户说 formula、SUMIFS/COUNTIFS、VBA 或 macro，普通 `.xlsx` 输出也应实现等价逻辑并写最终值，除非明确要求 live formulas 或 `.xlsm`。
- 新增已有公式作为 specification：解析公式引用范围、criteria、return range、aggregation intent 和 error handling，而不是保留未求值公式。
- 新增匹配操作符选择：`begins with` 用 `startswith`，`contains/search/occurrence` 用 substring，whole-cell match 才用精确相等。
- 新增文本、数值、日期、时间归一化：处理 NBSP、casefold、标点不一致、货币符号、Excel serial dates/times 和 date-like strings。
- 新增 period summary grid 处理：从 sheet names、title、headers、text months 和 date cells 中规范化 period labels。
- 新增 joins/grouping/lookup 规则：构建 normalized/composite keys，保留 source order，使用两遍处理，避免每行全表扫描。
- 新增目标范围清理：只清除指定 target range，防止 stale values/formulas，同时保留无关格式和内容。
- 新增格式应用：写值后用 `openpyxl` styles 精确应用 fills、alignment、fonts、borders、number formats 和 ARGB colors。
- 新增 filtered list/summary/aggregation 输出策略：先收集结果，再写入并清理残留；添加/删除行时注意样式和索引。
- 新增 missing-match behavior：numeric summary grids 通常填 `0`，filtered lists 或 `show only once` 通常填 blank (`None`)。
- 新增 blank-sensitive logic：公式输入可能为空时用 `data_only=True` 判断，真正空白输出写 `None`。
- 新增 slow-update 任务经验：包括 every nth row、schedule/calendar fill、INDEX/MATCH matrix、multi-step macro/VBA-style、special rows、residual balancing、time-threshold summary 等。
- 新增脚本鲁棒性：保持实现简单，始终运行最终 `solution.py`，修复语法/缩进/运行时错误，并验证代表性 target cells。

### 优化意图

优化重点是让 SpreadsheetBench 的 agent 不再停留在“写脚本保存文件”的层面，而是主动理解 workbook 结构、避免公式不计算导致的空值、按真实表头和示例推断目标逻辑，并在保存后验证结果。

## 跨 Benchmark 共性

- 优化后的 skill 普遍把抽象原则变成了可执行检查表，例如搜索账本、公式台账、period ledger、answer-type 推断、header map。
- 多数 benchmark 都增加了“边界/格式”约束：DocVQA 的最小答案片段、SearchQA 的短答案 surface form、OfficeQA 的最终数值格式、SpreadsheetBench 的 target range hygiene。
- 优化后的内容明显来自失败案例复盘：它们集中修补了循环、误取邻近值、选项强弱误判、日期/单位混淆、公式未求值和 clue 关系反向等高频错误。
- `SLOW_UPDATE` 部分承担跨 epoch 的长期经验沉淀，尤其在 ALFWorld 和 SpreadsheetBench 中包含非常具体的任务模式和恢复策略。
