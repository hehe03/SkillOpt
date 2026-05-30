from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def load_skill_payload(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    match = JSON_BLOCK_RE.search(text)
    raw_json = match.group(1).strip() if match else text.strip()
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("skill payload must be a JSON object")
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("skill payload must contain a rules array")
    return payload


def dump_rules_payload(payload: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_skill_payload_from_text(text: str) -> dict[str, Any]:
    match = JSON_BLOCK_RE.search(text)
    raw_json = match.group(1).strip() if match else text.strip()
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must contain a JSON object")
    if not isinstance(payload.get("rules"), list):
        raise ValueError("LLM response JSON must contain a rules array")
    return payload


def write_skill_markdown(payload: dict[str, Any], path: str | Path, *, title: str = "TraceSorter 优化规则 Skill") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        f"# {title}\n\n"
        "下面的 JSON 是当前规则 skill。评估脚本只读取 JSON 代码块。\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "```\n"
    )
    output_path.write_text(text, encoding="utf-8")
