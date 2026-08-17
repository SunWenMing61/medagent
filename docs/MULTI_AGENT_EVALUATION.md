# 多 Agent 评测

`medagent-backend/evals/datasets` 提供分诊、澄清、检索规划、证据核验、答案、输出安全和端到端的版本化 JSONL 示例。它们是合成回归样例，不是临床数据集。

运行离线示例评测：

```powershell
cd medagent-backend
python evals/runners/run_agent_evals.py --output evals/reports/offline_example_latest.json
```

报告中的 `report_type=executed_offline_example_dataset` 表示代码确实执行过，但指标只适用于随仓库提供的合成样例。

## A/B/C/D 对照

- A：单 Prompt + RAG
- B：RAG + 单次输出安全后审查
- C：Supervisor + 检索 + 答案 + 安全
- D：Supervisor + 并行检索 + 证据核验 + 输入/输出双重安全

生产/预发布系统应把每次真实运行记录成 JSONL，至少带 `variant`、`executed_at` 及所测指标，再运行：

```powershell
python evals/runners/compare_abcd.py captured-real-runs.jsonl --output evals/reports/abcd-real.json
```

比较器会拒绝空输入、缺少任一变体或标记为 synthetic 的记录，从而避免生成伪造实验结论。是否默认启用 D，应基于真实 Faithfulness、引用、安全 Recall、P95 延迟和成本收益决定。
