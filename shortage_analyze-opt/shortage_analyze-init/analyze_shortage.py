#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

NONE_LABEL = "- 未匹配到分支"
LABEL_ORDER = ["网容异常", "用量异常", "补库异常", "基线异常", "计划参数异常", "补库供应不及时", "责任库房异常", "替代交付异常"]
EMPTY_STRINGS = {"", "none", "null", "nan", "n/a", "na", "(空)"}


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip().lower() in EMPTY_STRINGS


def to_number(value: Any) -> float | None:
    if is_empty(value):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        value = float(value)
        return None if math.isnan(value) else value
    try:
        value = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return None if math.isnan(value) else value


def parse_duration_days(value: Any) -> float | None:
    if is_empty(value):
        return None
    if isinstance(value, (int, float)):
        return to_number(value)
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*([dhDH])?", text)
    if not match:
        return to_number(value)
    number = float(match.group(1))
    return number / 24.0 if (match.group(2) or "d").lower() == "h" else number


def safe_compare(left: Any, right: Any, operator: str) -> bool:
    left_num = to_number(left)
    right_num = to_number(right)
    if left_num is None or right_num is None:
        return False
    return {
        ">": left_num > right_num,
        "<": left_num < right_num,
        ">=": left_num >= right_num,
        "<=": left_num <= right_num,
        "==": left_num == right_num,
    }[operator]


def duration_compare(left: Any, right: Any, operator: str) -> bool:
    left_days = parse_duration_days(left)
    right_days = parse_duration_days(right)
    if left_days is None or right_days is None:
        return False
    return safe_compare(left_days, right_days, operator)


