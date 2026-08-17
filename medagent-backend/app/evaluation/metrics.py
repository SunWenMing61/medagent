"""RAG 与多Agent系统评估指标计算模块。

提供工业级 RAG 评估指标实现，包括：
1. 检索指标：衡量检索模块从知识库中找到相关文档的能力
2. 生成指标：衡量 LLM 基于检索结果生成回答的质量
3. 分类指标：衡量问题分类器的准确率

所有指标函数均接受统一格式的数据，便于组合使用。
"""

import math
import re
from collections import Counter
from typing import List, Dict, Set, Optional, Tuple, Callable


# ==============================================================================
# 1. 检索指标（Retrieval Metrics）
# ==============================================================================

def compute_precision_at_k(
    retrieved: List[int],
    relevant: Set[int],
    k: int = None,
) -> float:
    """计算 Precision@k：在 top-k 检索结果中，相关文档的比例。

    Precision@k = |relevant ∩ retrieved_top_k| / k

    Args:
        retrieved: 检索返回的文档 ID 列表（按相关性降序）
        relevant: 实际相关的文档 ID 集合
        k: 评估的截断位置，默认为 len(retrieved)

    Returns:
        0.0 ~ 1.0 的精度值
    """
    if k is None:
        k = len(retrieved)
    if k <= 0 or not retrieved:
        return 0.0
    top_k = list(dict.fromkeys(retrieved))[:k]
    if not top_k:
        return 0.0
    return len([doc_id for doc_id in top_k if doc_id in relevant]) / k


def compute_recall_at_k(
    retrieved: List[int],
    relevant: Set[int],
    k: int = None,
) -> float:
    """计算 Recall@k：在 top-k 检索结果中，覆盖了多少比例的相关文档。

    Recall@k = |relevant ∩ retrieved_top_k| / |relevant|

    Args:
        retrieved: 检索返回的文档 ID 列表（按相关性降序）
        relevant: 实际相关的文档 ID 集合
        k: 评估的截断位置，默认为 len(retrieved)

    Returns:
        0.0 ~ 1.0 的召回率值；空 Ground Truth 必须由上层标记 N/A
    """
    if k is None:
        k = len(retrieved)
    if k <= 0 or not retrieved:
        return 0.0
    if not relevant:
        return 0.0
    top_k = list(dict.fromkeys(retrieved))[:k]
    return len([doc_id for doc_id in top_k if doc_id in relevant]) / len(relevant)


