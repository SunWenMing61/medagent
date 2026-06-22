"""在线知识源管理的 API 端点。"""

# 导入 JSON 模块，用于序列化/反序列化
import json
# 导入类型提示：列表和可选类型
from typing import List, Optional

# 从 FastAPI 导入路由、依赖注入、HTTP 异常、查询参数
from fastapi import APIRouter, Depends, HTTPException, Query
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session

# 导入适配器相关函数：列出适配器类型、获取配置模式、获取适配器实例
from app.adapters import list_adapter_types, get_config_schema, get_adapter
# 导入获取当前用户的依赖函数
from app.core.dependencies import get_current_user
# 导入 MySQL 数据库会话获取函数
from app.db.session import get_mysql_db
# 导入用户模型
from app.models.user import User
# 导入知识库模型
from app.models.knowledge_base import KnowledgeBase
# 导入知识源模型
from app.models.knowledge_source import KnowledgeSource
# 导入知识源相关的 Pydantic 请求/响应模型
from app.schemas.knowledge_source import (
    SourceCreateRequest,
    SourceUpdateRequest,
    SourceResponse,
    SourceStatusResponse,
    SourceSyncResponse,
    SourceSchemaResponse,
)
# 导入知识源服务（包含 CRUD 和清理逻辑）
from app.services.source_service import source_service
# 导入同步任务队列函数
from app.tasks.source_tasks import enqueue_sync

# 创建知识源路由实例
router = APIRouter()


def _source_to_response(
    source: KnowledgeSource,
    document_count: int = 0,
) -> SourceResponse:
    """将 KnowledgeSource ORM 模型转换为 SourceResponse 响应模型。"""
    return SourceResponse(
        id=source.id,                       # 知识源 ID
        kb_id=source.kb_id,                 # 关联的知识库 ID
        source_type=source.source_type,     # 知识源类型（如 web_url, confluence 等）
        name=source.name,                   # 知识源名称
        config=source.config,               # 知识源配置（JSON 格式）
        sync_status=source.sync_status,     # 同步状态（idle/syncing/success/failed）
        document_count=document_count,      # 已同步的文档数量
        last_sync_at=source.last_sync_at,   # 上次同步时间
        error_message=source.error_message, # 错误信息（同步失败时记录）
        created_at=source.created_at,       # 创建时间
        updated_at=source.updated_at,       # 更新时间
    )


def _check_kb_permission(kb_id: int, user: User, mysql_db: Session) -> KnowledgeBase:
    """检查当前用户是否有权限操作指定知识库。"""
    # 查询知识库是否存在
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    # 只有知识库拥有者或管理员有权限
    if kb.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限操作此知识库")
    return kb


def _check_source_permission(source_id: int, user: User, mysql_db: Session):
    """检查当前用户是否有权限操作指定知识源。"""
    # 查询知识源是否存在
    source = mysql_db.query(KnowledgeSource).filter(
        KnowledgeSource.id == source_id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="知识源不存在")

    # 查询该知识源关联的知识库
    kb = mysql_db.query(KnowledgeBase).filter(
        KnowledgeBase.id == source.kb_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="关联知识库不存在")

    # 只有知识库拥有者或管理员有权限
    if kb.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限操作此知识源")
    return source


# 清理失效知识源接口：POST /api/sources/cleanup
@router.post("/cleanup")
def cleanup_sources(
    current_user: User = Depends(get_current_user),
):
    """删除所有关联知识库已不存在的孤立知识源。"""
    # 只有管理员可以执行清理操作
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    # 调用服务层清理孤立知识源
    deleted = source_service.cleanup_orphaned_sources()
    return {"message": f"已清理 {deleted} 个失效知识源", "deleted_count": deleted}


# 获取知识源配置模式接口：GET /api/sources/schemas
@router.get("/schemas", response_model=dict)
def list_source_schemas():
    """获取所有可用知识源类型的配置模式（schema）。"""
    result = {}
    for info in list_adapter_types():
        st = info["source_type"]             # 知识源类型名称
        adapter = get_adapter(st)            # 获取对应适配器实例
        # 构建配置模式响应
        result[st] = SourceSchemaResponse(
            source_type=st,
            display_name=info["display_name"],           # 显示名称
            config_schema=adapter.get_config_schema(),   # 配置字段模式定义
            defaults=adapter.get_default_config(),       # 默认配置值
        )
    return result


# 创建知识源接口：POST /api/sources
@router.post("", response_model=SourceResponse, status_code=201)
def create_source(
    req: SourceCreateRequest,                     # 创建请求体
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    """创建新的在线知识源。"""
    # 验证知识库存在且用户有操作权限
    _check_kb_permission(req.kb_id, current_user, mysql_db)

    # 验证适配器配置是否合法
    try:
        # 根据知识源类型获取对应的适配器
        adapter = get_adapter(req.source_type)
    except ValueError as e:
        # 如果适配器类型不存在，返回 400 错误
        raise HTTPException(status_code=400, detail=str(e))

    if req.config:
        # 使用适配器验证配置的合法性
        is_valid, error = adapter.validate_config(req.config)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"配置验证失败: {error}")

    # 创建知识源记录
    source = KnowledgeSource(
        kb_id=req.kb_id,                    # 所属知识库 ID
        source_type=req.source_type,        # 知识源类型
        name=req.name,                      # 知识源名称
        config=json.dumps(req.config, ensure_ascii=False),  # 配置（JSON 字符串）
        sync_status="idle",                 # 初始同步状态：空闲
    )
    mysql_db.add(source)
    mysql_db.commit()
    mysql_db.refresh(source)

    return _source_to_response(source)


