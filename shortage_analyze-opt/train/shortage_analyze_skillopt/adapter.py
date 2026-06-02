from __future__ import annotations

import os

from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.gradient.reflect import run_minibatch_reflect

from shortage_analyze_skillopt.dataloader import ShortageAnalyzeDataLoader
from shortage_analyze_skillopt.rollout import run_batch


class ShortageAnalyzeAdapter(EnvAdapter):
    def __init__(
        self,
        split_dir: str = "",
        data_path: str = "",
        split_mode: str = "split_dir",
        split_ratio: str = "6:2:2",
        split_seed: int = 42,
        split_output_dir: str = "",
        workers: int = 4,
        analyst_workers: int = 4,
        failure_only: bool = False,
        minibatch_size: int = 4,
        edit_budget: int = 3,
        seed: int = 42,
        limit: int = 0,
        exec_timeout: int = 300,
        max_completion_tokens: int = 4096,
        allow_test_labels: bool = False,
        initial_skill_path: str = "",
        initial_script_path: str = "",
        script_cache_dir: str = "",
        script_codegen_timeout: int = 900,
        script_codegen_model: str = "",
    ) -> None:
        self.workers = int(workers)
        self.analyst_workers = int(analyst_workers)
        self.failure_only = bool(failure_only)
        self.minibatch_size = int(minibatch_size)
        self.edit_budget = int(edit_budget)
        self.exec_timeout = int(exec_timeout)
        self.max_completion_tokens = int(max_completion_tokens)
        self.allow_test_labels = bool(allow_test_labels)
        self.initial_skill_path = str(initial_skill_path or "")
        self.initial_script_path = str(initial_script_path or "")
        self.script_cache_dir = str(script_cache_dir or "")
        self.script_codegen_timeout = int(script_codegen_timeout)
        self.script_codegen_model = str(script_codegen_model or "")
        self.dataloader = ShortageAnalyzeDataLoader(
            split_dir=split_dir,
            data_path=data_path,
            split_mode=split_mode,
            split_ratio=split_ratio,
            split_seed=split_seed,
            split_output_dir=split_output_dir,
            seed=seed,
            limit=limit,
            allow_test_labels=allow_test_labels,
        )

    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        if cfg.get("eval_test") and not self.allow_test_labels:
            raise ValueError(
                "当前配置禁止优化过程读取测试集标签，因此 evaluation.eval_test 必须为 false。"
            )
        if str(cfg.get("data_path") or "").strip():
            raise ValueError(
                "shortage_analyze 优化阶段不能配置 env.data_path；"
                "请先运行 prepare_skillopt_data.py，再使用 split_dir。"
            )
        if not self.script_cache_dir:
            self.script_cache_dir = os.path.join(str(cfg.get("out_root") or ""), "generated_scripts")
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
            exec_timeout=self.exec_timeout,
            max_completion_tokens=self.max_completion_tokens,
            diagnostic_mode=kwargs.get("diagnostic_mode", False),
            diagnostic_instruction=kwargs.get("diagnostic_instruction", ""),
            task_timeout=kwargs.get("task_timeout", self.exec_timeout + 120),
            script_cache_dir=self.script_cache_dir,
            initial_skill_path=self.initial_skill_path,
            initial_script_path=self.initial_script_path,
            script_codegen_timeout=self.script_codegen_timeout,
            script_codegen_model=self.script_codegen_model,
        )

    def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs) -> list[dict | None]:
        prediction_dir = kwargs.get("prediction_dir", os.path.join(out_dir, "predictions"))
        patches_dir = kwargs.get("patches_dir", os.path.join(out_dir, "patches"))
        raw_patches = run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=prediction_dir,
            patches_dir=patches_dir,
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
        return ["shortage_analyze"]

    def get_error_minibatch_prompt(self) -> str:
        return (
            "You will be given multiple failed shortage_analyze trajectories and the current skill document.\n"
            "Each item is a multi-label classification case. The final gate metric is sample-level accuracy: "
            "a sample is correct only when the predicted label set exactly equals the gold label set.\n"
            "However, your analysis must be label-level. Use the Missing labels, Extra labels, and "
            "Per-label comparison fields to identify which individual L2 rules caused false negatives "
            "or false positives.\n\n"
            "Propose concise, generalizable edits to the skill rules. Do not hardcode sample IDs, row indexes, "
            "or dataset-specific labels. Do not suggest reading Excel files, test labels, references, or scripts. "
            "Only improve the skill document's decision rules, field handling, and output constraints.\n\n"
            "Respond ONLY with valid JSON in this shape:\n"
            "{\n"
            "  \"batch_size\": <number>,\n"
            "  \"failure_summary\": [{\"failure_type\": \"<type>\", \"count\": <int>, \"description\": \"<one-line>\"}],\n"
            "  \"patch\": {\n"
            "    \"reasoning\": \"<why these edits address label-level FP/FN patterns>\",\n"
            "    \"edits\": [\n"
            "      {\"op\": \"append\", \"content\": \"<markdown>\"},\n"
            "      {\"op\": \"insert_after\", \"target\": \"<exact text>\", \"content\": \"<markdown>\"},\n"
            "      {\"op\": \"replace\", \"target\": \"<exact text>\", \"content\": \"<replacement>\"},\n"
            "      {\"op\": \"delete\", \"target\": \"<exact text>\"}\n"
            "    ]\n"
            "  }\n"
            "}\n"
            "Use an empty `edits` list if no patch is warranted."
        )

    def get_success_minibatch_prompt(self) -> str:
        return (
            "You will be given multiple successful shortage_analyze trajectories and the current skill document.\n"
            "This is a multi-label classification task. Preserve behavior that correctly predicts every "
            "individual label in the gold label set and avoids extra labels. Use the Per-label comparison "
            "fields to identify robust rule patterns worth keeping or clarifying.\n\n"
            "Only propose edits when they add general, non-duplicative guidance to the skill. Do not hardcode "
            "sample IDs, row indexes, or dataset-specific answers. Do not suggest reading Excel files, test labels, "
            "references, or scripts.\n\n"
            "Respond ONLY with valid JSON in this shape:\n"
            "{\n"
            "  \"batch_size\": <number>,\n"
            "  \"success_summary\": [{\"pattern\": \"<pattern>\", \"count\": <int>, \"description\": \"<one-line>\"}],\n"
            "  \"patch\": {\n"
            "    \"reasoning\": \"<why these edits preserve useful label-level behavior>\",\n"
            "    \"edits\": [\n"
            "      {\"op\": \"append\", \"content\": \"<markdown>\"},\n"
            "      {\"op\": \"insert_after\", \"target\": \"<exact text>\", \"content\": \"<markdown>\"},\n"
            "      {\"op\": \"replace\", \"target\": \"<exact text>\", \"content\": \"<replacement>\"},\n"
            "      {\"op\": \"delete\", \"target\": \"<exact text>\"}\n"
            "    ]\n"
            "  }\n"
            "}\n"
            "Use an empty `edits` list if no patch is warranted."
        )
