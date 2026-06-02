from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path


SKILLOPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINAL_SKILL = SKILLOPT_ROOT / "shortage_analyze" / "SKILL.md"
DEFAULT_RULES = SKILLOPT_ROOT / "shortage_analyze" / "references" / "rules.md"
DEFAULT_OUTPUT = SKILLOPT_ROOT / "shortage_analyze-init" / "initial_skill.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="基于原始 shortage_analyze skill 和详细规则生成 SkillOpt 优化基线。"
    )
    parser.add_argument("--original-skill", default=str(DEFAULT_ORIGINAL_SKILL))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def build_initial_skill(rules: str) -> str:
    return f"""---
name: shortage-analyze-skillopt-baseline
description: 用于 SkillOpt 优化的欠料归因规则文档。根据单行欠料分析数据判断 L2 分类标签，不调用外部脚本，不读取 Excel 或测试集标签。
---

# 欠料归因分析 SkillOpt 基线

你是欠料归因分析 Agent。你的任务是根据用户提供的一行欠料分析数据，判断应命中的 L2 分类标签。

## 输出要求

- 最终答案必须放在 `<answer>...</answer>` 中。
- 多个标签按下方“标签顺序”排序，并使用中文顿号 `、` 连接。
- 如果没有任何标签命中，输出 `<answer>- 未匹配到分支</answer>`。
- 不要读取 Excel 文件、测试集标签、`references/`、`scripts/` 或其它外部文件；只能根据当前行字段和本文档规则判断。

## 标签顺序

1. 网容异常
2. 用量异常
3. 补库异常
4. 基线异常
5. 计划参数异常
6. 补库供应不及时
7. 责任库房异常
8. 替代交付异常

## 通用判断约定

- 空值包括：缺失字段、空字符串、`None`、`nan`、`NaN`、`(空)`。
- 数值比较时，如果任一参与比较的值为空或不能转为数字，则该比较条件不满足，除非具体规则另有说明。
- 时间字段可能带单位：
  - `d` 表示天，例如 `62.87d`。
  - `h` 表示小时，比较前应换算为天，即小时数除以 24。
- `组合替代关系`、`组合替代库存汇总` 等字段可能是字符串形式的列表，例如 `[]` 或 `["item1"]`。

## 可优化规则

下面是从原始规则文档中融合进来的详细业务规则。SkillOpt 可以在训练中修正、补充、澄清这些规则，但不能引入依赖测试集标签或外部文件的特例。

{rules.strip()}

## SkillOpt 优化边界

- 可以优化：规则条件、空值处理、时间单位处理、标签冲突处理、输出格式约束、已知训练错误模式。
- 不可以优化：硬编码训练样本 ID、读取 `data.xlsx`、读取测试集标签、调用原始 Python 脚本、要求用户提供答案。
- 优化后的文档仍应能被人读懂，并能在训练结束后翻译成快速预测脚本。
"""


def run(args: argparse.Namespace) -> None:
    original_skill_path = Path(args.original_skill)
    rules_path = Path(args.rules)
    output_path = Path(args.output)

    original_skill_path.read_text(encoding="utf-8")
    rules = rules_path.read_text(encoding="utf-8")
    initial_skill = build_initial_skill(rules)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(initial_skill, encoding="utf-8")
    print(f"已生成 SkillOpt 初始 skill: {output_path}")
    print(f"来源 original skill: {original_skill_path}")
    print(f"来源 rules: {rules_path}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--original-skill",
        str(DEFAULT_ORIGINAL_SKILL),
        "--rules",
        str(DEFAULT_RULES),
        "--output",
        str(DEFAULT_OUTPUT),
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