def get_field(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and not is_empty(row[name]):
            return row[name]
    for name in names:
        if name in row:
            return row[name]
    return None


def parse_list_like(value: Any) -> list[Any]:
    if is_empty(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    text = str(value).strip()
    if text == "[]" or text.lower() in EMPTY_STRINGS:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            inner = text[1:-1].strip()
            return [inner] if inner else []
        return parsed if isinstance(parsed, list) else [parsed]
    return [text]


def check_网容异常(row: Mapping[str, Any]) -> bool:
    value = to_number(get_field(row, "网容"))
    return value is None or value <= 0


def check_用量异常(row: Mapping[str, Any]) -> bool:
    return safe_compare(get_field(row, "M2"), get_field(row, "M3-M13最大值"), ">") or safe_compare(
        get_field(row, "历史交易数量"), get_field(row, "原始基线"), ">"
    )


def check_补库异常(row: Mapping[str, Any]) -> bool:
    return safe_compare(get_field(row, "历史交易数量"), get_field(row, "补库提前期补库和调拨汇总数量"), ">")


def check_基线异常(row: Mapping[str, Any]) -> bool:
    return (
        safe_compare(get_field(row, "修改基线ROP"), get_field(row, "推荐基线"), "<")
        or safe_compare(get_field(row, "历史交易数量"), get_field(row, "原始基线"), ">")
        or (
            safe_compare(get_field(row, "原始基线"), 0, "==")
            and safe_compare(get_field(row, "历史交易数量"), 0, "==")
            and safe_compare(get_field(row, "网容"), 0, ">")
        )
    )


def check_计划参数异常(row: Mapping[str, Any]) -> bool:
    return safe_compare(get_field(row, "最终补库提前期", "最终补库提前期.1"), get_field(row, "计算补库提前期"), "<")


def check_补库供应不及时(row: Mapping[str, Any]) -> bool:
    lead_time = get_field(row, "最终补库提前期", "最终补库提前期.1")
    return duration_compare(get_field(row, "补库在途时间"), lead_time, ">") or duration_compare(get_field(row, "调拨在途时间"), lead_time, ">")


def check_责任库房异常(row: Mapping[str, Any]) -> bool:
    return duration_compare(get_field(row, "责任库房预测物流时长"), get_field(row, "SLA承诺时间"), ">")


def check_替代交付异常(row: Mapping[str, Any]) -> bool:
    single_stock = get_field(row, "单一替代库存汇总", "单一替代库存查询")
    shortage_qty = get_field(row, "总欠料数量", "总欠料数量.1", "欠料数量")
    relation = get_field(row, "组合替代关系", "组合替代关系.1")
    combo_stock = get_field(row, "组合替代库存汇总", "组合替代库存")
    combo_need = get_field(row, "组合替代需求数量")
    condition1 = safe_compare(single_stock, shortage_qty, "<")
    relation_items = parse_list_like(relation)
    if not relation_items:
        condition2 = False
    elif is_empty(combo_stock):
        condition2 = True
    elif not is_empty(combo_need):
        condition2 = safe_compare(combo_stock, combo_need, "<")
    else:
        condition2 = safe_compare(combo_stock, shortage_qty, "<")
    return condition1 and condition2


def predict_labels(features: Mapping[str, Any]) -> list[str]:
    checks = [
        ("网容异常", check_网容异常),
        ("用量异常", check_用量异常),
        ("补库异常", check_补库异常),
        ("基线异常", check_基线异常),
        ("计划参数异常", check_计划参数异常),
        ("补库供应不及时", check_补库供应不及时),
        ("责任库房异常", check_责任库房异常),
        ("替代交付异常", check_替代交付异常),
    ]
    return [label for label, check in checks if check(features)]


def format_prediction(labels: Sequence[str]) -> str:
    label_set = set(labels)
    ordered = [label for label in LABEL_ORDER if label in label_set]
    return "、".join(ordered) if ordered else NONE_LABEL


def analyze_row(row: Mapping[str, Any]) -> str:
    return format_prediction(predict_labels(row))


def load_split_items(split_path: str | Path) -> list[dict[str, Any]]:
    path = Path(split_path)
    if path.is_dir():
        path = path / "items.json"
    with path.open("r", encoding="utf-8-sig") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError(f"Split file must contain a JSON list: {path}")
    return items


def analyze_split(split_path: str | Path, output: str | Path | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in load_split_items(split_path):
        features = item.get("features")
        if not isinstance(features, dict):
            raise ValueError(f"Split item lacks features: {item!r}")
        labels = predict_labels(features)
        row = {
            "id": item.get("id"),
            "uid": item.get("uid", item.get("id")),
            "row_index": item.get("row_index"),
            "predicted_answer": format_prediction(labels),
            "predicted_labels": labels,
        }
        if "ground_truth" in item:
            row["ground_truth"] = item["ground_truth"]
        results.append(row)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".jsonl":
            with out_path.open("w", encoding="utf-8") as f:
                for row in results:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def analyze_excel(excel_path: str | Path, output_excel: str | Path | None = None, sheet: str | int | None = None) -> str:
    kwargs: dict[str, Any] = {}
    if sheet is not None:
        kwargs["sheet_name"] = sheet
    df = pd.read_excel(excel_path, **kwargs)
    df["L2分类结果"] = [analyze_row(row.to_dict()) for _, row in df.iterrows()]
    if output_excel is None:
        path = Path(excel_path)
        output_excel = path.parent / f"{path.stem}_归因分析结果.xlsx"
    out_path = Path(output_excel)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(out_path, index=False)
    return str(out_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="欠料归因规则脚本，支持 Excel 宽表和 SkillOpt split items.json。")
    parser.add_argument("excel", nargs="?", help="输入 Excel 路径；兼容原始脚本用法。")
    parser.add_argument("excel_output", nargs="?", help="输出 Excel 路径；兼容原始脚本用法。")
    parser.add_argument("--input-split", help="SkillOpt split 的 items.json 文件，或包含 items.json 的 split 目录。")
    parser.add_argument("--output", help="split 预测结果输出路径，支持 .json 或 .jsonl。")
    parser.add_argument("--input-excel", help="输入 Excel 路径；等价于位置参数 excel。")
    parser.add_argument("--output-excel", help="输出 Excel 路径；等价于位置参数 excel_output。")
    parser.add_argument("--sheet", default=None, help="Excel sheet 名称或序号；默认第一个 sheet。")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_split:
        results = analyze_split(args.input_split, args.output)
        if not args.output:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    source_excel = args.input_excel or args.excel
    if not source_excel:
        parser.error("请提供 Excel 输入路径，或使用 --input-split 指定 SkillOpt split。")
    sheet: str | int | None = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)
    print(analyze_excel(source_excel, args.output_excel or args.excel_output, sheet=sheet))


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--input-split",
        "shortage_analyze-opt/processed/shortage_analyze_split/train/items.json",
        "--output",
        "shortage_analyze-opt/processed/eval/init_train_predictions.jsonl",
    ]
    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
