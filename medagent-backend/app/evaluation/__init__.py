"""MedAgent 评估框架 —— RAG 与多Agent系统指标计算。

提供完整的检索和生成质量评估指标：
- 检索指标：Precision@k, Recall@k, F1@k, MRR, NDCG@k, Hit Rate
- 生成指标：Faithfulness, Answer Relevancy, Answer Correctness
- 分类指标：Accuracy, Precision, Recall, F1 (用于问题分类器评估)
- 综合报告：generate_report() 输出完整评估报告
"""

from .metrics import (
    # 检索指标
    compute_precision_at_k,
    compute_recall_at_k,
    compute_f1_at_k,
    compute_mrr,
    compute_hit_rate,
    compute_ndcg_at_k,
    compute_retrieval_metrics,
    # 生成指标
    compute_faithfulness,
    compute_answer_relevancy,
    compute_answer_correctness,
    compute_generation_metrics,
    # 分类指标
    compute_classification_metrics,
    # 综合报告
    generate_evaluation_report,
    # 工具
    relevance_f1_score,
    format_metrics_table,
)
from .judge import LLMJudge, JudgeOutput

__all__ = [
    "compute_precision_at_k",
    "compute_recall_at_k",
    "compute_f1_at_k",
    "compute_mrr",
    "compute_hit_rate",
    "compute_ndcg_at_k",
    "compute_retrieval_metrics",
    "compute_faithfulness",
    "compute_answer_relevancy",
    "compute_answer_correctness",
    "compute_generation_metrics",
    "compute_classification_metrics",
    "generate_evaluation_report",
    "relevance_f1_score",
    "format_metrics_table",
    "LLMJudge",
    "JudgeOutput",
]
