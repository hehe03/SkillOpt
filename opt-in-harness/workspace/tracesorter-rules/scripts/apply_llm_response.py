from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.skill import parse_skill_payload_from_text, write_skill_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 LLM/Harness 响应解析并写成 TraceSorter skill Markdown。")
    parser.add_argument("--response", required=True, help="LLM 原始响应文件。")
    parser.add_argument("--out-skill", required=True, help="输出 skill Markdown 路径。")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    response = Path(args.response).read_text(encoding="utf-8")
    payload = parse_skill_payload_from_text(response)
    write_skill_markdown(payload, args.out_skill)
    print("已写入优化后 skill")
    print(f"输出: {Path(args.out_skill).resolve()}")


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
