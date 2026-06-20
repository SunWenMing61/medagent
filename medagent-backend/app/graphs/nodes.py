"""Graph nodes for the MedAgent multi-agent workflow.

Each KB gets a sub-agent that independently retrieves chunks and generates
an answer. A main aggregator agent then synthesizes all sub-answers into
a comprehensive final response.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Generator, List

from app.graphs.graph_state import MedAgentState
from app.services.vector_service import vector_service
from app.services.safety_service import safety_service
from app.core.config import settings


# ---------------------------------------------------------------------------
# 1. Question classification (unchanged)
# ---------------------------------------------------------------------------

def classify_question_node(state: MedAgentState) -> MedAgentState:
    """Classify the question type using LLM or fallback rules."""
    import httpx

    api_key = settings.LLM_API_KEY
    if not api_key:
        state.question_type = _rule_based_classify(state.question)
        return state

    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "classify_prompt.txt"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    prompt_text = template.replace("{question}", state.question)

    try:
        response = httpx.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": 0.1,
                "max_tokens": 50,
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"].strip().lower()
        valid_types = {"medical_qa", "health_consult", "drug_qa", "paper_qa", "unknown"}
        if result in valid_types:
            state.question_type = result
        else:
            state.question_type = "medical_qa"
    except Exception:
        state.question_type = _rule_based_classify(state.question)

    return state


def _rule_based_classify(question: str) -> str:
    """Simple rule-based classification fallback."""
    q = question.lower()
    drug_keywords = ["drug", "medicine", "medication", "dosage", "side effect",
                     "drug interaction", "pill", "tablet", "capsule", "injection",
                     "药", "药品", "药物", "剂量", "副作用", "用法用量", "说明书"]
    health_keywords = ["health", "wellness", "diet", "exercise", "symptom",
                       "check-up", "prevention", "lifestyle",
                       "健康", "保健", "养生", "体检", "预防", "锻炼"]
    paper_keywords = ["paper", "study", "research", "journal", "clinical trial",
                      "literature", "论文", "研究", "文献", "临床试验", "期刊"]

    drug_score = sum(1 for kw in drug_keywords if kw in q)
    health_score = sum(1 for kw in health_keywords if kw in q)
    paper_score = sum(1 for kw in paper_keywords if kw in q)

    if drug_score >= health_score and drug_score >= paper_score and drug_score > 0:
        return "drug_qa"
    if paper_score >= health_score and paper_score > 0:
        return "paper_qa"
    if health_score > 0:
        return "health_consult"
    return "medical_qa"


# ---------------------------------------------------------------------------
# 2. Per-KB retrieval (replaces single retrieve_context_node)
# ---------------------------------------------------------------------------

def sub_agent_retrieve_node(state: MedAgentState) -> MedAgentState:
    """Retrieve chunks independently for each knowledge base.

    For every kb_id in state.kb_ids, perform a separate vector search
    scoped to that KB.  Results are stored in state.per_kb_chunks and
    also accumulated into state.references for the final response.

    If web_search_enabled is True, also performs a web search and stores
    results in state.web_search_results.
    """
    if not state.kb_ids:
        state.per_kb_chunks = {}
        state.references = []

    per_kb: Dict[int, List[dict]] = {}
    all_refs: List[dict] = []

    for kb_id in state.kb_ids:
        try:
            chunks = vector_service.search(
                query=state.question,
                kb_ids=[kb_id],
                top_k=settings.TOP_K,
                threshold=settings.SIMILARITY_THRESHOLD,
            )
            per_kb[kb_id] = chunks
            for c in chunks:
                all_refs.append({
                    "document_id": c["document_id"],
                    "kb_id": kb_id,
                    "kb_name": state.get_kb_name(kb_id),
                    "content": c["content"][:200],
                    "similarity": c["similarity"],
                    "page_num": c.get("page_num"),
                })
        except Exception:
            per_kb[kb_id] = []

    state.per_kb_chunks = per_kb
    state.references = all_refs

    # Web search
    if state.web_search_enabled:
        from app.utils.web_search import search_web, format_search_results
        try:
            web_results = search_web(
                query=state.question,
                api_key=settings.SEARCH_API_KEY,
                api_base=settings.SEARCH_API_BASE,
            )
            state.web_search_results = web_results
        except Exception as e:
            logger.warning("Web search failed in retrieve node: %s", e)
            state.web_search_results = []

    return state


# ---------------------------------------------------------------------------
# 3. Sub-agent generation + main-agent aggregation
#    (replaces single generate_answer_node)
# ---------------------------------------------------------------------------

def _load_prompt(prompt_file: str) -> str:
    """Load a prompt template file from the prompts directory."""
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", prompt_file
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _build_history_text(history_messages: List[dict], max_pairs: int = 5) -> str:
    """Build a conversation history string from previous messages."""
    if not history_messages:
        return ""
    lines = []
    count = 0
    for msg in reversed(history_messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"用户: {content.strip()}")
        elif role == "assistant":
            lines.append(f"助手: {content.strip()}")
        count += 1
        if count >= max_pairs * 2:
            break
    lines.reverse()
    return "\n\n".join(lines)


def _llm_call(prompt_text: str, temperature: float = 0.7,
              max_tokens: int = 2048, timeout: int = 60) -> str:
    """Make a single LLM call and return the response text."""
    return _llm_call_multimodal(
        [{"type": "text", "text": prompt_text}],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _llm_call_multimodal(
    content: list,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = 60,
) -> str:
    """Make an LLM call with multimodal content (text + images).

    Args:
        content: List of content blocks, e.g.
            [{"type": "text", "text": "..."},
             {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}]
    """
    import httpx

    api_key = settings.LLM_API_KEY
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")

    response = httpx.post(
        f"{settings.LLM_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": settings.LLM_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _llm_call_stream(prompt_text: str, temperature: float = 0.5,
                     max_tokens: int = 2048) -> Generator[str, None, None]:
    """Make a streaming LLM call, yielding tokens as they arrive."""
    yield from _llm_call_stream_multimodal(
        [{"type": "text", "text": prompt_text}],
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _llm_call_stream_multimodal(
    content: list,
    temperature: float = 0.5,
    max_tokens: int = 2048,
) -> Generator[str, None, None]:
    """Make a streaming multimodal LLM call, yielding tokens as they arrive."""
    import httpx

    api_key = settings.LLM_API_KEY
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")

    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": content}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        import json
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass


def _get_prompt_file(question_type: str) -> str:
    """Map question type to prompt file."""
    prompt_map = {
        "medical_qa": "medical_qa_prompt.txt",
        "health_consult": "health_consult_prompt.txt",
        "drug_qa": "drug_qa_prompt.txt",
        "paper_qa": "paper_summary_prompt.txt",
        "unknown": "medical_qa_prompt.txt",
    }
    return prompt_map.get(question_type, "medical_qa_prompt.txt")


def _build_thinking_prompt(state: MedAgentState) -> str:
    """Build the deep thinking prompt from graph state."""
    # Format sub-answers for context
    sub_answer_texts = []
    for sa in getattr(state, 'sub_answers', []):
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")
    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（知识库未返回相关信息）"

    # Add web search results
    web_context = ""
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_context = format_search_results(state.web_search_results)

    template = _load_prompt("deep_thinking_prompt.txt")
    prompt = (
        template
        .replace("{question}", state.question)
        .replace("{sub_answers}", sub_answers_formatted)
        .replace("{web_context}", web_context if web_context else "")
    )
    return prompt


def generate_thinking(state: MedAgentState) -> str:
    """Generate deep thinking content synchronously.

    Returns the thinking text or empty string if deep thinking disabled.
    """
    if not state.deep_thinking_enabled:
        return ""

    prompt = _build_thinking_prompt(state)
    try:
        return _llm_call(prompt, temperature=0.7, max_tokens=2048, timeout=90)
    except Exception as e:
        logger.warning("Deep thinking generation failed: %s", e)
        return ""


def generate_thinking_stream(state: MedAgentState):
    """Generate deep thinking content as a stream of tokens.

    Yields (token: str) for each token, or empty if disabled.
    """
    if not state.deep_thinking_enabled:
        return

    prompt = _build_thinking_prompt(state)
    try:
        for token in _llm_call_stream(prompt, temperature=0.7, max_tokens=2048):
            yield token
    except Exception as e:
        logger.warning("Deep thinking stream failed: %s", e)
        yield f"（深度思考过程遇到错误: {e}）"


def _run_sub_agent(kb_id: int, kb_name: str, question: str,
                   chunks: List[dict], prompt_file: str,
                   history_text: str = "") -> dict:
    """Execute a single sub-agent: retrieve context -> LLM generate -> return."""
    context_text = "\n\n---\n\n".join(
        [c["content"] for c in chunks]
    ) if chunks else ""

    if not context_text.strip():
        return {
            "kb_id": kb_id,
            "kb_name": kb_name,
            "answer": f"（知识库「{kb_name}」中未找到相关信息）",
            "chunk_count": 0,
        }

    template = _load_prompt(prompt_file)
    prompt_text = template.replace("{context}", context_text).replace("{question}", question)
    if history_text:
        if "{history}" in template:
            prompt_text = prompt_text.replace("{history}", history_text)
        else:
            prompt_text = f"**对话历史:**\n{history_text}\n\n---\n\n" + prompt_text

    try:
        answer = _llm_call(prompt_text, temperature=0.5, max_tokens=1024, timeout=60)
    except Exception as e:
        answer = f"（知识库「{kb_name}」回答生成失败: {str(e)}）"

    return {
        "kb_id": kb_id,
        "kb_name": kb_name,
        "answer": answer,
        "chunk_count": len(chunks),
    }


def sub_agent_generate_and_aggregate(state: MedAgentState) -> MedAgentState:
    """Phase 1: spawn sub-agents (one per KB with chunks) in parallel.

    Phase 2: feed all sub-answers to the aggregator agent.
    Supports multimodal attachments (images + documents).
    """
    api_key = settings.LLM_API_KEY
    if not api_key:
        state.raw_answer = "LLM API key not configured. Please set LLM_API_KEY in .env"
        return state

    prompt_file = _get_prompt_file(state.question_type)
    history_text = _build_history_text(state.history_messages)

    # ---- Phase 1: parallel sub-agent generation ----
    sub_answers: List[dict] = []
    futures = []

    # Build list of (kb_id, chunks) pairs that have content
    kb_tasks = []
    for kb_id in state.kb_ids:
        chunks = state.per_kb_chunks.get(kb_id, [])
        kb_name = state.get_kb_name(kb_id)
        kb_tasks.append((kb_id, kb_name, chunks))

    with ThreadPoolExecutor(max_workers=min(len(kb_tasks), 8)) as executor:
        for kb_id, kb_name, chunks in kb_tasks:
            future = executor.submit(
                _run_sub_agent, kb_id, kb_name, state.question, chunks, prompt_file, history_text,
            )
            futures.append(future)

        for future in as_completed(futures):
            try:
                sub_answers.append(future.result())
            except Exception as e:
                sub_answers.append({
                    "kb_id": 0,
                    "kb_name": "unknown",
                    "answer": f"（子Agent执行失败: {str(e)}）",
                    "chunk_count": 0,
                })

    state.sub_answers = sub_answers

    # ---- Phase 1.5: Deep thinking (optional) ----
    if state.deep_thinking_enabled:
        try:
            state.thinking_content = generate_thinking(state)
        except Exception as e:
            logger.warning("Deep thinking failed: %s", e)
            state.thinking_content = ""

    # ---- Phase 2: main aggregator ----
    # Format sub-answers for the aggregator prompt
    sub_answer_texts = []
    for sa in sub_answers:
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # Add web search results as a virtual sub-answer
    if state.web_search_results:
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts)

    if not sub_answers_formatted.strip():
        sub_answers_formatted = "（所有知识库均未返回相关信息）"

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

    # Check if we have image attachments — use multimodal call for the aggregator
    image_attachments = [a for a in state.attachments if a.get("type") == "image"]
    doc_attachments = [a for a in state.attachments if a.get("type") == "document"]

    if image_attachments:
        # Build multimodal content: text prompt + images
        from app.utils.chat_attachments import build_multimodal_content, describe_attachments_for_prompt

        # Add document text references to the prompt
        if doc_attachments:
            doc_desc = describe_attachments_for_prompt(doc_attachments)
            aggregator_prompt += f"\n\n用户上传的文档内容:\n{doc_desc}"

        content = build_multimodal_content(aggregator_prompt, image_attachments)

        try:
            state.raw_answer = _llm_call_multimodal(content, temperature=0.5, max_tokens=2048, timeout=90)
        except Exception as e:
            fallback_parts = [f"## {sa['kb_name']}\n{sa['answer']}" for sa in sub_answers if sa.get('answer')]
            if fallback_parts:
                state.raw_answer = "\n\n".join(fallback_parts)
            else:
                state.raw_answer = (
                    f"I apologize, but I encountered an error generating the answer. "
                    f"Please try again later. (Error: {str(e)})"
                )
    else:
        try:
            state.raw_answer = _llm_call(aggregator_prompt, temperature=0.5, max_tokens=2048, timeout=90)
        except Exception as e:
            # Fallback: concatenate sub-answers directly
            fallback_parts = [f"## {sa['kb_name']}\n{sa['answer']}" for sa in sub_answers if sa.get('answer')]
            if fallback_parts:
                state.raw_answer = "\n\n".join(fallback_parts)
            else:
                state.raw_answer = (
                    f"I apologize, but I encountered an error generating the answer. "
                    f"Please try again later. (Error: {str(e)})"
                )

    return state


# ---------------------------------------------------------------------------
# 4. Safety check (unchanged)
# ---------------------------------------------------------------------------

def safety_check_node(state: MedAgentState) -> MedAgentState:
    """Check answer for safety issues."""
    answer_lower = state.raw_answer.lower()

    boundary_indicators = [
        "diagnosis:", "diagnosis：", "prescribe", "prescription",
        "stop taking", "discontinue", "adjust your dosage",
    ]

    for indicator in boundary_indicators:
        if indicator in answer_lower:
            state.safety_flag = "boundary_warning"
            state.safe_answer = (
                state.raw_answer
                + "\n\n---\n⚠️ **Safety Notice:** The above response may contain information that should not be used "
                  "for self-diagnosis or self-treatment. Please consult a qualified healthcare professional."
            )
            return state

    is_high_risk, matched = safety_service.check_high_risk(state.question)
    if is_high_risk:
        state.safety_flag = "high_risk"
        state.safe_answer = safety_service.get_high_risk_response(matched)
        return state

    state.safety_flag = "safe"
    state.safe_answer = state.raw_answer
    return state


# ---------------------------------------------------------------------------
# 5. Response formatting (updated for multi-agent references)
# ---------------------------------------------------------------------------

def format_response_node(state: MedAgentState) -> MedAgentState:
    """Format the final response with references and disclaimer."""
    disclaimer = safety_service.get_disclaimer()

    if state.safety_flag == "high_risk":
        state.final_response = state.safe_answer
    elif state.safety_flag == "boundary_warning":
        state.final_response = state.safe_answer
    else:
        references_text = ""
        if state.sub_answers:
            ref_lines = []
            for sa in state.sub_answers:
                if sa.get("chunk_count", 0) > 0:
                    ref_lines.append(f"- **{sa['kb_name']}**: 贡献了 {sa['chunk_count']} 条相关段落")
            if ref_lines:
                references_text = "\n\n**各知识库贡献:**\n" + "\n".join(ref_lines)

        if not state.sub_answers or all(sa.get("chunk_count", 0) == 0 for sa in state.sub_answers):
            no_context_msg = (
                "\n\n**Note:** No relevant documents were found in the knowledge base for this question. "
                "The answer above is based on general knowledge and may not be specific to your situation."
            )
            state.final_response = state.safe_answer + no_context_msg + "\n\n---\n" + disclaimer
        else:
            state.final_response = state.safe_answer + references_text + "\n---\n" + disclaimer

    return state
