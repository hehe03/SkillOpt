from __future__ import annotations

import json
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader


LABEL_FIELDS = ("ground_truth", "answers", "label_set")


class ShortageAnalyzeDataLoader(SplitDataLoader):
    def __init__(self, *args, allow_test_labels: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.allow_test_labels = allow_test_labels

    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        json_path = path / "items.json"
        if not json_path.exists():
            raise FileNotFoundError(f"No items.json found in {split_path}")
        with json_path.open(encoding="utf-8-sig") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise ValueError(f"Expected JSON array in {json_path}")

        split_name = path.name.lower()
        if split_name == "test" and not self.allow_test_labels:
            for item in items:
                leaked = [field for field in LABEL_FIELDS if field in item]
                if leaked:
                    raise ValueError(
                        "test/items.json must not contain labels during optimization; "
                        f"item {item.get('id')} has {leaked}"
                    )
        if split_name in {"train", "val"}:
            for item in items:
                if not item.get("ground_truth"):
                    raise ValueError(f"{split_name} item {item.get('id')} missing ground_truth")
        return items
