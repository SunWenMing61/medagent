# Agent Memory / Retrieval v2 离线评测

本次运行的是可复现、无外部 API 的确定性回归基准，报告位于 `medagent-backend/evals/reports/memory_retrieval_v2_latest.json`。数据集包含 10 个针对医学编码、药名、数值约束的检索难例和 4 个跨租户/Assistant 来源 Memory 隔离用例。

| 指标 | 旧基线 | v2 | 绝对提升 |
|---|---:|---:|---:|
| Retrieval MRR | 0.45 | 1.00 | +0.55 |
| Retrieval Hit Rate@1 | 0.20 | 1.00 | +0.80 |
| Memory MRR | 0.75 | 1.00 | +0.25 |
| Memory 泄漏用例率 | 1.00 | 0.00 | -1.00 |

基线是 Dense/Sparse 加权排序和未按 namespace/source-role 隔离的 flat Memory；v2 是 Exact + Dense + Sparse RRF 与 tenant/user/source-role 前置过滤。运行命令：

```powershell
python evals/runners/run_memory_retrieval_v2_evals.py
```

这些数值是小型合成回归集上的架构能力测量，不代表真实临床正确率、在线向量库质量或 LLM 医学能力，也不能与公开医学 QA 榜单横向比较。上线验收仍应使用真实脱敏查询集，报告 Recall@K、MRR、nDCG、约束满足率、冲突识别率、P95 延迟以及人工医学评审结果。
