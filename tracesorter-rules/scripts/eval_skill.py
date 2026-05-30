from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.evaluator import evaluate_split


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="评估 TraceSorter 规则 skill 的最小闭环入口。")
    parser.add_argument("--skill", required=True, help="包含 JSON 规则块的 Markdown skill 文件。")
    parser.add_argument("--split-dir", required=True, help="包含 train/val/test 子目录的数据目录。")
    parser.add_argument("--split", default="val", choices=["train", "val", "test"], help="要评估的数据 split。")
    parser.add_argument("--out-root", required=True, help="输出 predictions、summary 和 failure cases 的目录。")
    parser.add_argument("--max-items", type=int, default=0, help="只评估前 N 条；0 表示全部。")
    parser.add_argument("--bad-threshold", type=float, help="覆盖 skill 中的 badcase 判定阈值。")
    parser.add_argument("--good-threshold", type=float, help="覆盖 skill 中的 goodcase 判定阈值。")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = evaluate_split(
        skill_path=args.skill,
        split_dir=args.split_dir,
        split=args.split,
        out_root=args.out_root,
        max_items=args.max_items,
        bad_threshold=args.bad_threshold,
        good_threshold=args.good_threshold,
    )
    print("评估完成")
    print(f"样本数: {summary['n_items']}")
    print(f"规则数: {summary['rules']}")
    if summary.get("count", 0):
        print(f"有标签样本数: {summary['count']}")
        print(f"badcase precision: {summary['badcase_precision']}")
        print(f"badcase recall: {summary['badcase_recall']}")
        print(f"badcase f1: {summary['badcase_f1']}")
        print(f"accuracy: {summary['accuracy']}")
    else:
        print("当前 split 没有可见标签，仅输出预测和规则命中原因，未计算 precision/recall/f1。")
    print(f"输出目录: {Path(args.out_root).resolve()}")


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
