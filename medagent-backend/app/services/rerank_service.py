"""重排序服务：对向量检索结果进行精排，提高 RAG 回答质量。

提供两层重排序策略：
1. 优先使用 BAAI/bge-reranker-v2-m3 交叉编码器模型（需要 sentence-transformers）
2. 降级使用 LLM API 进行基于提示词的重排序
3. 最终降级：保持原始顺序不变

使用单例模式，与项目中其他服务保持一致。
"""

# 导入类型提示：List、Dict、Optional、Any
from typing import List, Dict, Optional, Any
# 导入有序字典，用作 LRU 缓存
from collections import OrderedDict
# 导入日志记录器
import logging
# 导入 httpx，用于 LLM 降级方案中的 API 调用
import httpx
# 导入 hashlib，用于生成缓存键
import hashlib
# 导入 json，用于序列化缓存键
import json

# 导入应用配置
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── LRU 缓存配置 ─────────────────────────────────────────────────────────────────
# 最大缓存条目数：避免内存无限增长
_RERANK_CACHE_MAX_SIZE = 128


class RerankService:
    """检索结果重排序服务，对向量检索出的文本块进行语义精排。

    使用交叉编码器（Cross-Encoder）对 query 和每个 chunk 进行深度语义匹配，
    比向量检索的余弦相似度更精准，但速度较慢（适合对 top-K 结果精排）。
    """

    def __init__(self):
        """初始化重排序服务，延迟加载模型（避免启动时耗时）。"""
        # 交叉编码器模型实例（延迟加载）
        self._model = None
        # 标记模型是否尝试加载过（避免重复尝试）
        self._model_attempted = False
        # 标记是否使用 LLM 降级方案
        self._use_llm_fallback = False
        # LRU 缓存：OrderedDict，键为 (query_md5, chunks_md5) 元组，值为排序结果
        self._cache: OrderedDict = OrderedDict()

    def _get_cache_key(self, query: str, chunks: List[dict]) -> str:
        """生成用于 LRU 缓存的唯一键。

        通过对 query 和每个 chunk 的 content 进行哈希，保证相同输入复用缓存。

        Args:
            query: 查询文本
            chunks: 待重排序的文本块列表

        Returns:
            哈希字符串作为缓存键
        """
        # 提取所有块的内容并拼接
        contents = "||".join(c.get("content", "") for c in chunks)
        raw = f"{query}||{contents}"
        # 使用 MD5 生成定长哈希键
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _load_model(self) -> bool:
        """尝试加载交叉编码器模型。

        仅在首次调用时尝试加载，后续不再重试。

        Returns:
            是否成功加载模型
        """
        # 如果已经尝试过加载，直接返回结果
        if self._model_attempted:
            return self._model is not None

        # 标记为已尝试加载
        self._model_attempted = True

        try:
            # 尝试导入 sentence-transformers 的 CrossEncoder
            from sentence_transformers import CrossEncoder

            # 加载 BAAI/bge-reranker-v2-m3 交叉编码器重排序模型
            # 该模型针对中英文混合场景优化，适合医疗领域
            logger.info(
                "Loading reranker model: BAAI/bge-reranker-v2-m3 ..."
            )
            self._model = CrossEncoder(
                "BAAI/bge-reranker-v2-m3",
                # 使用 CPU 推理（如需 GPU 可改为 "cuda"）
                device="cpu",
                # 静默加载，减少日志噪音
                quiet=True,
            )
            logger.info("Reranker model loaded successfully.")
            return True
        except ImportError:
            # sentence-transformers 未安装，降级到 LLM 方案
            logger.warning(
                "sentence-transformers not installed, "
                "reranker will use LLM-based fallback"
            )
            self._use_llm_fallback = True
            return False
        except Exception as exc:
            # 模型加载失败（如网络问题、OOM 等），降级到 LLM 方案
            logger.warning(
                "Failed to load reranker model: %s, "
                "falling back to LLM reranking",
                exc,
            )
            self._use_llm_fallback = True
            return False

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """对检索结果进行重排序，返回精排后的 top_k 个结果。

        Args:
            query: 用户查询文本
            chunks: 检索到的文本块列表，每个块应包含 content、similarity 等字段
            top_k: 由混合检索器传入的候选结果上限
            threshold: 最小相似度阈值，低于此值的结果将被过滤。
                       为 None 时使用配置中的 SIMILARITY_THRESHOLD

        Returns:
            重排序后的文本块列表（按相关性降序），每块会附加 rerank_score 字段
        """
        # 如果没有待排序的数据，直接返回空列表
        if not chunks:
            return []

        # 如果只有一条数据，无需重排序，直接返回
        if len(chunks) <= 1:
            return self._enrich_and_return(chunks, query, threshold, top_k)

        # 设置阈值：参数优先，否则使用配置值，默认为 0.0（不过滤）
        if threshold is None:
            threshold = getattr(settings, "SIMILARITY_THRESHOLD", 0.0)

        # ---- LRU 缓存检查 ----
        cache_key = self._get_cache_key(query, chunks)
        if cache_key in self._cache:
            logger.debug("Rerank cache hit: %s", cache_key[:8])
            # 将命中条目移到末尾（LRU 策略）
            cached_result = self._cache.pop(cache_key)
            self._cache[cache_key] = cached_result
            # 从缓存结果中切片并应用阈值过滤
            return self._apply_threshold_and_top_k(
                cached_result, threshold, top_k
            )

        # ---- 执行重排序 ----
        try:
            # 尝试加载模型（首次调用时才真正加载）
            if self._load_model():
                # 交叉编码器重排序
                reranked = self._rerank_with_cross_encoder(query, chunks)
            elif self._use_llm_fallback:
                # LLM 降级方案
                reranked = self._rerank_with_llm(query, chunks)
            else:
                # 所有方案均不可用，保持原始顺序
                logger.info("No reranker available, keeping original order")
                reranked = list(chunks)
        except Exception as exc:
            # 重排序过程中发生异常，记录警告并保持原始顺序
            logger.warning("Reranking failed: %s, keeping original order", exc)
            reranked = list(chunks)

        # ---- 缓存结果（LRU 策略） ----
        if len(self._cache) >= _RERANK_CACHE_MAX_SIZE:
            # 缓存满时移除最久未使用的条目（FIFO）
            self._cache.popitem(last=False)
        self._cache[cache_key] = reranked

        # 应用阈值过滤和 top_k 截断
        return self._apply_threshold_and_top_k(reranked, threshold, top_k)

    def _rerank_with_cross_encoder(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """使用交叉编码器模型进行重排序。

        将 (query, chunk_content) 配对输入模型，得到语义匹配分数。
        交叉编码器比双编码器（向量检索）精度更高，因为 query 和 chunk
        可以在 Transformer 层中深度交互。

        Args:
            query: 用户查询文本
            chunks: 待排序的文本块列表

        Returns:
            按语义相关性降序排列的文本块列表（含 rerank_score 字段）
        """
        # 如果模型未成功加载，抛出异常以触发降级
        if self._model is None:
            raise RuntimeError("Cross-encoder model not loaded")

        # 构建模型输入：[(query, chunk1_content), (query, chunk2_content), ...]
        sentence_pairs = [
            (query, c.get("content", "")) for c in chunks
        ]

        # 批量计算语义匹配分数
        # CrossEncoder.predict() 返回每个 pair 的相关性分数列表
        scores = self._model.predict(sentence_pairs)

        # 将分数附加到每个块上，创建 (score, chunk) 配对
        scored = []
        for i, chunk in enumerate(chunks):
            # scores[i] 是 float 或 numpy 标量，统一转为 float
            score = float(scores[i]) if hasattr(scores, "__getitem__") else float(scores)
            chunk_copy = dict(chunk)
            chunk_copy["rerank_score"] = round(score, 6)  # 保留 6 位小数
            scored.append((score, chunk_copy))

        # 按分数降序排列（分数越高越相关）
        scored.sort(key=lambda x: x[0], reverse=True)

        # 提取排序后的块列表
        return [item[1] for item in scored]

    def _rerank_with_llm(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """使用 LLM 进行基于提示词的重排序（降级方案）。

        通过 LLM 对每个 chunk 进行相关性评分（0-10），然后按评分排序。
        此方案速度较慢但无需额外模型依赖。

        Args:
            query: 用户查询文本
            chunks: 待排序的文本块列表

        Returns:
            按 LLM 评分降序排列的文本块列表（含 rerank_score 字段）
        """
        # 检查 LLM API 是否已配置
        api_key = settings.LLM_API_KEY
        if not api_key:
            # 无 API 密钥时直接返回原始顺序
            logger.warning("LLM_API_KEY not configured, keeping original order")
            return list(chunks)

        # 逐块调用 LLM 进行相关性评分
        scored = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if not content.strip():
                # 空内容直接评 0 分
                chunk_copy = dict(chunk)
                chunk_copy["rerank_score"] = 0.0
                scored.append((0.0, chunk_copy))
                continue

            try:
                # 构建评分提示词（中文）
                prompt = (
                    f"你是一个医疗信息检索相关性评估专家。请评估以下文本片段"
                    f"与用户查询的相关性，给出 0-10 的整数评分。\n\n"
                    f"用户查询：{query}\n\n"
                    f"文本片段：{content[:500]}\n\n"  # 截断前 500 字符避免超长
                    f"请只返回一个 0-10 的整数评分，不要有任何其他文字。"
                )

                # 调用 LLM API
                with httpx.Client(timeout=10) as client:
                    response = client.post(
                        f"{settings.LLM_API_BASE}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": settings.LLM_MODEL,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.1,       # 低温度，保证稳定性
                            "max_tokens": 10,          # 只需输出一个数字
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    # 提取评分
                    raw_score = (
                        result["choices"][0]["message"]["content"]
                        .strip()
                    )
                    # 尝试解析为浮点数
                    try:
                        score = float(raw_score)
                    except (ValueError, TypeError):
                        # 解析失败时使用默认评分（保持原有顺序的中间值）
                        score = 5.0

                    # 归一化到 0-1 范围（便于与 cross-encoder 结果比较）
                    score = max(0.0, min(score / 10.0, 1.0))

            except Exception as exc:
                # LLM 评分失败，记录警告并使用中等评分
                logger.debug("LLM rerank score failed for chunk: %s", exc)
                score = 5.0  # 中等评分，不偏袒也不降级

            chunk_copy = dict(chunk)
            chunk_copy["rerank_score"] = round(score, 6)
            scored.append((score, chunk_copy))

        # 按评分降序排列
        scored.sort(key=lambda x: x[0], reverse=True)

        return [item[1] for item in scored]

    def _apply_threshold_and_top_k(
        self,
        chunks: List[Dict[str, Any]],
        threshold: float,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """对重排序后的结果应用阈值过滤和 top_k 截断。

        Args:
            chunks: 重排序后的文本块列表
            threshold: 相似度阈值
            top_k: 返回的最大结果数

        Returns:
            过滤和截断后的文本块列表
        """
        filtered = []
        for c in chunks:
            # 优先使用 rerank_score，若不存在则使用原始 similarity
            score = c.get("rerank_score") or c.get("similarity") or 0.0
            if score >= threshold:
                filtered.append(c)

        # 截取前 top_k 个结果
        return filtered[:top_k]

    def _enrich_and_return(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        threshold: float,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """处理只有一个块或空块的场景：补充 rerank_score 字段后返回。

        Args:
            chunks: 文本块列表（0 或 1 个元素）
            query: 用户查询（此处未使用，仅为接口一致性）
            threshold: 相似度阈值
            top_k: 返回的最大结果数

        Returns:
            添加了 rerank_score 字段的块列表
        """
        result = []
        for c in chunks:
            c_copy = dict(c)
            # 如果没有 rerank_score，使用原始 similarity 或 0
            if "rerank_score" not in c_copy:
                c_copy["rerank_score"] = c_copy.get("similarity", 0.0)
            result.append(c_copy)

        # 应用阈值过滤
        return self._apply_threshold_and_top_k(result, threshold, top_k)

    def clear_cache(self) -> None:
        """清空 LRU 缓存。"""
        self._cache.clear()
        logger.info("Rerank cache cleared")


# 全局单例实例，供其他模块直接使用
rerank_service = RerankService()
