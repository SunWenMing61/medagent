"""
GraphRAG（图检索增强生成）API 路由。

提供图谱实体提取、图搜索和混合查询（图+向量）的 HTTP 接口。
所有接口需要 JWT 认证。
"""

# 从 FastAPI 导入路由、依赖注入、HTTP 异常和状态码
from fastapi import APIRouter, Depends, HTTPException, Query
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session
# 导入类型提示
from typing import List, Optional

# 导入认证和权限相关的依赖
from app.core.dependencies import get_current_user
# 导入数据库会话工厂
from app.db.session import get_mysql_db
# 导入用户模型
from app.models.user import User
# 导入知识图谱的 ORM 模型
from app.models.knowledge_graph import GraphEntity, GraphRelation
# 导入图谱相关的 Pydantic 模式
from app.schemas.graph import (
    GraphEntityResponse,
    GraphRelationResponse,
    GraphSearchRequest,
    GraphSearchResponse,
)
# 导入图谱服务（实体提取、图搜索、混合搜索）
from app.services.graph_service import (
    extract_entities,
    search_graph,
    get_graph_context,
    get_store,
    add_entity,
    add_relation,
)

# 创建图谱路由实例
router = APIRouter()


def _entity_to_response(entity: GraphEntity) -> GraphEntityResponse:
    """将 GraphEntity ORM 模型转换为 GraphEntityResponse 响应模型。"""
    return GraphEntityResponse(
        id=entity.id,
        kb_id=entity.kb_id,
        entity_type=entity.entity_type,
        name=entity.name,
        metadata_json=entity.metadata_json,
        created_at=entity.created_at,
    )


def _relation_to_response(relation: GraphRelation) -> GraphRelationResponse:
    """将 GraphRelation ORM 模型转换为 GraphRelationResponse 响应模型。"""
    return GraphRelationResponse(
        id=relation.id,
        source_entity_id=relation.source_entity_id,
        target_entity_id=relation.target_entity_id,
        relation_type=relation.relation_type,
        metadata_json=relation.metadata_json,
        created_at=relation.created_at,
    )


# ==================== 实体提取接口 ====================


@router.post("/extract", summary="从文本中提取医疗实体")
def api_extract_entities(
    text: str = Query(..., min_length=1, description="需要提取实体的文本内容"),
    current_user: User = Depends(get_current_user),
):
    """从给定的文本中提取医疗实体（疾病、药物、症状、治疗、检查）。

    使用配置的大语言模型进行命名实体识别（NER），
    返回提取到的实体列表。
    """
    entities = extract_entities(text)
    return {"entities": entities, "count": len(entities)}


# ==================== 知识库图谱查询 ====================


