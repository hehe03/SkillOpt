from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracesorter_rules.skill import write_skill_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将现有规则 JSON 导入为 tracesorter-rules skill Markdown。")
    parser.add_argument("--rules-json", required=True, help="规则 JSON 文件，支持 {'rules': [...]} 或裸数组。")
    parser.add_argument("--out-skill", required=True, help="输出 skill Markdown。")
    parser.add_argument("--bad-threshold", type=float, default=0.6)
    parser.add_argument("--good-threshold", type=float, default=0.5)
    return parser


def _load_rules(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rules = data.get("rules", [])
    else:
        rules = data
    if not isinstance(rules, list):
        raise ValueError("rules-json must contain a list or {'rules': [...]}")
    return rules


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    rules = _load_rules(Path(args.rules_json))
    payload = {
        "bad_threshold": args.bad_threshold,
        "good_threshold": args.good_threshold,
        "rules": rules,
    }
    write_skill_markdown(payload, args.out_skill, title="TraceSorter 导入规则 Skill")
    print("规则导入完成")
    print(f"规则数: {len(rules)}")
    print(f"输出: {Path(args.out_skill).resolve()}")


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] | None = None

    main(SCRIPT_ARGS)
