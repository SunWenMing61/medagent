# 导入 JSON 模块，用于序列化和反序列化 JSON 数据
import json
# 导入日志模块，用于记录程序运行日志
import logging

# 从 FastAPI 导入路由、后台任务、依赖注入、HTTP 异常、文件上传等工具
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
# 导入流式响应类，用于 SSE（Server-Sent Events）流式输出
from fastapi.responses import StreamingResponse
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session
# 导入类型提示相关的工具
from typing import Dict, List, Optional

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 导入获取当前用户的依赖函数
from app.core.dependencies import get_current_user
# 导入数据库会话工厂：MySQL 和 PostgreSQL
from app.db.session import get_mysql_db, PgSessionLocal
# 导入用户模型
from app.models.user import User
# 导入聊天会话和消息模型
from app.models.chat import ChatSession, ChatMessage
# 导入知识库模型
from app.models.knowledge_base import KnowledgeBase
# 导入文档模型
from app.models.document import Document
# 导入文档块（切片）模型
from app.models.document_chunk import DocumentChunk
# 导入聊天相关的 Pydantic 请求/响应模型
from app.schemas.chat import (
    AskRequest, AskResponse, SessionResponse,
    MessageResponse, SessionDetailResponse,
)
# 导入多智能体工作流引擎
from app.graphs.medagent_graph import MedAgentWorkflow
# 导入构建历史文本的工具函数
from app.graphs.nodes import _build_history_text
# 导入聊天历史服务函数：获取/创建聊天历史知识库、存储对话、清理旧切片
from app.services.chat_history_service import (
    get_or_create_chat_history_kb,
    store_conversation,
    cleanup_old_chunks,
)

# 创建聊天路由实例
router = APIRouter()
# 初始化多智能体工作流实例（全局单例，避免重复加载）
workflow = MedAgentWorkflow()


def _merge_chat_history_kb(kb_ids: Optional[List[int]]) -> List[int]:
    """自动将全局聊天历史知识库包含到搜索范围中。"""
    # 获取或创建全局聊天历史知识库的 ID
    history_kb_id = get_or_create_chat_history_kb()
    if kb_ids:
        # 如果传入了知识库 ID 列表，将聊天历史知识库 ID 合并进去（去重）
        merged = list(set(kb_ids) | {history_kb_id})
    else:
        # 如果没有传入知识库 ID，则只使用聊天历史知识库
        merged = [history_kb_id]
    return merged


def _get_all_user_kbs(current_user: User, db: Session) -> List[int]:
    """返回当前用户可以访问的所有知识库 ID 列表（自己拥有的 + 公开的 + 聊天历史）。"""
    # 获取聊天历史知识库 ID
    history_kb_id = get_or_create_chat_history_kb()
    if current_user.role == "admin":
        # 管理员可以看到：自己拥有的 + 所有公开的知识库
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | (KnowledgeBase.visibility == "public")
        ).all()
    else:
        # 普通用户只能看到：自己拥有的 + 公开且状态为启用的知识库
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1))
        ).all()
    # 提取知识库 ID
    kb_ids = [kb.id for kb in kbs]
    # 合并聊天历史知识库 ID 并去重返回
    return list(set(kb_ids) | {history_kb_id})


def _resolve_kb_names(kb_ids: List[int], db: Session) -> Dict[int, str]:
    """将知识库 ID 列表解析为 {ID: 名称} 的映射字典。"""
    if not kb_ids:
        # 如果列表为空，返回空字典
        return {}
    # 批量查询知识库名称
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all()
    # 构建 ID 到名称的映射
    return {kb.id: kb.name for kb in kbs}


def _load_history(session_id: int, db: Session) -> List[dict]:
    """从数据库中加载指定会话的历史消息列表。"""
    # 按创建时间升序查询该会话的所有消息
    msgs = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    history = []
    for m in msgs:
        # 将每条消息转换为 {role, content} 格式
        history.append({"role": m.role, "content": m.content})
    return history


def _save_kb_ids(session: ChatSession, kb_ids: list[int] | None, db: Session):
    """如果传入了知识库 ID，将其保存到会话记录中。"""
    if kb_ids:
        # 将知识库 ID 列表序列化为 JSON 字符串并保存
        session.kb_ids_json = json.dumps(kb_ids)
        # 提交数据库更改
        db.commit()


def _parse_kb_ids(session: ChatSession) -> list[int] | None:
    """从 ChatSession 对象中解析 kb_ids_json 字段为列表，失败则返回 None。"""
    if session.kb_ids_json:
        try:
            # 尝试将 JSON 字符串解析为 Python 列表
            return json.loads(session.kb_ids_json)
        except (json.JSONDecodeError, TypeError):
            # 如果 JSON 格式无效或类型错误，返回 None
            return None
    return None


