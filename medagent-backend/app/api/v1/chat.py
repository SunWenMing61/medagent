import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db, PgSessionLocal
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.chat import (
    AskRequest, AskResponse, SessionResponse,
    MessageResponse, SessionDetailResponse,
)
from app.graphs.medagent_graph import MedAgentWorkflow
from app.graphs.nodes import _build_history_text
from app.services.chat_history_service import (
    get_or_create_chat_history_kb,
    store_conversation,
    cleanup_old_chunks,
)

router = APIRouter()
workflow = MedAgentWorkflow()


def _merge_chat_history_kb(kb_ids: Optional[List[int]]) -> List[int]:
    """Auto-include the global chat_history KB in the search scope."""
    history_kb_id = get_or_create_chat_history_kb()
    if kb_ids:
        merged = list(set(kb_ids) | {history_kb_id})
    else:
        merged = [history_kb_id]
    return merged


def _get_all_user_kbs(current_user: User, db: Session) -> List[int]:
    """Return all KB IDs accessible to the user (owned + public + chat_history)."""
    history_kb_id = get_or_create_chat_history_kb()
    if current_user.role == "admin":
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | (KnowledgeBase.visibility == "public")
        ).all()
    else:
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1))
        ).all()
    kb_ids = [kb.id for kb in kbs]
    return list(set(kb_ids) | {history_kb_id})


def _resolve_kb_names(kb_ids: List[int], db: Session) -> Dict[int, str]:
    """Resolve KB IDs to human-readable names."""
    if not kb_ids:
        return {}
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all()
    return {kb.id: kb.name for kb in kbs}


def _load_history(session_id: int, db: Session) -> List[dict]:
    """Load previous user+assistant messages from a session."""
    msgs = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    history = []
    for m in msgs:
        history.append({"role": m.role, "content": m.content})
    return history


def _save_kb_ids(session: ChatSession, kb_ids: list[int] | None, db: Session):
    """Save selected KB IDs to a session, if any."""
    if kb_ids:
        session.kb_ids_json = json.dumps(kb_ids)
        db.commit()


def _parse_kb_ids(session: ChatSession) -> list[int] | None:
    """Parse kb_ids_json from a ChatSession into a list, or None."""
    if session.kb_ids_json:
        try:
            return json.loads(session.kb_ids_json)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _post_process_chat(user_id: int, kb_id: int, question: str, answer: str, session_id: int | None = None):
    """Background task: store conversation and cleanup old chunks."""
    try:
        store_conversation(user_id, kb_id, question, answer, session_id=session_id)
    except Exception as e:
        logger.error("Failed to store conversation: %s", e)
    try:
        cleanup_old_chunks(kb_id)
    except Exception as e:
        logger.error("Failed to cleanup old chunks: %s", e)


