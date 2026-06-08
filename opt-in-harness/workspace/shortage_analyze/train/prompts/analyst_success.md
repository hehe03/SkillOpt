You will be given multiple successful shortage_analyze trajectories and the current skill document.
This is a multi-label classification task. Preserve behavior that correctly predicts every individual label in the gold label set and avoids extra labels. Use the Per-label comparison fields to identify robust rule patterns worth keeping or clarifying.

Only propose edits when they add general, non-duplicative guidance to the skill. Do not hardcode sample IDs, row indexes, or dataset-specific answers.

Respond ONLY with valid JSON in this shape:
{
  "batch_size": <number>,
  "success_summary": [{"pattern": "<pattern>", "count": <int>, "description": "<one-line>"}],
  "patch": {
    "reasoning": "<why these edits preserve useful label-level behavior>",
    "edits": [
      {"op": "append", "content": "<markdown>"},
      {"op": "insert_after", "target": "<exact text>", "content": "<markdown>"},
      {"op": "replace", "target": "<exact text>", "content": "<replacement>"},
      {"op": "delete", "target": "<exact text>"}
    ]
  }
}
Use an empty `edits` list if no patch is warranted.