def _post_process_chat(user_id: int, kb_id: int, question: str, answer: str, session_id: int | None = None):
    """后台任务：存储对话记录到聊天历史知识库，并清理旧切片。"""
    try:
        # 将当前问答对存储到聊天历史知识库
        store_conversation(user_id, kb_id, question, answer, session_id=session_id)
    except Exception as e:
        # 记录存储失败的日志，不中断主流程
        logger.error("Failed to store conversation: %s", e)
    try:
        # 清理指定知识库中过期的旧切片数据
        cleanup_old_chunks(kb_id)
    except Exception as e:
        # 记录清理失败的日志，不中断主流程
        logger.error("Failed to cleanup old chunks: %s", e)


# 问答接口（非流式）：POST /api/chat/ask，返回 AskResponse 类型
@router.post("/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,                                          # 请求体，包含问题、会话 ID 等
    background_tasks: BackgroundTasks,                        # FastAPI 后台任务，用于异步处理
    db: Session = Depends(get_mysql_db),                      # 数据库会话（MySQL）
    current_user: User = Depends(get_current_user),            # 当前已认证用户
):
    # 记录传入的会话 ID
    session_id = req.session_id
    if not session_id:
        # 如果没有传入会话 ID，则创建新的聊天会话
        session = ChatSession(
            user_id=current_user.id,         # 当前用户 ID
            title=req.question[:100],         # 会话标题取问题前 100 个字符
            session_type="qa",                # 会话类型为问答
        )
        # 将会话添加到数据库
        db.add(session)
        # 提交事务
        db.commit()
        # 刷新会话对象以获取数据库生成的 ID
        db.refresh(session)
        # 获取新生成的会话 ID
        session_id = session.id
        # 如果传入了知识库 ID，保存到会话
        _save_kb_ids(session, req.kb_ids, db)
    else:
        # 如果传入了会话 ID，查询该会话是否存在且属于当前用户
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            # 如果会话不存在或不属于当前用户，返回 404 错误
            raise HTTPException(status_code=404, detail="Session not found")

    # 保存用户问题到聊天消息表
    msg = ChatMessage(session_id=session_id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    # 加载当前会话的历史消息
    history_msgs = _load_history(session_id, db)
    # 获取当前用户可访问的所有知识库 ID
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    # 将知识库 ID 解析为名称映射
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # 执行多智能体工作流，获取回答结果
    result = workflow.run(
        question=req.question,                        # 用户提问
        user_id=current_user.id,                      # 当前用户 ID
        session_id=session_id,                        # 会话 ID
        kb_ids=merged_kb_ids,                         # 搜索的知识库 ID 列表
        kb_name_map=kb_name_map,                      # 知识库名称映射
        history_messages=history_msgs,                # 历史消息列表
        web_search_enabled=req.web_search_enabled,    # 是否启用网络搜索
        deep_thinking_enabled=req.deep_thinking_enabled,  # 是否启用深度思考
    )

    # 保存 AI 助手的回答到聊天消息表
    assistant_msg = ChatMessage(
        session_id=session_id,                # 会话 ID
        role="assistant",                     # 角色为助手
        content=result["final_response"],      # 最终回答内容
        references_json=result.get("references"),  # 参考来源（JSON 格式）
        safety_flag=result.get("safety_flag"),     # 安全标记
    )
    db.add(assistant_msg)
    db.commit()

    # 获取聊天历史知识库 ID，用于后台保存对话历史
    history_kb_id = get_or_create_chat_history_kb()
    # 将后处理任务（存储对话 + 清理旧切片）添加到后台执行
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        req.question, result["final_response"], session_id,
    )

    # 返回问答响应结果
    return AskResponse(
        session_id=session_id,                  # 会话 ID
        question=req.question,                  # 原始问题
        answer=result["final_response"],         # 回答内容
        references=result.get("references"),     # 参考来源
        safety_flag=result.get("safety_flag"),   # 安全标记
        # 医疗免责声明：仅作参考，非医疗建议
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "Please consult a qualified healthcare professional for medical decisions.",
    )


