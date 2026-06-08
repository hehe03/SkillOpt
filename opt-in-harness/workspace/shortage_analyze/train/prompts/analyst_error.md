You will be given multiple failed shortage_analyze trajectories and the current skill document.
Each item is a multi-label classification case. The final gate metric is sample-level accuracy: a sample is correct only when the predicted label set exactly equals the gold label set.
However, your analysis must be label-level. Use the Missing labels, Extra labels, and Per-label comparison fields to identify which individual L2 rules caused false negatives or false positives.

Propose concise, generalizable edits to the skill rules. Do not hardcode sample IDs, row indexes, or dataset-specific labels. Only improve the skill document's decision rules, field handling, and output constraints.

Respond ONLY with valid JSON in this shape:
{
  "batch_size": <number>,
  "failure_summary": [{"failure_type": "<type>", "count": <int>, "description": "<one-line>"}],
  "patch": {
    "reasoning": "<why these edits address label-level FP/FN patterns>",
    "edits": [
      {"op": "append", "content": "<markdown>"},
      {"op": "insert_after", "target": "<exact text>", "content": "<markdown>"},
      {"op": "replace", "target": "<exact text>", "content": "<replacement>"},
      {"op": "delete", "target": "<exact text>"}
    ]
  }
}
Use an empty `edits` list if no patch is warranted.
