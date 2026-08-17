# 混合检索固定 A/B 评测

评测使用固定的 10 个无患者数据难例，同时运行 Dense-only 基线和生产检索中的
Dense + Sparse + Exact + RRF 融合规则。固定数据集用于比较提示词、模型或检索策略
修改前后的相对变化，不代表真实临床效果。

运行：

```bash
cd medagent-backend
python evals/runners/run_hybrid_retrieval_comparison.py
```

报告写入 `evals/reports/hybrid_retrieval_comparison_latest.json`。登录后也可在前端
“检索调试与可观测性”页面点击“重新测试”，页面会显示 Accuracy@1、Precision、
Recall、NDCG、MRR 以及相对 Dense 基线的百分点变化。

## 2026-08-08 当前结果

| 指标 | Dense-only | 混合检索 | 绝对提升 |
|---|---:|---:|---:|
| Accuracy@1 | 20.00% | 100.00% | +80.00 个百分点 |
| Recall@1 | 20.00% | 100.00% | +80.00 个百分点 |
| Recall@3 | 40.00% | 100.00% | +60.00 个百分点 |
| NDCG@3 | 30.00% | 100.00% | +70.00 个百分点 |
| MRR | 41.67% | 100.00% | +58.33 个百分点 |

以上是用于版本回归的固定合成难例结果，不应解释为临床准确率。
