"""
GraphRAG（图检索增强生成）相关的 Pydantic 模式定义。

包含图实体、图关系、图搜索请求与响应的序列化模型。
"""

# 从 pydantic 导入 BaseModel 和 Field
from pydantic import BaseModel, Field
# 从 Python 标准库导入 datetime，用于时间戳字段
from datetime import datetime
# 导入列表和可选类型
from typing import List, Optional


class GraphEntityResponse(BaseModel):
    """图实体响应模型，返回图谱中提取的医疗实体信息。"""
    # 实体 ID
    id: int
    # 所属知识库 ID
    kb_id: int
    # 实体类型：disease / drug / symptom / treatment / exam
    entity_type: str
    # 实体名称
    name: str
    # 元数据（JSON 格式）
    metadata_json: Optional[str] = None
    # 创建时间
    created_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class GraphRelationResponse(BaseModel):
    """图关系响应模型，返回实体之间的语义关系。"""
    # 关系 ID
    id: int
    # 源实体 ID
    source_entity_id: int
    # 目标实体 ID
    target_entity_id: int
    # 关系类型：treats / causes / side_effect / indicates / contraindicates
    relation_type: str
    # 元数据（JSON 格式）
    metadata_json: Optional[str] = None
    # 创建时间
    created_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性读取数据
        from_attributes = True


class GraphSearchRequest(BaseModel):
    """图搜索请求模型，用于在图谱中查询相关实体和关系。"""
    # 搜索查询文本
    query: str = Field(..., min_length=1, description="搜索查询文本")
    # 知识库 ID，限定搜索范围
    kb_id: int = Field(..., description="知识库 ID")
    # 搜索深度（BFS 层数），默认 2
    max_depth: int = Field(default=2, ge=1, le=5, description="图搜索深度")
    # 可选：限制返回结果数量
    top_k: Optional[int] = Field(default=20, description="返回结果数量上限")


class GraphSearchResponse(BaseModel):
    """图搜索响应模型，返回图谱搜索结果。"""
    # 搜索到的实体列表
    entities: List[GraphEntityResponse] = []
    # 搜索到的关系列表
    relations: List[GraphRelationResponse] = []
    # 上下文文本（格式化后的子图描述，适合 LLM 使用）
    graph_context: str = ""

