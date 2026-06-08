你要把一个欠料归因 Skill 文档转换为可运行 Python 脚本。

要求：
1. 只输出完整 Python 代码，不要解释，不要 Markdown 代码围栏。
2. 规则来源只能是“当前 Skill 文档”；参考脚本只用于接口和工程风格。
3. 脚本应为自包含预测逻辑，只根据传入的 `features` 和当前 Skill 文档判断标签。
4. 必须提供以下函数：
   - `predict_labels(features: dict) -> list[str]`
   - `format_prediction(labels: list[str]) -> str`
5. 可选提供 CLI：`--input-split`、`--input-excel`、`--output`、`--output-excel`、`--sheet`。
6. 标签顺序固定为：网容异常、用量异常、补库异常、基线异常、计划参数异常、补库供应不及时、责任库房异常、替代交付异常。
7. 无命中时 `format_prediction` 返回 `- 未匹配到分支`，多个标签用中文顿号 `、` 连接。
8. 稳健处理空值、数字转换、`d/h` 时间单位、字符串列表字段。

## 当前 Skill 文档

__SKILL_CONTENT__

## 接口参考脚本

__REFERENCE_SCRIPT__