# 获取知识源列表接口：GET /api/sources
@router.get("", response_model=List[SourceResponse])
def list_sources(
    kb_id: Optional[int] = Query(None),         # 可选的知识库 ID 筛选
    mysql_db: Session = Depends(get_mysql_db),  # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    """获取知识源列表，可选的按知识库 ID 过滤。

    会自动清理关联知识库已不存在的孤立知识源。
    """
    # 自动清理孤立知识源（其关联的 KB 已被删除）
    source_service.cleanup_orphaned_sources()

    # 构建查询
    query = mysql_db.query(KnowledgeSource)

    if kb_id:
        # 如果指定了知识库 ID，按知识库过滤
        query = query.filter(KnowledgeSource.kb_id == kb_id)

    # 非管理员用户只能看到自己知识库下的知识源
    if current_user.role != "admin":
        admin_kb_ids = mysql_db.query(KnowledgeBase.id).filter(
            KnowledgeBase.owner_id == current_user.id
        ).subquery()
        query = query.filter(KnowledgeSource.kb_id.in_(admin_kb_ids))

    # 按创建时间降序排列
    sources = query.order_by(KnowledgeSource.created_at.desc()).all()

    # 构建响应列表（包含每个知识源的文档数量）
    result = []
    for s in sources:
        count = source_service.get_source_document_count(s.id)
        result.append(_source_to_response(s, count))
    return result


# 获取单个知识源接口：GET /api/sources/{source_id}
@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: int,                                   # 知识源 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),        # MySQL 数据库会话
    current_user: User = Depends(get_current_user),   # 当前已认证用户
):
    """根据 ID 获取单个知识源详情。"""
    # 检查权限并获取知识源
    source = _check_source_permission(source_id, current_user, mysql_db)
    # 获取该知识源的文档数量
    count = source_service.get_source_document_count(source.id)
    return _source_to_response(source, count)


# 更新知识源接口：PUT /api/sources/{source_id}
@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int,                                   # 知识源 ID（路径参数）
    req: SourceUpdateRequest,                         # 更新请求体
    mysql_db: Session = Depends(get_mysql_db),        # MySQL 数据库会话
    current_user: User = Depends(get_current_user),   # 当前已认证用户
):
    """更新知识源的配置信息。"""
    # 检查权限并获取知识源
    source = _check_source_permission(source_id, current_user, mysql_db)

    if req.name is not None:
        # 更新知识源名称
        source.name = req.name
    if req.config is not None:
        # 更新知识源配置（JSON 序列化存储）并重置同步状态
        source.config = json.dumps(req.config, ensure_ascii=False)
        source.sync_status = "idle"  # 配置变化后重置同步状态
    if req.kb_id is not None and req.kb_id != source.kb_id:
        # 如果迁移到其他知识库，验证新知识库存在且有权限
        _check_kb_permission(req.kb_id, current_user, mysql_db)
        source.kb_id = req.kb_id
        source.sync_status = "idle"  # 知识库变更后也重置同步状态

    # 提交更改
    mysql_db.commit()
    mysql_db.refresh(source)
    count = source_service.get_source_document_count(source.id)
    return _source_to_response(source, count)


# 删除知识源接口：DELETE /api/sources/{source_id}
@router.delete("/{source_id}")
def delete_source(
    source_id: int,                                   # 知识源 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),        # MySQL 数据库会话
    current_user: User = Depends(get_current_user),   # 当前已认证用户
):
    """删除知识源及其所有同步的文档。"""
    # 检查权限并获取知识源
    source = _check_source_permission(source_id, current_user, mysql_db)
    # 调用服务层删除知识源及关联文档
    deleted_docs = source_service.delete_source(source.id)
    return {
        "message": "知识源已删除",
        "deleted_documents": deleted_docs,  # 返回被删除的文档数量
    }


# 触发知识源同步接口：POST /api/sources/{source_id}/sync
@router.post("/{source_id}/sync", response_model=SourceSyncResponse)
def trigger_sync(
    source_id: int,                                   # 知识源 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),        # MySQL 数据库会话
    current_user: User = Depends(get_current_user),   # 当前已认证用户
):
    """触发知识源的异步同步操作。"""
    # 检查权限并获取知识源
    source = _check_source_permission(source_id, current_user, mysql_db)

    if source.sync_status == "syncing":
        # 如果知识源正在同步中，拒绝重复触发
        raise HTTPException(status_code=409, detail="该知识源正在同步中，请等待完成")

    # 立即更新同步状态为"同步中"
    source.sync_status = "syncing"
    source.error_message = None   # 清除之前的错误信息
    mysql_db.commit()

    # 将同步任务加入 RQ 任务队列异步执行
    enqueue_sync(source_id)

    return SourceSyncResponse(source_id=source.id)


# 获取知识源同步状态接口：GET /api/sources/{source_id}/status
@router.get("/{source_id}/status", response_model=SourceStatusResponse)
def get_source_status(
    source_id: int,                                   # 知识源 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),        # MySQL 数据库会话
    current_user: User = Depends(get_current_user),   # 当前已认证用户
):
    """获取知识源的当前同步状态。"""
    # 检查权限并获取知识源
    source = _check_source_permission(source_id, current_user, mysql_db)
    # 返回同步状态信息
    return SourceStatusResponse(
        id=source.id,
        sync_status=source.sync_status,      # 同步状态
        last_sync_at=source.last_sync_at,    # 上次同步时间
        error_message=source.error_message,  # 错误信息
    )