def compute_f1_at_k(
    retrieved: List[int],
    relevant: Set[int],
    k: int = None,
) -> float:
    """计算 F1@k：Precision@k 和 Recall@k 的调和平均数。

    F1@k = 2 * P@k * R@k / (P@k + R@k)

    Returns:
        0.0 ~ 1.0 的 F1 值；如果 P@k + R@k == 0，返回 0.0
    """
    p = compute_precision_at_k(retrieved, relevant, k)
    r = compute_recall_at_k(retrieved, relevant, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def compute_mrr(
    retrieved: List[int],
    relevant: Set[int],
) -> float:
    """计算 MRR (Mean Reciprocal Rank)：第一个相关结果的排名的倒数。

    MRR = 1 / rank_of_first_relevant

    衡量系统能否最快找到第一个正确答案。

    Returns:
        0.0 ~ 1.0 的 MRR 值
    """
    for i, doc_id in enumerate(dict.fromkeys(retrieved)):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def compute_hit_rate(
    retrieved: List[int],
    relevant: Set[int],
    k: int = None,
) -> float:
    """计算 Hit Rate@k：top-k 结果中是否至少有一个相关文档。

    Hit Rate@k = 1 if |relevant ∩ retrieved_top_k| > 0 else 0

    Returns:
        1.0（命中）或 0.0（未命中）
    """
    if k is None:
        k = len(retrieved)
    if k <= 0 or not retrieved:
        return 0.0
    return 1.0 if any(doc_id in relevant for doc_id in list(dict.fromkeys(retrieved))[:k]) else 0.0


def compute_ndcg_at_k(
    retrieved: List[int],
    relevance_scores: Dict[int, float],
    k: int = None,
) -> float:
    """计算 NDCG@k (Normalized Discounted Cumulative Gain)。

    考虑排序位置和相关性等级的综合指标，比 Precision@k 更精细。

    Args:
        retrieved: 检索返回的文档 ID 列表
        relevance_scores: {doc_id: 相关性分数} 的映射
        k: 截断位置

    Returns:
        0.0 ~ 1.0 的 NDCG 值
    """
    if k is None:
        k = len(retrieved)
    if k <= 0 or not retrieved:
        return 0.0

    top_k = list(dict.fromkeys(retrieved))[:k]

    # DCG: 按检索顺序累加折损后的相关性得分
    dcg = 0.0
    for i, doc_id in enumerate(top_k):
        rel = relevance_scores.get(doc_id, 0.0)
        if i == 0:
            dcg += rel
        else:
            dcg += rel / math.log2(i + 1)

    # IDCG: 理想排序下的 DCG（按相关性降序排列）
    ideal = sorted(relevance_scores.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal):
        if i == 0:
            idcg += rel
        else:
            idcg += rel / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0


def compute_retrieval_metrics(
    retrieved: List[int],
    relevant: Set[int],
    relevance_scores: Optional[Dict[int, float]] = None,
    k_values: List[int] = None,
) -> Dict[str, float]:
    """一站式计算所有检索指标。

    Args:
        retrieved: 检索返回的文档 ID 列表
        relevant: 相关文档 ID 集合
        relevance_scores: 可选的分级相关性评分 {doc_id: score}
        k_values: 要计算的 k 值列表，默认 [1, 3, 5, 10]

    Returns:
        包含所有指标值的字典，如:
        {"precision@1": 1.0, "recall@5": 0.8, "f1@5": 0.89, "mrr": 1.0,
         "hit_rate@3": 1.0, "ndcg@5": 0.95}
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    metrics = {"mrr": compute_mrr(retrieved, relevant)}

    if relevance_scores is None:
        # 如果没有分级评分，使用二元相关性（相关=1, 不相关=0）
        relevance_scores = {doc_id: 1.0 for doc_id in relevant}

    for k in k_values:
        metrics[f"precision@{k}"] = compute_precision_at_k(retrieved, relevant, k)
        metrics[f"recall@{k}"] = compute_recall_at_k(retrieved, relevant, k)
        metrics[f"f1@{k}"] = compute_f1_at_k(retrieved, relevant, k)
        metrics[f"hit_rate@{k}"] = compute_hit_rate(retrieved, relevant, k)
        metrics[f"ndcg@{k}"] = compute_ndcg_at_k(retrieved, relevance_scores, k)

    # 综合指标：多 k 平均
    for base in ("precision", "recall", "f1"):
        vals = [metrics[f"{base}@{k}"] for k in k_values]
        metrics[f"avg_{base}"] = sum(vals) / len(vals)

    return metrics


# ==============================================================================
# 2. 生成指标（Generation Metrics）
# ==============================================================================

def compute_faithfulness(
    answer: str,
    context_sentences: List[str],
) -> float:
    """计算忠实度：回答中的主张在多大程度上被检索到的上下文所支持。

    通过检查回答中的关键 Claims 是否能从上下文中找到依据来评估。

    实现策略：
    1. 从回答中提取关键名词短语/数字/实体（简化实现）
    2. 检查这些元素是否在上下文中出现
    3. 返回支持的比率

    更精确的实现应使用 LLM 作为 Judge 来评估每个 Claim。此处
    使用基于 N-gram 重叠的近似方法。

    Args:
        answer: 生成的回答文本
        context_sentences: 检索到的上下文文本列表

    Returns:
        0.0 ~ 1.0 的忠实度分数
    """
    if not answer or not context_sentences:
        return 0.0

    # 将上下文合并为一个大文本用于匹配
    context_text = " ".join(context_sentences).lower()

    # 从回答中提取关键元素
    # 1. 数字（包括百分比、剂量等医学关键信息）
    numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', answer))

    # 2. 引号内的内容（常为引用原文）
    quotes = set(re.findall(r'"([^"]+)"', answer))

    # 3. 医学实体关键词（通过大小写和术语模式）
    # 假设大写开头的医学术语和长名词短语
    words = answer.split()
    medical_terms = set()
    for w in words:
        clean_w = w.strip(",.!?;:()[]{}""''")
        if len(clean_w) > 3 and clean_w[0].isupper():
            medical_terms.add(clean_w.lower())

    # 统计支持的 claims
    supported_claims = 0
    total_claims = 0

    # 检查数字是否在上下文中
    for num in numbers:
        total_claims += 1
        clean_num = num.lower()
        if clean_num in context_text:
            supported_claims += 1

    # 检查引文
    for quote in quotes:
        total_claims += 1
        if quote.lower() in context_text:
            supported_claims += 1

    # 检查医学术语
    for term in medical_terms:
        total_claims += 1
        if term in context_text:
            supported_claims += 1

    # 如果没有提取到任何 claims，使用简单的文本重叠作为后备
    if total_claims == 0:
        answer_sentences = [s.strip() for s in re.split(r'[.!?\n]', answer) if s.strip()]
        if not answer_sentences:
            return 1.0  # empty answer = faithful

        supported = 0
        for sent in answer_sentences:
            if not sent:
                supported += 1
                continue
            sent_clean = sent.lower()
            key_words = []
            for w in sent_clean.split():
                w = w.strip()
                for ch in ".,!?;:()[]":  # strip punctuation
                    w = w.replace(ch, "")
                if len(w) > 3:
                    key_words.append(w)
            chinese_blocks = re.findall(r'[一-鿿]{2,}', sent_clean)
            for block in chinese_blocks:
                for n in (2, 3):
                    for i in range(len(block) - n + 1):
                        gram = block[i:i+n]
                        if gram.lower() in context_text or gram in context_text:
                            key_words.append(gram)
            if not key_words:
                supported += 1
                continue
            match_count = sum(1 for w in key_words if w.lower() in context_text)
            if match_count / len(key_words) >= 0.2:
                supported += 1
        return supported / len(answer_sentences)

    return supported_claims / total_claims if total_claims > 0 else 1.0


def compute_answer_relevancy(
    question: str,
    answer: str,
) -> float:
    """计算答案相关性：回答是否直接针对用户问题。

    通过检查回答中是否包含了问题中的关键概念来衡量。

    Args:
        question: 用户原始问题
        answer: 生成的回答

    Returns:
        0.0 ~ 1.0 的相关性分数
    """
    if not question or not answer:
        return 0.0

    q_lower = question.lower()
    a_lower = answer.lower()

    # 提取问题的关键词（去除停用词）
    stop_words = {"的", "了", "是", "在", "什么", "怎么", "如何", "哪些",
                  "请", "帮", "我", "你", "吗", "呢", "吧", "啊",
                  "the", "a", "an", "is", "are", "was", "were",
                  "what", "how", "why", "when", "where", "which",
                  "please", "help", "can", "could", "would", "should"}

    # 对中文文本的提取策略：提取英文词 + 中文 n-gram
    q_words = set()
    for w in q_lower.split():
        w = w.strip(".,!?;:'()[]")
        if w and w not in stop_words and len(w) > 1:
            q_words.add(w)
    import re as _cjk_re
    for block in _cjk_re.findall(r'[一-鿿]+', q_lower):
        if len(block) >= 2:
            q_words.add(block)
        for n in (2, 3):
            for i in range(len(block) - n + 1):
                gram = block[i:i+n]
                if gram not in stop_words:
                    q_words.add(gram)
    if not q_words:
        return 1.0

    # 计算问题关键词在回答中出现的比例
    matched = sum(1 for w in q_words if w in a_lower)
    return matched / len(q_words)


def compute_answer_correctness(
    answer: str,
    expected_answer: str,
) -> float:
    """计算答案正确性：生成的回答与标准答案的匹配程度。

    使用 ROUGE-L（最长公共子序列）的简化版本，结合关键词重叠。

    Args:
        answer: 生成的回答
        expected_answer: 期望的标准答案

    Returns:
        0.0 ~ 1.0 的正确性分数
    """
    if not answer or not expected_answer:
        return 0.0

    a_lower = answer.lower().strip()
    e_lower = expected_answer.lower().strip()

    # 方法1：计算 token F1（基于分词）
    def tokenize(text: str) -> Set[str]:
        tokens = re.findall(r'\b[a-z]+\b', text)
        tokens += [t for t in re.split(r'[\s,，。.！?？、；;：:]+', text) if len(t) > 1]
        return set(tokens)

    a_tokens = tokenize(a_lower)
    e_tokens = tokenize(e_lower)

    if not e_tokens:
        return 1.0 if not a_tokens else 0.0

    # 精确匹配
    exact_match = 1.0 if a_lower == e_lower else 0.0

    # Token 重叠
    intersection = a_tokens & e_tokens
    if not a_tokens or not e_tokens:
        token_f1 = 0.0
    else:
        precision = len(intersection) / len(a_tokens)
        recall = len(intersection) / len(e_tokens)
        token_f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0

    # 方法2：最长公共子序列比例 (ROUGE-L 简化)
    def lcs_ratio(a: str, b: str) -> float:
        """计算 LCS 长度占较长字符串的比例。"""
        if not a or not b:
            return 0.0
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        lcs_len = dp[m][n]
        return lcs_len / max(len(a), len(b))

    rouge_l = lcs_ratio(a_lower, e_lower)

    # 综合评分：Exact Match (权重0.2) + Token F1 (权重0.4) + ROUGE-L (权重0.4)
    # 但精确匹配是最高优先级
    if exact_match == 1.0:
        return 1.0

    return 0.2 * exact_match + 0.4 * token_f1 + 0.4 * rouge_l


def compute_generation_metrics(
    question: str,
    answer: str,
    expected_answer: str,
    context_sentences: List[str] = None,
) -> Dict[str, float]:
    """一站式计算所有生成指标。

    Args:
        question: 用户问题
        answer: 生成的回答
        expected_answer: 标准答案
        context_sentences: 检索到的上下文文本列表

    Returns:
        包含忠实度、相关性、正确性等指标的字典
    """
    metrics = {}
    metrics["faithfulness"] = compute_faithfulness(
        answer, context_sentences or []
    )
    metrics["answer_relevancy"] = compute_answer_relevancy(question, answer)
    metrics["answer_correctness"] = compute_answer_correctness(answer, expected_answer)
    return metrics


# ==============================================================================
# 3. 分类指标（Classification Metrics）
# ==============================================================================

def compute_classification_metrics(
    predictions: List[str],
    ground_truth: List[str],
    label_set: Set[str] = None,
) -> Dict[str, float]:
    """计算问题分类器的评估指标。

    Args:
        predictions: 预测的类别标签列表
        ground_truth: 真实的类别标签列表
        label_set: 所有可能的类别标签集合

    Returns:
        包含准确率、宏平均精确率/召回率/F1 的字典
    """
    if not predictions or not ground_truth:
        return {"accuracy": 0.0, "macro_precision": 0.0, "macro_recall": 0.0, "macro_f1": 0.0}

    if label_set is None:
        label_set = set(ground_truth) | set(predictions)

    # 准确率 (Accuracy)
    correct = sum(1 for p, g in zip(predictions, ground_truth) if p == g)
    accuracy = correct / len(predictions)

    # 每个类别的指标
    per_class_metrics = {}
    for label in label_set:
        # True Positives, False Positives, False Negatives
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p == label and g == label)
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p == label and g != label)
        fn = sum(1 for p, g in zip(predictions, ground_truth) if p != label and g == label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0

        per_class_metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(1 for g in ground_truth if g == label),
        }

    # 宏平均 (Macro Average)
    macro_precision = sum(m["precision"] for m in per_class_metrics.values()) / len(per_class_metrics)
    macro_recall = sum(m["recall"] for m in per_class_metrics.values()) / len(per_class_metrics)
    macro_f1 = sum(m["f1"] for m in per_class_metrics.values()) / len(per_class_metrics)

    return {
        "accuracy": accuracy,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "per_class": per_class_metrics,
    }


# ==============================================================================
# 4. 工具函数
# ==============================================================================

def relevance_f1_score(
    retrieved: List[int],
    relevant: Set[int],
) -> float:
    """快捷计算整体检索 F1（k=全部结果）。"""
    return compute_f1_at_k(retrieved, relevant)


def format_metrics_table(
    metrics: Dict[str, float],
    title: str = "Metrics Report",
) -> str:
    """将指标字典格式化为易读的表格字符串。"""
    lines = [
        f"=" * 60,
        f"  {title}",
        f"=" * 60,
    ]

    # 分组显示
    retrieval_keys = [k for k in metrics if any(x in k for x in
                      ["precision", "recall", "f1@", "hit_rate", "mrr", "ndcg", "avg_"])]
    generation_keys = [k for k in metrics if any(x in k for x in
                       ["faithful", "relevancy", "correctness"])]
    other_keys = [k for k in metrics if k not in retrieval_keys and k not in generation_keys]

    if retrieval_keys:
        lines.append(f"\n  📥 检索指标:")
        lines.append(f"  {'-' * 40}")
        for k in sorted(retrieval_keys):
            v = metrics[k]
            lines.append(f"    {k:25s} = {v:>8.4f}" if isinstance(v, float) else f"    {k:25s} = {v}")

    if generation_keys:
        lines.append(f"\n  📝 生成指标:")
        lines.append(f"  {'-' * 40}")
        for k in sorted(generation_keys):
            v = metrics[k]
            lines.append(f"    {k:25s} = {v:>8.4f}" if isinstance(v, float) else f"    {k:25s} = {v}")

    if other_keys:
        lines.append(f"\n  📊 综合指标:")
        lines.append(f"  {'-' * 40}")
        for k in sorted(other_keys):
            v = metrics[k]
            if isinstance(v, dict):
                lines.append(f"    {k:25s} = (嵌套字典)")
            else:
                lines.append(f"    {k:25s} = {v:>8.4f}" if isinstance(v, float) else f"    {k:25s} = {v}")

    lines.append(f"\n" + "=" * 60)
    return "\n".join(lines)


def generate_evaluation_report(
    retrieval_results: List[Dict] = None,
    generation_results: List[Dict] = None,
    classification_results: Dict = None,
) -> str:
    """生成完整的评估报告。

    Args:
        retrieval_results: 检索结果列表，每项包含 retrieved/relevant/relevance_scores
        generation_results: 生成结果列表，每项包含 question/answer/expected/context
        classification_results: 分类结果字典，包含 predictions/ground_truth

    Returns:
        格式化的评估报告字符串
    """
    sections = []
    all_metrics = {}

    # 1. 检索评估
    if retrieval_results:
        total_metrics = {}
        count = len(retrieval_results)
        for result in retrieval_results:
            metrics = compute_retrieval_metrics(
                result.get("retrieved", []),
                result.get("relevant", set()),
                result.get("relevance_scores"),
            )
            for k, v in metrics.items():
                if k not in total_metrics:
                    total_metrics[k] = 0.0
                total_metrics[k] += v

        # 计算平均值
        avg_metrics = {k: v / count for k, v in total_metrics.items()}
        all_metrics.update(avg_metrics)
        sections.append(format_metrics_table(avg_metrics, f"📥 检索评估 (共 {count} 个查询)"))

    # 2. 生成评估
    if generation_results:
        total_metrics = {}
        count = len(generation_results)
        for result in generation_results:
            metrics = compute_generation_metrics(
                result.get("question", ""),
                result.get("answer", ""),
                result.get("expected_answer", ""),
                result.get("context", []),
            )
            for k, v in metrics.items():
                if k not in total_metrics:
                    total_metrics[k] = 0.0
                total_metrics[k] += v

        avg_metrics = {k: v / count for k, v in total_metrics.items()}
        all_metrics.update(avg_metrics)
        sections.append(format_metrics_table(avg_metrics, f"📝 生成评估 (共 {count} 个问答对)"))

    # 3. 分类评估
    if classification_results:
        metrics = compute_classification_metrics(
            classification_results.get("predictions", []),
            classification_results.get("ground_truth", []),
            classification_results.get("label_set"),
        )
        all_metrics.update({k: v for k, v in metrics.items() if not isinstance(v, dict)})
        sections.append(format_metrics_table(
            {k: v for k, v in metrics.items() if not isinstance(v, dict)},
            f"🏷️ 分类评估",
        ))
        # 输出 per-class 详情
        if "per_class" in metrics:
            per_class = metrics["per_class"]
            lines = [f"\n  各类别详情:"]
            for label, m in per_class.items():
                lines.append(
                    f"    {label:20s} P={m['precision']:.3f} R={m['recall']:.3f} "
                    f"F1={m['f1']:.3f} (样本数: {m['support']})"
                )
            sections.append("\n".join(lines))

    return "\n".join(sections)
