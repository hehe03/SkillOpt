from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.predictor import predict_split


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="加载当前 TraceSorter skill，对指定 split 输出预测标签。")
    parser.add_argument("--skill", required=True, help="当前规则 skill Markdown。")
    parser.add_argument("--split-dir", required=True, help="包含 train/val/test 子目录的数据目录。")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"], help="要预测的数据 split。")
    parser.add_argument("--out-root", required=True, help="预测输出目录。")
    parser.add_argument("--max-items", type=int, default=0, help="只预测前 N 条；0 表示全部。")
    parser.add_argument("--bad-threshold", type=float, help="覆盖 skill 中的 badcase 判定阈值。")
    parser.add_argument("--good-threshold", type=float, help="覆盖 skill 中的 goodcase 判定阈值。")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = predict_split(
        skill_path=args.skill,
        split_dir=args.split_dir,
        split=args.split,
        out_root=args.out_root,
        max_items=args.max_items,
        bad_threshold=args.bad_threshold,
        good_threshold=args.good_threshold,
    )
    print("预测完成")
    print(f"样本数: {summary['n_items']}")
    print(f"规则数: {summary['rules']}")
    print(f"预测 goodcase: {summary['predicted_goodcase']}")
    print(f"预测 badcase: {summary['predicted_badcase']}")
    print(f"输出目录: {Path(args.out_root).resolve()}")


if __name__ == "__main__":
    # Fill SCRIPT_ARGS when running this file directly from an IDE.
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
