# 导入类型提示：List 用于列表类型, Optional 用于可选类型
from typing import List, Optional
# 导入 SQLAlchemy 的 Session 类型,用于数据库会话操作
from sqlalchemy.orm import Session
# 导入 text 函数,用于执行原生 SQL 查询
from sqlalchemy import text

# 导入应用配置,获取嵌入 API 和检索参数等设置
from app.core.config import settings
# 导入文档块模型,对应 PostgreSQL 中的 document_chunk 表
from app.models.document_chunk import DocumentChunk
# 导入 PostgreSQL 的会话工厂,用于创建数据库连接
from app.db.session import PgSessionLocal


class VectorService:
    """向量搜索服务,使用 pgvector 进行余弦相似度向量检索。"""

    def _get_embedding(self, text: str) -> List[float]:
        """调用配置的嵌入 API 获取文本的向量嵌入。

        Args:
            text: 需要向量化的输入文本

        Returns:
            浮点数列表,即文本的嵌入向量
        """
        import httpx  # 内部导入 httpx 库用于发送 HTTP 请求

        api_key = settings.EMBEDDING_API_KEY  # 从配置中获取 API 密钥
        if not api_key:
            raise ValueError("EMBEDDING_API_KEY not configured")  # 未配置密钥则抛出异常

        # 向嵌入 API 发送 POST 请求,获取文本的向量表示
        response = httpx.post(
            f"{settings.EMBEDDING_API_BASE}/embeddings",  # 拼接 API 端点 URL
            headers={"Authorization": f"Bearer {api_key}"},  # 设置认证头
            json={"model": settings.EMBEDDING_MODEL, "input": text, "dimensions": 1024},  # 请求体: 模型名、输入文本、向量维度
            timeout=30,  # 设置 30 秒超时
        )
        response.raise_for_status()  # 检查响应状态码,非 2xx 则抛出异常
        data = response.json()  # 解析响应 JSON
        return data["data"][0]["embedding"]  # 从响应中提取嵌入向量

    def embed_text(self, text: str) -> List[float]:
        """对外暴露的文本嵌入接口,直接委托给内部方法。"""
        return self._get_embedding(text)

    def search(
        self,
        query: str,
        kb_ids: Optional[List[int]] = None,
        top_k: int = None,
        threshold: float = None,
    ) -> List[dict]:
        """使用 pgvector 余弦相似度搜索相似的文档块。

        Args:
            query: 查询文本
            kb_ids: 可选的知识库 ID 列表,用于限定搜索范围
            top_k: 返回的最相似结果数量,默认使用配置值
            threshold: 相似度阈值,低于此值的结果将被过滤,默认使用配置值

        Returns:
            字典列表,每个字典包含块 ID、文档 ID、知识库 ID、内容、页码和相似度
        """
        if top_k is None:
            top_k = settings.TOP_K  # 若未指定则使用配置中的默认返回条数
        if threshold is None:
            threshold = settings.SIMILARITY_THRESHOLD  # 若未指定则使用配置中的默认相似度阈值

        query_vector = self._get_embedding(query)  # 对查询文本进行向量化
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"  # 将向量列表转为 PostgreSQL 数组字符串格式

        db: Session = PgSessionLocal()  # 创建 PostgreSQL 数据库会话
        try:
            if kb_ids:
                # 如果有指定知识库 ID,则在 SQL 中添加 IN 子句过滤
                kb_placeholders = ",".join(str(k) for k in kb_ids)  # 将 kb_ids 拼成逗号分隔的字符串
                sql = text(f"""
                    SELECT id, document_id, kb_id, chunk_index, content, page_num,
                           1 - (embedding <=> '{vector_str}'::vector) AS similarity
                    FROM document_chunk
                    WHERE kb_id IN ({kb_placeholders})
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> '{vector_str}'::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """)
            else:
                # 无指定知识库,搜索所有文档块
                sql = text(f"""
                    SELECT id, document_id, kb_id, chunk_index, content, page_num,
                           1 - (embedding <=> '{vector_str}'::vector) AS similarity
                    FROM document_chunk
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> '{vector_str}'::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """)

            # 执行 SQL 查询,传入 top_k 和 threshold 参数
            rows = db.execute(sql, {"top_k": top_k, "threshold": threshold}).fetchall()
            results = []  # 初始化结果列表
            for row in rows:
                # 将每行查询结果转换为字典格式
                results.append({
                    "id": row[0],          # 文档块 ID
                    "document_id": row[1], # 所属文档 ID
                    "kb_id": row[2],       # 知识库 ID
                    "chunk_index": row[3], # 块在文档中的索引
                    "content": row[4],     # 块文本内容
                    "page_num": row[5],    # 来源页码
                    "similarity": float(row[6]),  # 余弦相似度分数
                })
            return results
        finally:
            db.close()  # 确保数据库会话被关闭


# 全局单例实例,供其他模块直接使用
vector_service = VectorService()