@router.get(
    "/kb/{kb_id}",
    response_model=GraphSearchResponse,
    summary="获取知识库的完整图谱",
)
def get_kb_graph(
    kb_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定知识库的所有图谱实体和关系。

    返回该知识库中从文档提取的全部实体和关系，
    用于前端图谱可视化和知识浏览。
    """
    # 查询该知识库下的所有实体
    entities = (
        mysql_db.query(GraphEntity)
        .filter(GraphEntity.kb_id == kb_id)
        .all()
    )
    # 获取对应实体的 ID 列表，用于查询关系
    entity_ids = [e.id for e in entities]
    relations = []
    if entity_ids:
        relations = (
            mysql_db.query(GraphRelation)
            .filter(
                (GraphRelation.source_entity_id.in_(entity_ids))
                | (GraphRelation.target_entity_id.in_(entity_ids))
            )
            .all()
        )

    # 构建图上下文文本
    entity_names = [e.name for e in entities]
    context_text = get_graph_context(f"kb_{kb_id}", entity_names)

    return GraphSearchResponse(
        entities=[_entity_to_response(e) for e in entities],
        relations=[_relation_to_response(r) for r in relations],
        graph_context=context_text,
    )


# ==================== 图谱搜索接口 ====================


@router.get(
    "/search",
    response_model=GraphSearchResponse,
    summary="在图谱中搜索相关实体和关系",
)
def api_search_graph(
    query: str = Query(..., min_length=1, description="搜索查询文本"),
    kb_id: int = Query(..., description="知识库 ID"),
    max_depth: int = Query(default=2, ge=1, le=5, description="图搜索深度"),
    top_k: Optional[int] = Query(default=20, description="返回结果数量上限"),
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """在图谱中执行语义搜索，返回与查询相关的实体和关系。

    采用混合策略：
    1. 先用 LLM 从查询中提取实体
    2. 在数据库中搜索匹配的实体
    3. 在内存图谱中执行 BFS 扩展
    """
    # 第一步：用 LLM 从查询中提取实体关键词
    extracted = extract_entities(query)
    query_entity_names = [e["name"].lower() for e in extracted]

    # 第二步：在数据库中查找匹配的实体
    db_entities = []
    if query_entity_names:
        # 构建模糊匹配条件
        from sqlalchemy import or_
        name_conditions = [
            GraphEntity.name.ilike(f"%{name}%")
            for name in query_entity_names
        ]
        db_entities = (
            mysql_db.query(GraphEntity)
            .filter(
                GraphEntity.kb_id == kb_id,
                or_(*name_conditions),
            )
            .limit(top_k)
            .all()
        )

    # 第三步：将数据库实体载入内存图谱并执行 BFS 扩展
    store = get_store()
    loaded_entity_ids: List[str] = []
    for ent in db_entities:
        eid = str(ent.id)
        store.add_entity(eid, ent.entity_type, ent.name)
        loaded_entity_ids.append(eid)

    # 加载与该知识库相关的所有关系
    if db_entities:
        db_entity_ids = [e.id for e in db_entities]
        relations = (
            mysql_db.query(GraphRelation)
            .filter(
                (GraphRelation.source_entity_id.in_(db_entity_ids))
                | (GraphRelation.target_entity_id.in_(db_entity_ids))
            )
            .all()
        )
        for rel in relations:
            store.add_relation(
                str(rel.source_entity_id),
                str(rel.target_entity_id),
                rel.relation_type,
            )
            # 确保关系两端的实体也在图谱中
            if rel.source_entity_id not in [int(e) for e in loaded_entity_ids]:
                src = mysql_db.query(GraphEntity).filter(
                    GraphEntity.id == rel.source_entity_id
                ).first()
                if src:
                    store.add_entity(str(src.id), src.entity_type, src.name)
            if rel.target_entity_id not in [int(e) for e in loaded_entity_ids]:
                tgt = mysql_db.query(GraphEntity).filter(
                    GraphEntity.id == rel.target_entity_id
                ).first()
                if tgt:
                    store.add_entity(str(tgt.id), tgt.entity_type, tgt.name)

    # 第四步：执行图搜索
    subgraph = search_graph(loaded_entity_ids, max_depth=max_depth)
    context_text = get_graph_context(query, loaded_entity_ids)

    # 第五步：去重构建结果
    seen_entity_ids: set = set()
    result_entities: list = []
    result_relations: list = []

    for item in subgraph:
        ent = item["entity"]
        conn = item["connected_entity"]
        # 只返回数据库中有记录的实体
        for e in [ent, conn]:
            if e and e.get("name"):
                # 尝试在数据库中找到对应实体
                db_ent = mysql_db.query(GraphEntity).filter(
                    GraphEntity.kb_id == kb_id,
                    GraphEntity.name == e["name"],
                ).first()
                if db_ent and db_ent.id not in seen_entity_ids:
                    seen_entity_ids.add(db_ent.id)
                    result_entities.append(_entity_to_response(db_ent))

    return GraphSearchResponse(
        entities=result_entities,
        relations=result_relations,
        graph_context=context_text,
    )

