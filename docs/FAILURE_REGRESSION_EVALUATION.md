# 固定测试集与故障归因回归评测

这套评测用于回答一个具体问题：修改提示词、模型或检索策略后，系统究竟变好了还是变差了，以及失败发生在哪一层。

## 固定资产

- 测试集：`medagent-backend/evals/datasets/failure_taxonomy_v1.jsonl`
- 捕获结果格式：`medagent-backend/evals/captured_run.schema.json`
- 评分器：`medagent-backend/app/evaluation/failure_taxonomy.py`
- 命令行：`medagent-backend/evals/runners/run_failure_regression_evals.py`

测试集包含 12 个固定用例和固定证据快照，覆盖事实检索、用药安全、表格读取、相邻分块、FDA/PubMed 路由、对比任务、摘要任务、无证据回答和急症任务。报告记录测试集版本及 SHA-256；基线和候选版本的 SHA-256 不一致时禁止比较，防止测试题变化造成虚假提升。

## 四类故障如何区分

| 类型 | 判定依据 | 典型原因 |
|---|---|---|
| `retrieval_failure` | Top-K 没有命中标注证据，或固定事实覆盖率不足 | Query 改写丢词、召回不足、重排错误 |
| `answer_hallucination` | 出现明确错误事实、引用未检索证据、结构化声明没有依据 | Prompt 约束变弱、模型编造、引用绑定失效 |
| `tool_parameter_error` | 必需工具未调用、参数不满足约束、出现 `TOOL_INPUT_INVALID` 等错误 | 参数名/类型错误、ID 丢失、Top-K 越界 |
| `task_incomplete` | 未进入允许终态、答案为空或必答要点缺失 | 提前结束、只回答一部分、预算或流程中断 |

每个用例同时保留四个布尔故障标记，便于观察连锁故障；`primary_failure` 按“工具参数 → 检索 → 幻觉 → 未完成”的上游优先级给出主要根因。

评分完全采用确定性标注规则，不调用 LLM Judge，因此不会因为评委模型或温度变化而漂移。

## 捕获一次真实运行

对每个固定用例执行当前候选系统，并逐行写入 JSONL。每行至少包含：

```json
{
  "case_id": "rag_htn_threshold",
  "status": "completed",
  "answer": "…… [ev_fixed_htn_01]",
  "retrieved_evidence": [
    {"evidence_id": "ev_fixed_htn_01", "content": "……", "score": 0.92}
  ],
  "citations": ["ev_fixed_htn_01"],
  "claims": [
    {"claim": "……", "citation_ids": ["ev_fixed_htn_01"]}
  ],
  "tool_calls": [
    {
      "name": "local_knowledge_base",
      "arguments": {"query": "高血压诊断阈值", "top_k": 10},
      "status": "success",
      "error_code": null
    }
  ]
}
```

固定题目不包含真实患者信息，因此评测捕获文件可以保存工具参数。生产请求仍只记录参数哈希，不应为了评测而放宽生产隐私策略。

建议把每次配置写成独立 JSON，例如：

```json
{
  "prompt_version": "answer_generator_v2",
  "model": "candidate-model",
  "retrieval_strategy": "hybrid_rrf_rerank_v3",
  "git_commit": "<commit sha>"
}
```

## 运行和比较

在 `medagent-backend` 目录执行：

```powershell
python evals/runners/run_failure_regression_evals.py validate

python evals/runners/run_failure_regression_evals.py score `
  evals/runs/baseline.jsonl `
  --run-id baseline-v1 `
  --config evals/runs/baseline-config.json `
  --output evals/reports/failure-baseline-v1.json

python evals/runners/run_failure_regression_evals.py score `
  evals/runs/candidate.jsonl `
  --run-id candidate-v2 `
  --config evals/runs/candidate-config.json `
  --output evals/reports/failure-candidate-v2.json

python evals/runners/run_failure_regression_evals.py compare `
  evals/reports/failure-baseline-v1.json `
  evals/reports/failure-candidate-v2.json `
  --output evals/reports/failure-comparison-v2.json `
  --fail-on-regression
```

`--fail-on-regression` 在出现回退时返回退出码 2，可直接作为 CI 门禁。

## 如何判断变好或变差

报告包含四个组件分数、严格通过率和总分：检索 30%、回答有据性 30%、工具参数正确性 20%、任务完成度 20%。

报告还会直接输出常用数值：`accuracy`（全部条件均通过的端到端准确率）、
`precision_at_k`、`recall_at_k`、`hit_rate_at_k`、`mrr`、
`hallucination_free_rate`、`tool_parameter_accuracy` 和
`task_completion_accuracy`。检索指标只在要求检索的用例上取平均，工具参数准确率
只在要求调用工具的用例上取平均，不会用无需检索或无需工具的题目虚增分数。

- `better`：总分提高，且没有新增失败用例或恶化的故障类型。
- `worse`：总分下降，或通过用例发生明确回退。
- `mixed`：有修复也有新增回退，需要看 `fixed_cases` 和 `regressed_cases`。
- `unchanged`：所有可比指标和逐题结果不变。

不要覆盖旧基线。只有人工确认候选版本在四类故障上都没有不可接受的回退后，才把候选报告复制为下一版基线。

当前模型首次真实在线基线见
[`CURRENT_MODEL_BASELINE_EVALUATION.md`](CURRENT_MODEL_BASELINE_EVALUATION.md)，机器可读报告位于
`medagent-backend/evals/reports/failure_current_model_baseline_v1.json`。
