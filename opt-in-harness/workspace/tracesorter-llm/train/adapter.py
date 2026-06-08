from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from typing import Any

from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.gradient.reflect import run_minibatch_reflect

COMMON_TRAIN_ROOT = Path(__file__).resolve().parents[3] / "train"
if str(COMMON_TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_TRAIN_ROOT))
TRAIN_ROOT = Path(__file__).resolve().parent
if str(TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(TRAIN_ROOT))

from rollout import run_batch
from split_items_loader import StandardItemsDataLoader


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8-sig").strip()


class BalancedTraceSorterDataLoader(StandardItemsDataLoader):
    def __init__(
        self,
        *args,
        balanced_train_batches: bool = True,
        balance_labels: str = "goodcase,badcase",
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.balanced_train_batches = bool(balanced_train_batches)
        self.balance_labels = [
            label.strip()
            for label in str(balance_labels or "goodcase,badcase").split(",")
            if label.strip()
        ]

    @staticmethod
    def _label_of(item: dict[str, Any]) -> str:
        return str(item.get("ground_truth") or item.get("label") or "").strip().lower()

    def _balanced_sample(self, *, batch_size: int, seed: int) -> list[dict]:
        items = list(self.train_items)
        if not self.balanced_train_batches or batch_size <= 0 or len(self.balance_labels) < 2:
            rng = random.Random(seed)
            rng.shuffle(items)
            return items[:batch_size]

        buckets: dict[str, list[dict]] = {
            label: [item for item in items if self._label_of(item) == label]
            for label in self.balance_labels
        }
        if any(not bucket for bucket in buckets.values()):
            rng = random.Random(seed)
            rng.shuffle(items)
            return items[:batch_size]

        rng = random.Random(seed)
        label_order = list(self.balance_labels)
        rng.shuffle(label_order)
        base = batch_size // len(label_order)
        remainder = batch_size % len(label_order)
        quotas = {
            label: base + (1 if index < remainder else 0)
            for index, label in enumerate(label_order)
        }

        sampled: list[dict] = []
        for label in label_order:
            bucket = list(buckets[label])
            rng.shuffle(bucket)
            quota = quotas[label]
            if quota <= len(bucket):
                sampled.extend(bucket[:quota])
            else:
                sampled.extend(bucket)
                sampled.extend(rng.choice(bucket) for _ in range(quota - len(bucket)))

        rng.shuffle(sampled)
        return sampled[:batch_size]

    def build_train_batch(self, batch_size: int, seed: int, **kwargs) -> BatchSpec:
        items = self._balanced_sample(batch_size=batch_size, seed=seed)
        return BatchSpec(
            phase="train",
            split="train",
            seed=seed,
            batch_size=len(items),
            payload=items,
            metadata={
                "balanced_train_batches": self.balanced_train_batches,
                "balance_labels": self.balance_labels,
            },
        )

    def plan_train_epoch(
        self,
        *,
        epoch: int,
        steps_per_epoch: int,
        accumulation: int,
        batch_size: int,
        seed: int,
        **kwargs,
    ) -> list[BatchSpec]:
        total_batches = steps_per_epoch * accumulation
        return [
            self.build_train_batch(
                batch_size=batch_size,
                seed=seed + epoch * 1000 + batch_idx + 1,
                **kwargs,
            )
            for batch_idx in range(total_batches)
        ]


class TraceSorterLlmAdapter(EnvAdapter):
    def __init__(
        self,
        split_dir: str = "",
        data_path: str = "",
        split_mode: str = "split_dir",
        split_ratio: str = "6:2:2",
        split_seed: int = 42,
        split_output_dir: str = "",
        workers: int = 1,
        analyst_workers: int = 1,
        failure_only: bool = False,
        minibatch_size: int = 4,
        edit_budget: int = 3,
        seed: int = 42,
        limit: int = 0,
        llm_timeout: int = 300,
        max_trace_chars: int = 24000,
        target_model: str = "harness-default",
        balanced_train_batches: bool = True,
        balance_labels: str = "goodcase,badcase",
    ) -> None:
        self.workers = int(workers)
        self.analyst_workers = int(analyst_workers)
        self.failure_only = bool(failure_only)
        self.minibatch_size = int(minibatch_size)
        self.edit_budget = int(edit_budget)
        self.llm_timeout = int(llm_timeout)
        self.max_trace_chars = int(max_trace_chars)
        self.target_model = str(target_model or "harness-default")
        self.dataloader = BalancedTraceSorterDataLoader(
            split_dir=split_dir,
            data_path=data_path,
            split_mode=split_mode,
            split_ratio=split_ratio,
            split_seed=split_seed,
            split_output_dir=split_output_dir,
            seed=seed,
            limit=limit,
            balanced_train_batches=balanced_train_batches,
            balance_labels=balance_labels,
        )

    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        if str(cfg.get("data_path") or "").strip():
            raise ValueError("tracesorter-llm 使用 process/prepare_data.py 生成的 split_dir 数据，env.data_path 应保持为空。")
        self.dataloader.setup(cfg)

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kwargs):
        return list(batch.payload or [])

    def build_train_env(self, batch_size: int, seed: int, **kwargs):
        batch = self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs):
        batch = self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def rollout(self, env_manager, skill_content: str, out_dir: str, **kwargs) -> list[dict]:
        return run_batch(
            items=list(env_manager),
            out_root=out_dir,
            skill_content=skill_content,
            workers=self.workers,
            llm_timeout=kwargs.get("task_timeout", self.llm_timeout),
            max_trace_chars=self.max_trace_chars,
            target_model=self.target_model,
        )

    def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs) -> list[dict | None]:
        raw_patches = run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=kwargs.get("prediction_dir", os.path.join(out_dir, "predictions")),
            patches_dir=kwargs.get("patches_dir", os.path.join(out_dir, "patches")),
            workers=self.analyst_workers,
            failure_only=self.failure_only,
            minibatch_size=self.minibatch_size,
            edit_budget=self.edit_budget,
            random_seed=kwargs.get("random_seed"),
            error_system=self.get_error_minibatch_prompt(),
            success_system=self.get_success_minibatch_prompt(),
            step_buffer_context=kwargs.get("step_buffer_context", ""),
            meta_skill_context=kwargs.get("meta_skill_context", ""),
            update_mode=getattr(self, "_cfg", {}).get("skill_update_mode", "patch"),
        )
        for patch in raw_patches:
            if isinstance(patch, dict) and isinstance(patch.get("patch"), list):
                patch["patch"] = {
                    "reasoning": "Converted from shorthand list format.",
                    "edits": patch["patch"],
                }
        return raw_patches

    def get_task_types(self) -> list[str]:
        return ["trace_classification"]

    def get_error_minibatch_prompt(self) -> str:
        return _read_prompt("analyst_error.md")

    def get_success_minibatch_prompt(self) -> str:
        return _read_prompt("analyst_success.md")