# 问答接口（流式）：POST /api/chat/ask/stream，通过 SSE 流式返回
@router.post("/ask/stream")
def ask_question_stream(
    req: AskRequest,                                          # 请求体
    background_tasks: BackgroundTasks,                        # 后台任务
    db: Session = Depends(get_mysql_db),                      # MySQL 数据库会话
    current_user: User = Depends(get_current_user),            # 当前已认证用户
):
    """通过 SSE（Server-Sent Events）流式返回多智能体的回答。

    子智能体同步执行，最终聚合器的响应逐 token 流式输出。
    流式输出完成后，完整回答被保存到数据库中。
    """
    # 记录传入的会话 ID
    session_id = req.session_id
    if not session_id:
        # 没有传入会话 ID，创建新会话
        session = ChatSession(
            user_id=current_user.id,         # 当前用户 ID
            title=req.question[:100],         # 标题取自问题
            session_type="qa",                # 会话类型
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id
        # 保存知识库 ID 到会话
        _save_kb_ids(session, req.kb_ids, db)
    else:
        # 查询已有会话
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # 保存用户消息
    msg = ChatMessage(session_id=session_id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    # 加载历史消息和知识库信息
    history_msgs = _load_history(session_id, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # 导入工作流和节点模块（延迟导入，避免循环依赖）
    from app.graphs.medagent_graph import MedAgentWorkflow as Mw
    from app.graphs.nodes import (
        classify_question_node, sub_agent_retrieve_node,
        sub_agent_generate_and_aggregate, safety_check_node, format_response_node,
    )
    from app.graphs.graph_state import MedAgentState

    # 初始化多智能体状态对象
    state = MedAgentState(
        question=req.question,                        # 用户问题
        user_id=current_user.id,                      # 用户 ID
        session_id=session_id,                        # 会话 ID
        kb_ids=merged_kb_ids,                         # 知识库 ID 列表
        kb_name_map=kb_name_map,                      # 知识库名称映射
        history_messages=history_msgs,                # 历史消息
        web_search_enabled=req.web_search_enabled,    # 是否启用网络搜索
        deep_thinking_enabled=req.deep_thinking_enabled,  # 是否启用深度思考
    )

    # 同步执行：问题分类、知识检索
    state.question_type = "medical_qa"
    state = sub_agent_retrieve_node(state)

    # 同步执行：子智能体生成 + 聚合器
    from app.graphs.nodes import (
        _build_history_text, _load_prompt, _get_prompt_file, _llm_call_stream,
        generate_thinking_stream,
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 获取对应问题类型的提示词文件路径
    prompt_file = _get_prompt_file(state.question_type)
    # 将历史消息格式化为文本
    history_text = _build_history_text(state.history_messages)

    # 准备每个知识库的子智能体任务
    sub_answers = []
    kb_tasks = []
    for kb_id in state.kb_ids:
        # 获取该知识库的检索结果切片
        chunks = state.per_kb_chunks.get(kb_id, [])
        # 获取知识库名称
        kb_name = state.get_kb_name(kb_id)
        if chunks:
            # 如果有检索到的切片，添加为子任务
            kb_tasks.append((kb_id, kb_name, chunks))

    if kb_tasks:
        # 使用线程池并行执行多个知识库的子智能体处理
        with ThreadPoolExecutor(max_workers=min(len(kb_tasks), 8)) as executor:
            futures = []
            for kb_id, kb_name, chunks in kb_tasks:
                # 导入子智能体运行函数
                from app.graphs.nodes import _run_sub_agent
                # 提交子任务到线程池
                f = executor.submit(_run_sub_agent, kb_id, kb_name, state.question, chunks, prompt_file, history_text)
                futures.append(f)
            # 收集所有子任务的结果
            for f in as_completed(futures):
                try:
                    sub_answers.append(f.result())
                except Exception as e:
                    # 如果子智能体失败，返回错误占位信息
                    sub_answers.append({"kb_id": 0, "kb_name": "unknown", "answer": f"（子Agent失败: {e}）", "chunk_count": 0})

    # 在 event_generator 之前设置 sub_answers，确保深度思考可以使用
    state.sub_answers = sub_answers

    # 格式化每个知识库的子回答
    sub_answer_texts = []
    for sa in sub_answers:
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # 如果有网络搜索结果，也加入聚合
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    # 如果没有任何子回答，使用占位信息
    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（所有知识库均未返回相关信息）"

    # 加载聚合器提示词模板，并填充问题和子回答
    aggregator_template = _load_prompt("aggregator_prompt.txt")
    aggregator_prompt = (
        aggregator_template
        .replace("{question}", state.question)
        .replace("{sub_answers}", sub_answers_formatted)
    )
    # 如果有历史消息，添加到聚合提示词中
    if history_text:
        if "{history}" in aggregator_template:
            # 模板中已有 {history} 占位符，直接替换
            aggregator_prompt = aggregator_prompt.replace("{history}", history_text)
        else:
            # 模板中没有占位符，在开头追加历史记录
            aggregator_prompt = f"**对话历史:**\n{history_text}\n\n---\n\n" + aggregator_prompt

    # 定义 SSE 事件生成器（异步生成器函数）
    async def event_generator():
        full_text = ""          # 累积的完整回答文本
        thinking_text = ""      # 累积的深度思考文本

        # 阶段 1：如果启用了深度思考，先流式输出思考过程
        if req.deep_thinking_enabled:
            try:
                for token in generate_thinking_stream(state):
                    thinking_text += token
                    # 发送思考 token 的 SSE 事件
                    yield f"data: {json.dumps({'type': 'think', 'token': token})}\n\n"
            except Exception as e:
                # 深度思考流式输出出错时记录警告
                logger.warning("Deep thinking stream error: %s", e)

        # 阶段 2：逐 token 流式输出最终回答
        try:
            for token in _llm_call_stream(aggregator_prompt, temperature=0.5, max_tokens=2048):
                full_text += token
                # 发送回答 token 的 SSE 事件
                yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
        except Exception as e:
            # 回答流式输出出错时发送错误事件并终止
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # 流式输出完成后，执行安全检查和格式化
        state.raw_answer = full_text
        state.thinking_content = thinking_text
        state.sub_answers = sub_answers
        safety_check_node(state)      # 安全检测
        format_response_node(state)   # 响应格式化

        # 将最终回答保存到数据库
        db2 = next(get_mysql_db())
        try:
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=state.final_response,        # 最终回答
                references_json=state.references,    # 参考来源
                safety_flag=state.safety_flag,       # 安全标记
            )
            db2.add(assistant_msg)
            db2.commit()

            # 将问答对存储到聊天历史知识库
            history_kb_id = get_or_create_chat_history_kb()
            store_conversation(current_user.id, history_kb_id, req.question, state.final_response, session_id=session_id)
            cleanup_old_chunks(history_kb_id)

            # 保存消息 ID 以便后续引用
            saved_message_id = assistant_msg.id
        except Exception as e:
            # 保存失败时记录错误日志
            logger.error("Failed to save streamed answer: %s", e)
            saved_message_id = None
        finally:
            # 关闭第二个数据库会话
            db2.close()

        # 发送完成事件，包含会话 ID、消息 ID、安全标记和思考内容
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'message_id': saved_message_id, 'safety_flag': state.safety_flag, 'thinking': thinking_text})}\n\n"

    # 返回 SSE 流式响应
    return StreamingResponse(
        event_generator(),                                          # 事件生成器
        media_type="text/event-stream",                              # SSE 媒体类型
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},  # 禁止缓存，保持连接
    )


