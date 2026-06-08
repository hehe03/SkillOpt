# TraceSorter 初始规则 Skill

下面的 JSON 是固定初始规则。SkillOpt 优化时应只改写 JSON 代码块中的 `bad_threshold`、`good_threshold` 和 `rules`，不要改写评估脚本。

```json
{
  "bad_threshold": 0.6,
  "good_threshold": 0.5,
  "rules": [
    {
      "id": "parse_error",
      "label": "badcase",
      "weight": 1.0,
      "group": "hard_failure",
      "group_cap": 1.0,
      "description": "Trace 不是可解析的 JSON 对象或数组。",
      "all": [
        {
          "feature": "parse_error",
          "op": "==",
          "value": true
        }
      ]
    },
    {
      "id": "empty_trace",
      "label": "badcase",
      "weight": 0.9,
      "group": "hard_failure",
      "group_cap": 1.0,
      "description": "Trace 为空。",
      "all": [
        {
          "feature": "is_empty_trace",
          "op": "==",
          "value": true
        }
      ]
    },
    {
      "id": "runtime_error_text",
      "label": "badcase",
      "weight": 0.7,
      "group": "error_signal",
      "group_cap": 0.8,
      "description": "Trace 中出现 error、exception、timeout 或 failed 等失败文本。",
      "all": [
        {
          "feature": "has_error_text",
          "op": "==",
          "value": true
        }
      ]
    },
    {
      "id": "empty_results_many_steps",
      "label": "badcase",
      "weight": 0.45,
      "group": "missing_result",
      "group_cap": 0.6,
      "description": "多步执行中大多数结果为空。",
      "all": [
        {
          "feature": "step_count",
          "op": ">=",
          "value": 3
        },
        {
          "feature": "empty_result_ratio",
          "op": ">=",
          "value": 0.67
        }
      ]
    },
    {
      "id": "repeated_action_loop",
      "label": "badcase",
      "weight": 0.45,
      "group": "loop_signal",
      "group_cap": 0.6,
      "description": "相同 action 连续重复，疑似卡住。",
      "all": [
        {
          "feature": "max_consecutive_same_action",
          "op": ">=",
          "value": 3
        }
      ]
    },
    {
      "id": "final_answer_without_error",
      "label": "goodcase",
      "weight": 0.55,
      "group": "answer_evidence",
      "group_cap": 0.7,
      "description": "存在 final answer 且没有错误文本。",
      "all": [
        {
          "feature": "has_final_answer",
          "op": "==",
          "value": true
        },
        {
          "feature": "has_error_text",
          "op": "==",
          "value": false
        }
      ]
    },
    {
      "id": "mostly_nonempty_results",
      "label": "goodcase",
      "weight": 0.35,
      "group": "result_evidence",
      "group_cap": 0.45,
      "description": "多数步骤产生非空结果。",
      "all": [
        {
          "feature": "step_count",
          "op": ">=",
          "value": 1
        },
        {
          "feature": "nonempty_result_ratio",
          "op": ">=",
          "value": 0.7
        }
      ]
    }
  ]
}
```