@router.post("/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session_id = req.session_id
    if not session_id:
        session = ChatSession(
            user_id=current_user.id,
            title=req.question[:100],
            session_type="qa",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id
        _save_kb_ids(session, req.kb_ids, db)
    else:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    msg = ChatMessage(session_id=session_id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(session_id, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session_id,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        web_search_enabled=req.web_search_enabled,
        deep_thinking_enabled=req.deep_thinking_enabled,
    )

    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    history_kb_id = get_or_create_chat_history_kb()
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        req.question, result["final_response"], session_id,
    )

    return AskResponse(
        session_id=session_id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "Please consult a qualified healthcare professional for medical decisions.",
    )


@router.post("/ask/stream")
def ask_question_stream(
    req: AskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Stream the multi-agent answer via SSE.

    Sub-agents run synchronously, then the final aggregator response is
    streamed token-by-token.  The complete answer is saved to the DB
    after streaming finishes.
    """
    session_id = req.session_id
    if not session_id:
        session = ChatSession(
            user_id=current_user.id,
            title=req.question[:100],
            session_type="qa",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id
        _save_kb_ids(session, req.kb_ids, db)
    else:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    msg = ChatMessage(session_id=session_id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(session_id, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    from app.graphs.medagent_graph import MedAgentWorkflow as Mw
    from app.graphs.nodes import (
        classify_question_node, sub_agent_retrieve_node,
        sub_agent_generate_and_aggregate, safety_check_node, format_response_node,
    )
    from app.graphs.graph_state import MedAgentState

    state = MedAgentState(
        question=req.question,
        user_id=current_user.id,
        session_id=session_id,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        web_search_enabled=req.web_search_enabled,
        deep_thinking_enabled=req.deep_thinking_enabled,
    )

    # Run classify, retrieve, sub-agents synchronously
    state.question_type = "medical_qa"
    state = sub_agent_retrieve_node(state)

    # Run sub-agents + aggregator
    from app.graphs.nodes import (
        _build_history_text, _load_prompt, _get_prompt_file, _llm_call_stream,
        generate_thinking_stream,
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed

    prompt_file = _get_prompt_file(state.question_type)
    history_text = _build_history_text(state.history_messages)

    sub_answers = []
    kb_tasks = []
    for kb_id in state.kb_ids:
        chunks = state.per_kb_chunks.get(kb_id, [])
        kb_name = state.get_kb_name(kb_id)
        if chunks:
            kb_tasks.append((kb_id, kb_name, chunks))

    if kb_tasks:
        with ThreadPoolExecutor(max_workers=min(len(kb_tasks), 8)) as executor:
            futures = []
            for kb_id, kb_name, chunks in kb_tasks:
                from app.graphs.nodes import _run_sub_agent
                f = executor.submit(_run_sub_agent, kb_id, kb_name, state.question, chunks, prompt_file, history_text)
                futures.append(f)
            for f in as_completed(futures):
                try:
                    sub_answers.append(f.result())
                except Exception as e:
                    sub_answers.append({"kb_id": 0, "kb_name": "unknown", "answer": f"（子Agent失败: {e}）", "chunk_count": 0})

    # Set state.sub_answers BEFORE event_generator so deep thinking can use them
    state.sub_answers = sub_answers

    sub_answer_texts = []
    for sa in sub_answers:
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # Add web search results
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（所有知识库均未返回相关信息）"

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

    async def event_generator():
        full_text = ""
        thinking_text = ""

        # Phase 1: Deep thinking streaming (if enabled)
        if req.deep_thinking_enabled:
            try:
                for token in generate_thinking_stream(state):
                    thinking_text += token
                    yield f"data: {json.dumps({'type': 'think', 'token': token})}\n\n"
            except Exception as e:
                logger.warning("Deep thinking stream error: %s", e)

        # Phase 2: Answer streaming
        try:
            for token in _llm_call_stream(aggregator_prompt, temperature=0.5, max_tokens=2048):
                full_text += token
                yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # After streaming completes, run safety + format
        state.raw_answer = full_text
        state.thinking_content = thinking_text
        state.sub_answers = sub_answers
        safety_check_node(state)
        format_response_node(state)

        # Save to DB
        db2 = next(get_mysql_db())
        try:
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=state.final_response,
                references_json=state.references,
                safety_flag=state.safety_flag,
            )
            db2.add(assistant_msg)
            db2.commit()

            history_kb_id = get_or_create_chat_history_kb()
            store_conversation(current_user.id, history_kb_id, req.question, state.final_response, session_id=session_id)
            cleanup_old_chunks(history_kb_id)

            # Save IDs while session is still open
            saved_message_id = assistant_msg.id
        except Exception as e:
            logger.error("Failed to save streamed answer: %s", e)
            saved_message_id = None
        finally:
            db2.close()

        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'message_id': saved_message_id, 'safety_flag': state.safety_flag, 'thinking': thinking_text})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ==============================================================================
# Multipart chat endpoints — support file/image upload alongside question
# ==============================================================================

def _process_chat_files(files: List[UploadFile]) -> tuple:
    """Process uploaded chat files.

    Returns (attachments list, temp_file_paths list for cleanup).
    """
    from app.utils.chat_attachments import process_attachment, save_uploaded_file, cleanup_file

    attachments = []
    temp_files = []

    for file in files:
        if not file.filename:
            continue
        try:
            content = file.file.read()
            file_path = save_uploaded_file(content, file.filename)
            temp_files.append(file_path)

            att = process_attachment(file_path, file.filename, file.content_type or "")
            if att:
                attachments.append(att)
        except Exception as e:
            logger.error("Failed to process chat file %s: %s", file.filename, e)

    return attachments, temp_files


@router.post("/ask-multipart")
async def ask_question_multipart(
    question: str = Form(...),
    web_search_enabled: bool = Form(False),
    deep_thinking_enabled: bool = Form(False),
    kb_ids: Optional[str] = Form(None),
    session_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(default=[]),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a question with optional file/image attachments.

    Accepts multipart/form-data with:
      - question (required)
      - web_search_enabled (optional, default false)
      - deep_thinking_enabled (optional, default false)
      - kb_ids (optional JSON array string)
      - session_id (optional)
      - files (optional, multiple)
    """
    # Parse kb_ids
    parsed_kb_ids = None
    if kb_ids:
        try:
            parsed_kb_ids = json.loads(kb_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    # Process attachments
    attachments, temp_files = _process_chat_files(files)

    # Create or get session
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

    msg = ChatMessage(session_id=sid, role="user", content=question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(sid, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    # Build attachments description for history storage
    att_desc = ""
    if attachments:
        from app.utils.chat_attachments import describe_attachments_for_prompt
        att_desc = "\n\n" + describe_attachments_for_prompt(attachments)

    result = workflow.run(
        question=question,
        user_id=current_user.id,
        session_id=sid,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        attachments=attachments,
        web_search_enabled=web_search_enabled,
        deep_thinking_enabled=deep_thinking_enabled,
    )

    assistant_msg = ChatMessage(
        session_id=sid,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    # Store conversation in chat history KB
    history_kb_id = get_or_create_chat_history_kb()
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        question, result["final_response"], sid,
    )

    # Clean up temp files
    for fp in temp_files:
        from app.utils.chat_attachments import cleanup_file
        background_tasks.add_task(cleanup_file, fp)

    return AskResponse(
        session_id=sid,
        question=question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "Please consult a qualified healthcare professional for medical decisions.",
    )


@router.post("/ask-multipart/stream")
async def ask_question_multipart_stream(
    question: str = Form(...),
    web_search_enabled: bool = Form(False),
    deep_thinking_enabled: bool = Form(False),
    kb_ids: Optional[str] = Form(None),
    session_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Stream a response with optional file/image attachments.

    Accepts multipart/form-data with:
      - question (required)
      - web_search_enabled (optional, default false)
      - deep_thinking_enabled (optional, default false)
      - kb_ids (optional JSON array string)
      - session_id (optional)
      - files (optional, multiple)
    """
    # Parse kb_ids
    parsed_kb_ids = None
    if kb_ids:
        try:
            parsed_kb_ids = json.loads(kb_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    # Process attachments
    attachments, temp_files = _process_chat_files(files)

    # Create or get session
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

    msg = ChatMessage(session_id=sid, role="user", content=question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(sid, db)
    merged_kb_ids = _get_all_user_kbs(current_user, db)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    from app.graphs.medagent_graph import MedAgentWorkflow as Mw
    from app.graphs.nodes import (
        classify_question_node, sub_agent_retrieve_node,
        sub_agent_generate_and_aggregate, safety_check_node, format_response_node,
    )
    from app.graphs.graph_state import MedAgentState

    state = MedAgentState(
        question=question,
        user_id=current_user.id,
        session_id=sid,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        attachments=attachments,
        web_search_enabled=web_search_enabled,
        deep_thinking_enabled=deep_thinking_enabled,
    )

    # Run classify, retrieve, sub-agents synchronously
    state.question_type = "medical_qa"
    state = sub_agent_retrieve_node(state)

    # Run sub-agents + aggregator
    from app.graphs.nodes import _build_history_text, _load_prompt, _get_prompt_file, _llm_call_stream, _llm_call_stream_multimodal
    from app.graphs.nodes import _run_sub_agent, generate_thinking_stream
    from concurrent.futures import ThreadPoolExecutor, as_completed

    prompt_file = _get_prompt_file(state.question_type)
    history_text = _build_history_text(state.history_messages)

    sub_answers = []
    kb_tasks = []
    for kb_id in state.kb_ids:
        chunks = state.per_kb_chunks.get(kb_id, [])
        kb_name = state.get_kb_name(kb_id)
        if chunks:
            kb_tasks.append((kb_id, kb_name, chunks))

    if kb_tasks:
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

    # Set state.sub_answers BEFORE event_generator so deep thinking can use them
    state.sub_answers = sub_answers

    sub_answer_texts = []
    for sa in sub_answers:
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # Add web search results
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（所有知识库均未返回相关信息）"

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

    # Add document attachment text to prompt
    doc_attachments = [a for a in attachments if a.get("type") == "document"]
    image_attachments = [a for a in attachments if a.get("type") == "image"]
    if doc_attachments:
        from app.utils.chat_attachments import describe_attachments_for_prompt
        aggregator_prompt += "\n\n" + describe_attachments_for_prompt(doc_attachments)

    async def event_generator():
        full_text = ""
        thinking_text = ""

        # Phase 1: Deep thinking streaming (if enabled)
        if state.deep_thinking_enabled:
            try:
                for token in generate_thinking_stream(state):
                    thinking_text += token
                    yield f"data: {json.dumps({'type': 'think', 'token': token})}\n\n"
            except Exception as e:
                logger.warning("Deep thinking stream error: %s", e)

        # Phase 2: Answer streaming
        try:
            if image_attachments:
                from app.utils.chat_attachments import build_multimodal_content
                content = build_multimodal_content(aggregator_prompt, image_attachments)
                for token in _llm_call_stream_multimodal(content, temperature=0.5, max_tokens=2048):
                    full_text += token
                    yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
            else:
                for token in _llm_call_stream(aggregator_prompt, temperature=0.5, max_tokens=2048):
                    full_text += token
                    yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # After streaming completes, run safety + format
        state.raw_answer = full_text
        state.thinking_content = thinking_text
        state.sub_answers = sub_answers
        safety_check_node(state)
        format_response_node(state)

        # Save to DB
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

        # Clean up temp files
        for fp in temp_files:
            from app.utils.chat_attachments import cleanup_file
            try:
                cleanup_file(fp)
            except Exception:
                pass

        yield f"data: {json.dumps({'done': True, 'session_id': sid, 'message_id': saved_message_id, 'safety_flag': state.safety_flag, 'thinking': thinking_text})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/health", response_model=AskResponse)
def health_consult(
    req: AskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        title=req.question[:100],
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,
        session_type="health",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(session.id, db)
    merged_kb_ids = _merge_chat_history_kb(current_user, req.kb_ids)
    kb_name_map = _resolve_kb_names(merged_kb_ids, db)

    workflow = MedAgentWorkflow()
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=merged_kb_ids,
        kb_name_map=kb_name_map,
        history_messages=history_msgs,
        force_type="health_consult",
    )

    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    history_kb_id = get_or_create_chat_history_kb()
    background_tasks.add_task(
        _post_process_chat, current_user.id, history_kb_id,
        req.question, result["final_response"], session.id,
    )

    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is for reference only and does not constitute medical advice. "
                   "If you are experiencing a medical emergency, please call emergency services immediately.",
    )


@router.post("/drug", response_model=AskResponse)
def drug_qa(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        title=req.question[:100],
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,
        session_type="drug",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    if not req.kb_ids:
        drug_kbs = db.query(KnowledgeBase).filter(
            KnowledgeBase.type == "drug",
            (KnowledgeBase.owner_id == current_user.id) |
            ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1)),
        ).all()
        req.kb_ids = [kb.id for kb in drug_kbs]

    history_msgs = _load_history(session.id, db)
    workflow = MedAgentWorkflow()
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=req.kb_ids,
        kb_name_map=_resolve_kb_names(req.kb_ids or [], db),
        history_messages=history_msgs,
        force_type="drug_qa",
    )

    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This information is based on the drug instructions provided. "
                   "Do not adjust or stop medication without consulting a doctor or pharmacist.",
    )


@router.post("/paper", response_model=AskResponse)
def paper_qa(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        title=req.question[:100],
        kb_ids_json=json.dumps(req.kb_ids) if req.kb_ids else None,
        session_type="paper",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(msg)
    db.commit()

    history_msgs = _load_history(session.id, db)
    workflow = MedAgentWorkflow()
    result = workflow.run(
        question=req.question,
        user_id=current_user.id,
        session_id=session.id,
        kb_ids=req.kb_ids,
        kb_name_map=_resolve_kb_names(req.kb_ids or [], db),
        history_messages=history_msgs,
        force_type="paper_qa",
    )

    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["final_response"],
        references_json=result.get("references"),
        safety_flag=result.get("safety_flag"),
    )
    db.add(assistant_msg)
    db.commit()

    return AskResponse(
        session_id=session.id,
        question=req.question,
        answer=result["final_response"],
        references=result.get("references"),
        safety_flag=result.get("safety_flag"),
        disclaimer="This summary is for reference only and does not constitute medical advice.",
    )


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
    type: Optional[str] = None,
):
    q = db.query(ChatSession).filter(ChatSession.user_id == current_user.id)
    if type:
        q = q.filter(ChatSession.session_type == type)
    sessions = q.order_by(ChatSession.updated_at.desc()).all()
    return [
        SessionResponse(
            id=s.id, user_id=s.user_id, title=s.title,
            session_type=s.session_type, summary=s.summary,
            created_at=s.created_at, updated_at=s.updated_at,
            kb_ids=_parse_kb_ids(s),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()

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


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete related chat_history documents (conversation stored in KB)
    sid_str = str(session_id)
    docs = db.query(Document).filter(
        Document.source_id == 0,
        Document.uploader_id == current_user.id,
        Document.source_url == sid_str,
    ).all()
    if docs:
        doc_ids = [d.id for d in docs]
        try:
            pg_db: Session = PgSessionLocal()
            try:
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

        db.query(Document).filter(Document.id.in_(doc_ids)).delete(
            synchronize_session=False
        )

    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}