# ==============================================================================
# 多部分表单聊天接口 —— 支持在问题中附带文件/图片上传
# ==============================================================================

def _process_chat_files(files: List[UploadFile]) -> tuple:
    """处理聊天中上传的文件。

    返回 (附件列表, 临时文件路径列表)，用于清理。
    """
    # 导入附件处理工具函数
    from app.utils.chat_attachments import process_attachment, save_uploaded_file, cleanup_file

    attachments = []    # 附件列表
    temp_files = []     # 临时文件路径列表

    for file in files:
        # 跳过没有文件名的空文件
        if not file.filename:
            continue
        try:
            # 读取文件内容
            content = file.file.read()
            # 将文件保存到临时目录
            file_path = save_uploaded_file(content, file.filename)
            temp_files.append(file_path)

            # 处理附件，生成对应的描述信息
            att = process_attachment(file_path, file.filename, file.content_type or "")
            if att:
                attachments.append(att)
        except Exception as e:
            # 处理失败时记录日志，不中断其他文件处理
            logger.error("Failed to process chat file %s: %s", file.filename, e)

    return attachments, temp_files


# 多部分表单问答接口：POST /api/chat/ask-multipart，支持文件上传
@router.post("/ask-multipart")
async def ask_question_multipart(
    question: str = Form(...),                          # 问题文本（必填表单字段）
    web_search_enabled: bool = Form(False),             # 是否启用网络搜索（可选，默认关闭）
    deep_thinking_enabled: bool = Form(False),          # 是否启用深度思考（可选，默认关闭）
    kb_ids: Optional[str] = Form(None),                 # 知识库 ID 列表（JSON 字符串，可选）
    session_id: Optional[int] = Form(None),             # 会话 ID（可选，不传则新建）
    files: List[UploadFile] = File(default=[]),         # 上传的文件列表（可选）
    background_tasks: BackgroundTasks = BackgroundTasks(),  # 后台任务
    db: Session = Depends(get_mysql_db),                # MySQL 数据库会话
    current_user: User = Depends(get_current_user),      # 当前已认证用户
):
    """通过多部分表单提交问题，可附带文件/图片附件。

    接受 multipart/form-data 格式，包含：
      - question（必填）
      - web_search_enabled（可选）
      - deep_thinking_enabled（可选）
      - kb_ids（可选 JSON 数组字符串）
      - session_id（可选）
      - files（可选，可多个）
    """
    # 解析知识库 ID 的 JSON 字符串
    parsed_kb_ids = None
    if kb_ids:
        try:
            parsed_kb_ids = json.loads(kb_ids)
        except (json.JSONDecodeError, TypeError):
            # 如果 JSON 解析失败，忽略该字段
            pass

    # 处理上传的文件附件
    attachments, temp_files = _process_chat_files(files)

    # 创建或获取已存在的会话
    sid = session_id
    if not sid:
        # 创建新会话
        session = ChatSession(
            user_id=current_user.id,
            title=question[:100],
            session_type="qa",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        sid = session.id
        # 保存知识库 ID 到会话
        _save_kb_ids(session, parsed_kb_ids, db)
    else:
        # 查询已有会话
        session = db.query(ChatSession).filter(
            ChatSession.id == sid,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # 保存用户消息
    msg = ChatMessage(session_id=sid, role="user", content=question)
    db.add(msg)
    db.commit()

    # 加载历史消息和知识库信息
    history_msgs = _load_history(sid, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # 构建附件描述文本，用于后续历史存储
    att_desc = ""
    if attachments:
        from app.utils.chat_attachments import describe_attachments_for_prompt
        att_desc = "\n\n" + describe_attachments_for_prompt(attachments)

    # 执行多智能体工作流，传入附件信息
    result = workflow.run(
        question=question,                        # 用户问题
        user_id=current_user.id,                  # 用户 ID
        session_id=sid,                           # 会话 ID
        kb_ids=merged_kb_ids,                     # 搜索的知识库 ID
        kb_name_map=kb_name_map,                  # 知识库名称映射
        history_messages=history_msgs,            # 历史消息
        attachments=attachments,                  # 附件列表
        web_search_enabled=web_search_enabled,    # 网络搜索开关
        deep_thinking_enabled=deep_thinking_enabled,  # 深度思考开关
    )

    # 保存 AI 助手的回答
    assistant_msg = ChatMessage(
        session_id=sid,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    # 后台存储对话到聊天历史知识库
    history_kb_id = get_or_create_chat_history_kb()
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        question, result["final_response"], sid,
    )

    # 后台清理临时文件
    for fp in temp_files:
        from app.utils.chat_attachments import cleanup_file
        background_tasks.add_task(cleanup_file, fp)

    # 返回问答响应
    return AskResponse(
        session_id=sid,
        question=question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "Please consult a qualified healthcare professional for medical decisions.",
    )


# 流式多部分表单问答接口：POST /api/chat/ask-multipart/stream
@router.post("/ask-multipart/stream")
async def ask_question_multipart_stream(
    question: str = Form(...),                          # 问题文本（必填）
    web_search_enabled: bool = Form(False),             # 网络搜索开关
    deep_thinking_enabled: bool = Form(False),          # 深度思考开关
    kb_ids: Optional[str] = Form(None),                 # 知识库 ID（JSON 字符串）
    session_id: Optional[int] = Form(None),             # 会话 ID
    files: List[UploadFile] = File(default=[]),         # 上传的文件列表
    db: Session = Depends(get_mysql_db),                # MySQL 数据库会话
    current_user: User = Depends(get_current_user),      # 当前已认证用户
):
    """通过 SSE 流式返回回答，支持附带文件/图片附件。

    接受 multipart/form-data 格式，包含：
      - question（必填）
      - web_search_enabled（可选）
      - deep_thinking_enabled（可选）
      - kb_ids（可选 JSON 数组字符串）
      - session_id（可选）
      - files（可选，可多个）
    """
    # 解析知识库 ID 的 JSON 字符串
    parsed_kb_ids = None
    if kb_ids:
        try:
            parsed_kb_ids = json.loads(kb_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    # 处理上传的文件附件
    attachments, temp_files = _process_chat_files(files)

    # 创建或获取已有会话
    sid = session_id
    if not sid:
        session = ChatSession(
            user_id=current_user.id,
            title=question[:100],
            session_type="qa",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        sid = session.id
        _save_kb_ids(session, parsed_kb_ids, db)
    else:
        session = db.query(ChatSession).filter(
            ChatSession.id == sid,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # 保存用户消息
    msg = ChatMessage(session_id=sid, role="user", content=question)
    db.add(msg)
    db.commit()

    # 加载历史消息和知识库信息
    history_msgs = _load_history(sid, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # 延迟导入工作流和节点模块
    from app.graphs.medagent_graph import MedAgentWorkflow as Mw
    from app.graphs.nodes import (
        classify_question_node, sub_agent_retrieve_node,
        sub_agent_generate_and_aggregate, safety_check_node, format_response_node,
    )
    from app.graphs.graph_state import MedAgentState

    # 初始化多智能体状态（含附件信息）
    state = MedAgentState(
        question=question,
        user_id=current_user.id,
        session_id=sid,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        attachments=attachments,              # 附件信息
        web_search_enabled=web_search_enabled,
        deep_thinking_enabled=deep_thinking_enabled,
    )

    # 同步执行：问题分类 + 知识检索
    state.question_type = "medical_qa"
    state = sub_agent_retrieve_node(state)

    # 同步执行：子智能体 + 聚合器
    from app.graphs.nodes import _build_history_text, _load_prompt, _get_prompt_file, _llm_call_stream, _llm_call_stream_multimodal
    from app.graphs.nodes import _run_sub_agent, generate_thinking_stream
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 获取提示词文件并构建历史文本
    prompt_file = _get_prompt_file(state.question_type)
    history_text = _build_history_text(state.history_messages)

    # 准备每个知识库的子智能体任务
    sub_answers = []
    kb_tasks = []
    for kb_id in state.kb_ids:
        chunks = state.per_kb_chunks.get(kb_id, [])
        kb_name = state.get_kb_name(kb_id)
        if chunks:
            kb_tasks.append((kb_id, kb_name, chunks))

    if kb_tasks:
        # 使用线程池并行执行子智能体
        with ThreadPoolExecutor(max_workers=min(len(kb_tasks), 8)) as executor:
            futures = []
            for kb_id, kb_name, chunks in kb_tasks:
                f = executor.submit(_run_sub_agent, kb_id, kb_name, state.question, chunks, prompt_file, history_text)
                futures.append(f)
            for f in as_completed(futures):
                try:
                    sub_answers.append(f.result())
                except Exception as e:
                    sub_answers.append({"kb_id": 0, "kb_name": "unknown", "answer": f"（子Agent失败: {e}）", "chunk_count": 0})

    # 设置子回答到状态，供深度思考使用
    state.sub_answers = sub_answers

    # 格式化子回答文本
    sub_answer_texts = []
    for sa in sub_answers:
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # 如果有网络搜索结果，加入聚合
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（所有知识库均未返回相关信息）"

    # 加载聚合器提示词模板
    aggregator_template = _load_prompt("aggregator_prompt.txt")
    aggregator_prompt = (
        aggregator_template
        .replace("{question}", state.question)
        .replace("{sub_answers}", sub_answers_formatted)
    )
    if history_text:
        if "{history}" in aggregator_template:
            aggregator_prompt = aggregator_prompt.replace("{history}", history_text)
        else:
            aggregator_prompt = f"**对话历史:**\n{history_text}\n\n---\n\n" + aggregator_prompt

    # 将文档附件描述添加到聚合提示词末尾
    doc_attachments = [a for a in attachments if a.get("type") == "document"]
    image_attachments = [a for a in attachments if a.get("type") == "image"]
    if doc_attachments:
        from app.utils.chat_attachments import describe_attachments_for_prompt
        aggregator_prompt += "\n\n" + describe_attachments_for_prompt(doc_attachments)

    # SSE 事件生成器
    async def event_generator():
        full_text = ""
        thinking_text = ""

        # 阶段 1：深度思考流式输出
        if state.deep_thinking_enabled:
            try:
                for token in generate_thinking_stream(state):
                    thinking_text += token
                    yield f"data: {json.dumps({'type': 'think', 'token': token})}\n\n"
            except Exception as e:
                logger.warning("Deep thinking stream error: %s", e)

        # 阶段 2：回答流式输出（根据是否有图片选择不同的流式方法）
        try:
            if image_attachments:
                # 有图片附件时，使用多模态流式调用
                from app.utils.chat_attachments import build_multimodal_content
                content = build_multimodal_content(aggregator_prompt, image_attachments)
                for token in _llm_call_stream_multimodal(content, temperature=0.5, max_tokens=2048):
                    full_text += token
                    yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
            else:
                # 没有图片时，使用纯文本流式调用
                for token in _llm_call_stream(aggregator_prompt, temperature=0.5, max_tokens=2048):
                    full_text += token
                    yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # 流式完成后执行安全检查和格式化
        state.raw_answer = full_text
        state.thinking_content = thinking_text
        state.sub_answers = sub_answers
        safety_check_node(state)
        format_response_node(state)

        # 保存到数据库
        db2 = next(get_mysql_db())
        try:
            assistant_msg = ChatMessage(
                session_id=sid,
                role="assistant",
                content=state.final_response,
                references_json=state.references,
                safety_flag=state.safety_flag,
            )
            db2.add(assistant_msg)
            db2.commit()

            history_kb_id = get_or_create_chat_history_kb()
            store_conversation(current_user.id, history_kb_id, question, state.final_response, session_id=sid)
            cleanup_old_chunks(history_kb_id)

            saved_message_id = assistant_msg.id
        except Exception as e:
            logger.error("Failed to save streamed answer: %s", e)
            saved_message_id = None
        finally:
            db2.close()

        # 清理临时文件
        for fp in temp_files:
            from app.utils.chat_attachments import cleanup_file
            try:
                cleanup_file(fp)
            except Exception:
                pass

        # 发送完成事件
        yield f"data: {json.dumps({'done': True, 'session_id': sid, 'message_id': saved_message_id, 'safety_flag': state.safety_flag, 'thinking': thinking_text})}\n\n"

    # 返回 SSE 流式响应
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# 健康咨询接口：POST /api/chat/health，返回 AskResponse 类型
@router.post("/health", response_model=AskResponse)
def health_consult(
    req: AskRequest,                                          # 请求体
    background_tasks: BackgroundTasks,                        # 后台任务
    db: Session = Depends(get_mysql_db),                      # MySQL 数据库会话
    current_user: User = Depends(get_current_user),            # 当前已认证用户
):
    # 创建新的健康咨询会话
    session = ChatSession(
        user_id=current_user.id,                                      # 用户 ID
        title=req.question[:100],                                      # 标题
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,    # 知识库 ID（JSON 字符串）
        session_type="health",                                         # 会话类型：健康咨询
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 保存用户消息
    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    # 加载历史消息和知识库信息
    history_msgs = _load_history(session.id, db)
    merged_kb_ids = _merge_chat_history_kb(current_user, req.kb_ids)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # 执行工作流，强制类型为健康咨询
    workflow = MedAgentWorkflow()
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        force_type="health_consult",    # 强制工作流以健康咨询模式运行
    )

    # 保存助手回答
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    # 后台存储对话历史
    history_kb_id = get_or_create_chat_history_kb()
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        req.question, result["final_response"], session.id,
    )

    # 返回问答响应（含紧急免责声明）
    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "If you are experiencing a medical emergency, please call emergency services immediately.",
    )


# 药品问答接口：POST /api/chat/drug，返回 AskResponse 类型
@router.post("/drug", response_model=AskResponse)
def drug_qa(
    req: AskRequest,                                    # 请求体
    db: Session = Depends(get_mysql_db),                # MySQL 数据库会话
    current_user: User = Depends(get_current_user),      # 当前已认证用户
):
    # 创建新的药品问答会话
    session = ChatSession(
        user_id=current_user.id,
        title=req.question[:100],
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,
        session_type="drug",         # 会话类型：药品问答
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 保存用户消息
    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    # 如果未指定知识库，自动查找所有药品类型的知识库
    if not req.kb_ids:
        drug_kbs = db.query(KnowledgeBase).filter(
            KnowledgeBase.type == "drug",            # 类型为药品
            (KnowledgeBase.owner_id == current_user.id) |
            ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1)),
        ).all()
        req.kb_ids = [kb.id for kb in drug_kbs]

    # 加载历史消息
    history_msgs = _load_history(session.id, db)
    workflow = MedAgentWorkflow()
    # 执行工作流，强制类型为药品问答
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=req.kb_ids,
        kb_name_map=_resolve_kb_names(req.kb_ids or [], db),
        history_messages=history_msgs,
        force_type="drug_qa",         # 强制药品问答模式
    )

    # 保存回答
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    # 返回问答响应（含药品免责声明）
    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is based on the drug instructions provided. "
                   "Do not adjust or stop medication without consulting a doctor or pharmacist.",
    )


# 论文问答接口：POST /api/chat/paper，返回 AskResponse 类型
@router.post("/paper", response_model=AskResponse)
def paper_qa(
    req: AskRequest,                                    # 请求体
    db: Session = Depends(get_mysql_db),                # MySQL 数据库会话
    current_user: User = Depends(get_current_user),      # 当前已认证用户
):
    # 创建新的论文问答会话
    session = ChatSession(
        user_id=current_user.id,
        title=req.question[:100],
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,
        session_type="paper",        # 会话类型：论文问答
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 保存用户消息
    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    # 加载历史消息
    history_msgs = _load_history(session.id, db)
    workflow = MedAgentWorkflow()
    # 执行工作流，强制类型为论文问答
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=req.kb_ids,
        kb_name_map=_resolve_kb_names(req.kb_ids or [], db),
        history_messages=history_msgs,
        force_type="paper_qa",       # 强制论文问答模式
    )

    # 保存回答
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    # 返回问答响应
    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This summary is for reference only and does not constitute medical advice.",
    )


# 获取会话列表接口：GET /api/chat/sessions，返回 SessionResponse 列表
@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    db: Session = Depends(get_mysql_db),            # 数据库会话
    current_user: User = Depends(get_current_user),  # 当前已认证用户
    type: Optional[str] = None,                     # 可选的会话类型筛选
):
    # 查询当前用户的所有会话
    q = db.query(ChatSession).filter(ChatSession.user_id == current_user.id)
    if type:
        # 如果指定了类型，按类型过滤
        q = q.filter(ChatSession.session_type == type)
    # 按更新时间降序排列
    sessions = q.order_by(ChatSession.updated_at.desc()).all()
    # 将 ORM 对象转换为响应模型
    return [
        SessionResponse(
            id=s.id, user_id=s.user_id, title=s.title,
            session_type=s.session_type, summary=s.summary,
            created_at=s.created_at, updated_at=s.updated_at,
            kb_ids=_parse_kb_ids(s),              # 解析知识库 ID
        )
        for s in sessions
    ]


