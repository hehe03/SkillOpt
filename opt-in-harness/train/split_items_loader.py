from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader


class StandardItemsDataLoader(SplitDataLoader):
    """Load the opt-in-harness standard split layout.

    Expected layout:

    ```text
    split_dir/
      train/items.json
      val/items.json
      test/items.json
    ```

    Each `items.json` must be a JSON array of objects. By default train and
    val items must include `ground_truth`, because SkillOpt needs labels for
    rollout scoring and selection.
    """

    def __init__(
        self,
        *args,
        item_file_name: str = "items.json",
        required_label_field: str = "ground_truth",
        required_label_splits: Iterable[str] = ("train", "val"),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.item_file_name = str(item_file_name or "items.json")
        self.required_label_field = str(required_label_field or "")
        self.required_label_splits = {
            str(split).strip().lower()
            for split in required_label_splits
            if str(split).strip()
        }

    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        json_path = path / self.item_file_name
        if not json_path.exists():
            raise FileNotFoundError(f"No {self.item_file_name} found in {split_path}")

        with json_path.open(encoding="utf-8-sig") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise ValueError(f"Expected JSON array in {json_path}")

        split_name = path.name.lower()
        if self.required_label_field and split_name in self.required_label_splits:
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError(f"{json_path} contains non-object item: {item!r}")
                if not item.get(self.required_label_field):
                    item_id = item.get("id", "<missing id>")
                    raise ValueError(
                        f"{split_name} item {item_id} missing {self.required_label_field}"
                    )
        return items