# 获取单个会话详情接口：GET /api/chat/sessions/{session_id}
@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: int,                                  # 会话 ID（路径参数）
    db: Session = Depends(get_mysql_db),              # 数据库会话
    current_user: User = Depends(get_current_user),    # 当前已认证用户
):
    # 查询会话是否存在且属于当前用户
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 查询该会话下的所有消息，按时间升序排列
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()

    # 返回会话详情，包含会话信息和消息列表
    return SessionDetailResponse(
        session=SessionResponse(
            id=session.id, user_id=session.user_id, title=session.title,
            session_type=session.session_type, summary=session.summary,
            created_at=session.created_at, updated_at=session.updated_at,
            kb_ids=_parse_kb_ids(session),
        ),
        messages=[
            MessageResponse(
                id=m.id, session_id=m.session_id, role=m.role,
                content=m.content, references_json=m.references_json,
                safety_flag=m.safety_flag, created_at=m.created_at,
            )
            for m in messages
        ],
    )


# 删除会话接口：DELETE /api/chat/sessions/{session_id}
@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,                                  # 会话 ID（路径参数）
    db: Session = Depends(get_mysql_db),              # MySQL 数据库会话
    current_user: User = Depends(get_current_user),    # 当前已认证用户
):
    # 查询会话是否存在且属于当前用户
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 删除关联的聊天历史文档（存储在知识库中的对话记录）
    sid_str = str(session_id)
    docs = db.query(Document).filter(
        Document.source_id == 0,
        Document.uploader_id == current_user.id,
        Document.source_url == sid_str,
    ).all()
    if docs:
        # 如果有关联文档，需要同时删除 PostgreSQL 中的切片和 MySQL 中的文档记录
        doc_ids = [d.id for d in docs]
        try:
            # 连接到 PostgreSQL 数据库
            pg_db: Session = PgSessionLocal()
            try:
                # 删除这些文档在 PostgreSQL 中的切片
                pg_db.query(DocumentChunk).filter(
                    DocumentChunk.document_id.in_(doc_ids),
                ).delete(synchronize_session=False)
                pg_db.commit()
            except Exception as exc:
                logger.warning("Failed to delete chat_history chunks: %s", exc)
                pg_db.rollback()
            finally:
                pg_db.close()
        except Exception as exc:
            logger.warning("Failed to connect to pg for chunk cleanup: %s", exc)

        # 删除 MySQL 中的文档记录
        db.query(Document).filter(Document.id.in_(doc_ids)).delete(
            synchronize_session=False
        )

    # 删除所有会话消息
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    # 删除会话本身
    db.delete(session)
    # 提交事务
    db.commit()
    return {"message": "Session deleted"}
