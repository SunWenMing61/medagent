"""Graph nodes for the MedAgent multi-agent workflow.
# MedAgent 多智能体工作流的图节点模块

Each KB gets a sub-agent that independently retrieves chunks and generates
an answer. A main aggregator agent then synthesizes all sub-answers into
a comprehensive final response.
# 每个知识库对应一个子智能体，独立检索文本块并生成回答。
# 主聚合器智能体再将所有子答案综合成一份全面的最终响应。
"""

# 导入 os 模块，用于文件路径操作（加载提示词模板文件）
import os
# 导入 ThreadPoolExecutor（线程池执行器）和 as_completed（获取已完成 Future），用于并行执行子智能体任务
from concurrent.futures import ThreadPoolExecutor, as_completed
# 导入类型注解：Dict（字典）、Generator（生成器）、List（列表）
from typing import Dict, Generator, List

# 导入工作流状态类，在各节点间传递和更新状态数据
from app.graphs.graph_state import MedAgentState
# 导入向量检索服务，用于从知识库中检索与问题相关的文本块
from app.services.vector_service import vector_service
# 导入安全检测服务，用于检查问答内容是否涉及高风险话题
from app.services.safety_service import safety_service
# 导入全局配置对象，获取 LLM API 地址、密钥、模型名称等设置
from app.core.config import settings


# ---------------------------------------------------------------------------
# 1. Question classification
# 1. 问题分类节点
# ---------------------------------------------------------------------------

# 定义 classify_question_node 函数：使用 LLM 对用户问题进行类型分类，失败时回退到规则分类
def classify_question_node(state: MedAgentState) -> MedAgentState:
    """Classify the question type using LLM or fallback rules."""  # 使用 LLM 对问题分类，若失败则回退到规则分类
    # 在函数内导入 httpx，用于发送 HTTP 请求调用 LLM API
    import httpx

    # 从配置中获取 LLM API 密钥
    api_key = settings.LLM_API_KEY
    # 如果 API 密钥未配置，则跳过 LLM 调用，直接使用规则分类
    if not api_key:
        # 调用基于关键词匹配的规则分类函数
        state.question_type = _rule_based_classify(state.question)
        # 返回更新后的状态
        return state

    # 构建分类提示词模板的完整文件路径：当前文件所在目录的上级目录下的 prompts/classify_prompt.txt
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "classify_prompt.txt"
    )
    # 以 UTF-8 编码打开并读取提示词模板文件
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 将模板中的 {question} 占位符替换为实际用户问题文本
    prompt_text = template.replace("{question}", state.question)

    try:
        # 发送 POST 请求到 LLM 的聊天补全接口
        response = httpx.post(
            f"{settings.LLM_API_BASE}/chat/completions",  # LLM API 的完整 URL
            headers={"Authorization": f"Bearer {api_key}"},  # 身份验证头
            json={
                "model": settings.LLM_MODEL,  # 使用的模型名称
                "messages": [{"role": "user", "content": prompt_text}],  # 用户消息（分类提示词）
                "temperature": 0.1,  # 低温度值使分类结果更加确定、可复现
                "max_tokens": 50,  # 分类只需返回短类型名称，50 个 token 足够
            },
            timeout=15,  # 请求超时时间 15 秒
        )
        # 检查 HTTP 响应状态，非 2xx 时会抛出异常
        response.raise_for_status()
        # 从响应 JSON 中提取模型回复的文本内容，去除首尾空白并转为小写
        result = response.json()["choices"][0]["message"]["content"].strip().lower()
        # 定义所有有效的分类类型集合
        valid_types = {"medical_qa", "health_consult", "drug_qa", "paper_qa", "unknown"}
        # 如果 LLM 返回的值在有效类型集合中，则接受该分类结果
        if result in valid_types:
            state.question_type = result
        else:
            # 如果 LLM 返回了无效类型，则默认归类为 medical_qa
            state.question_type = "medical_qa"
    except Exception:
        # 如果 LLM 调用过程中发生任何异常（网络错误、解析错误等），回退到规则分类
        state.question_type = _rule_based_classify(state.question)

    # 返回更新了问题分类的状态对象
    return state


# 定义 _rule_based_classify 函数：基于关键词匹配的简单规则分类，作为 LLM 分类失败时的回退方案
def _rule_based_classify(question: str) -> str:
    """Simple rule-based classification fallback."""  # 简单的基于规则的分类回退方法
    # 将问题文本转为小写，便于进行不区分大小写的关键词匹配
    q = question.lower()
    # 定义与药物相关的关键词列表（中英文混合），用于匹配药物咨询类问题
    drug_keywords = ["drug", "medicine", "medication", "dosage", "side effect",
                     "drug interaction", "pill", "tablet", "capsule", "injection",
                     "药", "药品", "药物", "剂量", "副作用", "用法用量", "说明书"]
    # 定义与健康咨询相关的关键词列表（中英文混合），用于匹配健康养生类问题
    health_keywords = ["health", "wellness", "diet", "exercise", "symptom",
                       "check-up", "prevention", "lifestyle",
                       "健康", "保健", "养生", "体检", "预防", "锻炼"]
    # 定义与学术论文相关的关键词列表（中英文混合），用于匹配论文分析类问题
    paper_keywords = ["paper", "study", "research", "journal", "clinical trial",
                      "literature", "论文", "研究", "文献", "临床试验", "期刊"]

    # 计算问题文本中包含的药物相关关键词数量（计分）
    drug_score = sum(1 for kw in drug_keywords if kw in q)
    # 计算问题文本中包含的健康咨询相关关键词数量（计分）
    health_score = sum(1 for kw in health_keywords if kw in q)
    # 计算问题文本中包含的论文相关关键词数量（计分）
    paper_score = sum(1 for kw in paper_keywords if kw in q)

    # 如果药物得分最高且大于 0，则判定为药物咨询类问题
    if drug_score >= health_score and drug_score >= paper_score and drug_score > 0:
        return "drug_qa"
    # 如果论文得分最高且大于 0，则判定为论文分析类问题
    if paper_score >= health_score and paper_score > 0:
        return "paper_qa"
    # 如果健康咨询得分大于 0，则判定为健康咨询类问题
    if health_score > 0:
        return "health_consult"
    # 所有关键词均未匹配时，默认归类为通用医学问答
    return "medical_qa"


# ---------------------------------------------------------------------------
# 2. Per-KB retrieval (replaces single retrieve_context_node)
# 2. 按知识库独立检索（替代原来的单次检索节点）
# ---------------------------------------------------------------------------

# 定义 sub_agent_retrieve_node 函数：为每个知识库独立执行向量检索，并可选执行网络搜索
def sub_agent_retrieve_node(state: MedAgentState) -> MedAgentState:
    """Retrieve chunks independently for each knowledge base.
    # 为每个知识库独立检索文本块

    For every kb_id in state.kb_ids, perform a separate vector search
    scoped to that KB.  Results are stored in state.per_kb_chunks and
    also accumulated into state.references for the final response.
    # 对 state.kb_ids 中的每个 kb_id，执行限定在该知识库范围内的独立向量搜索。
    # 检索结果存入 state.per_kb_chunks，同时汇总到 state.references 用于最终响应。

    If web_search_enabled is True, also performs a web search and stores
    results in state.web_search_results.
    # 如果 web_search_enabled 为 True，还会执行网络搜索并将结果存入 state.web_search_results。
    """
    # 如果知识库 ID 列表为空，则直接返回空的检索结果
    if not state.kb_ids:
        state.per_kb_chunks = {}  # 各知识库检索结果设为空字典
        state.references = []     # 引用列表设为空列表
        # 注：这里缺少 return state，但后续代码会继续执行，并在空列表情况下同样更新 state 后返回

    # 初始化用于按知识库 ID 存储文本块的字典
    per_kb: Dict[int, List[dict]] = {}
    # 初始化用于存储所有引用的列表
    all_refs: List[dict] = []

    # 遍历所有需要查询的知识库 ID
    for kb_id in state.kb_ids:
        try:
            # 调用向量检索服务，查询与问题相关的文本块
            chunks = vector_service.search(
                query=state.question,          # 查询字符串
                kb_ids=[kb_id],               # 限定检索范围为当前知识库
                top_k=settings.TOP_K,          # 返回前 K 个最相似的文本块
                threshold=settings.SIMILARITY_THRESHOLD,  # 相似度阈值过滤
            )
            # 将检索结果按知识库 ID 存入字典
            per_kb[kb_id] = chunks
            # 遍历每个文本块，构造引用信息并加入全局引用列表
            for c in chunks:
                all_refs.append({
                    "document_id": c["document_id"],    # 文档唯一标识
                    "kb_id": kb_id,                      # 所属知识库 ID
                    "kb_name": state.get_kb_name(kb_id), # 知识库可读名称
                    "content": c["content"][:200],       # 文本块前 200 个字符作为摘要
                    "similarity": c["similarity"],        # 与问题的相似度得分
                    "page_num": c.get("page_num"),        # 可选的页码信息
                })
        except Exception:
            # 如果某个知识库检索失败，为该知识库设置空列表，保证流程不中断
            per_kb[kb_id] = []

    # 将按知识库分组的检索结果存入状态
    state.per_kb_chunks = per_kb
    # 将所有引用信息存入状态
    state.references = all_refs

    # 如果启用了网络搜索，执行网络搜索并合并结果
    if state.web_search_enabled:
        # 导入网络搜索工具函数
        from app.utils.web_search import search_web, format_search_results
        try:
            # 调用网络搜索 API
            web_results = search_web(
                query=state.question,              # 搜索查询
                api_key=settings.SEARCH_API_KEY,    # 搜索引擎 API 密钥
                api_base=settings.SEARCH_API_BASE,  # 搜索引擎 API 基础地址
            )
            # 将搜索结果存入状态
            state.web_search_results = web_results
        except Exception as e:
            # 网络搜索失败时记录警告日志，并设搜索结果为空列表
            logger.warning("Web search failed in retrieve node: %s", e)
            state.web_search_results = []

    # 返回更新后的状态对象
    return state


# ---------------------------------------------------------------------------
# 3. Sub-agent generation + main-agent aggregation
# 3. 子智能体生成 + 主智能体聚合（替代原来的单次生成节点）
# ---------------------------------------------------------------------------

# 定义 _load_prompt 函数：从 prompts 目录加载指定名称的提示词模板文件
def _load_prompt(prompt_file: str) -> str:
    """Load a prompt template file from the prompts directory."""  # 从 prompts 目录加载提示词模板文件
    # 构建提示词文件的完整路径：当前文件所在目录的上级目录下的 prompts/{文件名}
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", prompt_file
    )
    # 以 UTF-8 编码打开文件并读取全部内容
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# 定义 _build_history_text 函数：将历史对话消息列表格式化为字符串，用于给 LLM 提供对话上下文
def _build_history_text(history_messages: List[dict], max_pairs: int = 5) -> str:
    """Build a conversation history string from previous messages."""  # 从历史消息构建对话历史字符串
    # 如果没有历史消息，直接返回空字符串
    if not history_messages:
        return ""
    # 初始化列表，用于存储格式化后的消息行
    lines = []
    # 计数器，用于限制消息对数量
    count = 0
    # 从最新的消息开始反向遍历（因为最近的对话最相关）
    for msg in reversed(history_messages):
        # 获取消息的角色（user 或 assistant）
        role = msg.get("role", "")
        # 获取消息的文本内容
        content = msg.get("content", "")
        # 如果角色是用户，格式化为 "用户: {内容}"
        if role == "user":
            lines.append(f"用户: {content.strip()}")
        # 如果角色是助手，格式化为 "助手: {内容}"
        elif role == "assistant":
            lines.append(f"助手: {content.strip()}")
        # 计数器递增
        count += 1
        # 限制最大消息对数为 max_pairs * 2（因为一对包含 user 和 assistant 两条）
        if count >= max_pairs * 2:
            break
    # 由于是反向遍历的，最终需要反转列表以恢复正确的时间顺序
    lines.reverse()
    # 将所有行用双换行连接成一个字符串并返回
    return "\n\n".join(lines)


# 定义 _llm_call 函数：发送纯文本提示词给 LLM 并返回响应文本
def _llm_call(prompt_text: str, temperature: float = 0.7,
              max_tokens: int = 2048, timeout: int = 60) -> str:
    """Make a single LLM call and return the response text."""  # 发起一次 LLM 调用并返回响应文本
    # 将纯文本提示词包装为多模态内容格式（仅包含 text 块），然后调用多模态 LLM 接口
    return _llm_call_multimodal(
        [{"type": "text", "text": prompt_text}],  # 内容块列表，仅含一条文本块
        temperature=temperature,                   # 生成温度
        max_tokens=max_tokens,                     # 最大生成 token 数
        timeout=timeout,                           # 请求超时时间
    )


# 定义 _llm_call_multimodal 函数：发送多模态内容（文本 + 图片）给 LLM 并返回响应文本
def _llm_call_multimodal(
    content: list,         # 多模态内容块列表，每个块包含 type（text/image_url）和对应数据
    temperature: float = 0.7,   # 生成温度，控制输出的随机性
    max_tokens: int = 2048,     # 最大生成的 token 数量
    timeout: int = 60,          # HTTP 请求超时时间（秒）
) -> str:
    """Make an LLM call with multimodal content (text + images).
    # 使用多模态内容（文本 + 图片）调用 LLM

    Args:
        content: List of content blocks, e.g.
            [{"type": "text", "text": "..."},
             {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}]
        # 内容块列表，示例：
        # [{"type": "text", "text": "..."},
        #  {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}]
    """
    # 在函数内导入 httpx，用于发送 HTTP 请求
    import httpx

    # 从配置获取 LLM API 密钥
    api_key = settings.LLM_API_KEY
    # 如果 API 密钥未配置，则抛出运行时错误
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")

    # 发送 POST 请求到 LLM 的聊天补全接口
    response = httpx.post(
        f"{settings.LLM_API_BASE}/chat/completions",  # API 完整 URL
        headers={"Authorization": f"Bearer {api_key}"},  # 认证头
        json={
            "model": settings.LLM_MODEL,    # 模型名称
            "messages": [{"role": "user", "content": content}],  # 多模态消息内容
            "temperature": temperature,     # 温度参数
            "max_tokens": max_tokens,       # 最大 token 数
        },
        timeout=timeout,  # 超时时间
    )
    # 检查响应状态码，非 2xx 时抛出异常
    response.raise_for_status()
    # 从响应 JSON 中提取助手的消息内容并返回
    return response.json()["choices"][0]["message"]["content"]


# 定义 _llm_call_stream 函数：发送纯文本提示词给 LLM 并流式返回生成的 token
def _llm_call_stream(prompt_text: str, temperature: float = 0.5,
                     max_tokens: int = 2048) -> Generator[str, None, None]:
    """Make a streaming LLM call, yielding tokens as they arrive."""  # 发起流式 LLM 调用，逐个产出 token
    # 将纯文本包装为多模态内容格式（仅含 text 块），然后调用流式多模态接口
    yield from _llm_call_stream_multimodal(
        [{"type": "text", "text": prompt_text}],  # 内容块列表
        temperature=temperature,                   # 生成温度
        max_tokens=max_tokens,                     # 最大生成 token 数
    )


# 定义 _llm_call_stream_multimodal 函数：发送多模态内容并以生成器方式流式返回 LLM 的 token
def _llm_call_stream_multimodal(
    content: list,           # 多模态内容块列表
    temperature: float = 0.5,    # 生成温度
    max_tokens: int = 2048,      # 最大生成 token 数
) -> Generator[str, None, None]:  # 返回生成器，逐个产出 token 字符串
    """Make a streaming multimodal LLM call, yielding tokens as they arrive."""  # 发起流式多模态 LLM 调用，逐个产出 token
    # 在函数内导入 httpx
    import httpx

    # 从配置获取 LLM API 密钥
    api_key = settings.LLM_API_KEY
    # 如果 API 密钥未配置，则抛出运行时错误
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")

    # 使用 httpx 客户端（超时 120 秒）建立流式连接
    with httpx.Client(timeout=120) as client:
        # 以流式方式发送 POST 请求
        with client.stream(
            "POST",
            f"{settings.LLM_API_BASE}/chat/completions",  # API URL
            headers={"Authorization": f"Bearer {api_key}"},  # 认证头
            json={
                "model": settings.LLM_MODEL,    # 模型名称
                "messages": [{"role": "user", "content": content}],  # 多模态消息
                "temperature": temperature,     # 温度
                "max_tokens": max_tokens,       # 最大 token 数
                "stream": True,                 # 启用流式模式
            },
        ) as response:
            # 检查 HTTP 响应状态
            response.raise_for_status()
            # 逐行读取服务器发送的事件流（SSE 格式）
            for line in response.iter_lines():
                # 如果行为空或者是结束标记 "data: [DONE]"，则跳过
                if not line or line == "data: [DONE]":
                    continue
                # 处理以 "data: " 开头的数据行（标准的 SSE 格式）
                if line.startswith("data: "):
                    try:
                        # 在函数内导入 json 模块用于解析
                        import json
                        # 去除 "data: " 前缀后解析 JSON
                        chunk = json.loads(line[6:])
                        # 从回复块中提取增量内容
                        delta = chunk["choices"][0].get("delta", {})
                        # 获取文本 token
                        token = delta.get("content", "")
                        # 如果 token 非空，则产出该 token
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        # 解析失败时静默跳过（遇到格式异常的行时不中断流）
                        pass


# 定义 _get_prompt_file 函数：根据问题类型映射到对应的提示词模板文件名
def _get_prompt_file(question_type: str) -> str:
    """Map question type to prompt file."""  # 将问题类型映射到提示词模板文件名
    # 问题类型到提示词模板文件名的映射字典
    prompt_map = {
        "medical_qa": "medical_qa_prompt.txt",        # 通用医学问答 -> 医学问答提示词
        "health_consult": "health_consult_prompt.txt",  # 健康咨询 -> 健康咨询提示词
        "drug_qa": "drug_qa_prompt.txt",              # 药物咨询 -> 药物问答提示词
        "paper_qa": "paper_summary_prompt.txt",        # 论文分析 -> 论文摘要提示词
        "unknown": "medical_qa_prompt.txt",            # 未知类型 -> 默认使用医学问答提示词
    }
    # 从映射中查找，若未找到则默认返回医学问答提示词
    return prompt_map.get(question_type, "medical_qa_prompt.txt")


# 定义 _build_thinking_prompt 函数：从当前状态构建深度思考模式的提示词
def _build_thinking_prompt(state: MedAgentState) -> str:
    """Build the deep thinking prompt from graph state."""  # 从工作流状态构建深度思考提示词
    # 格式化各子智能体的回答，构建深度思考的参考信息部分
    sub_answer_texts = []
    # 遍历状态中的子答案列表
    for sa in getattr(state, 'sub_answers', []):
        # 为每个子答案添加带知识库名称和段落数的标题
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")
    # 将所有子答案文本用分隔线连接，若无子答案则使用占位文本
    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts) if sub_answer_texts else "（知识库未返回相关信息）"

    # 如果存在网络搜索结果，将其格式化为额外的上下文
    web_context = ""
    if state.web_search_results:
        # 导入网络搜索结果格式化工具
        from app.utils.web_search import format_search_results
        web_context = format_search_results(state.web_search_results)

    # 加载深度思考专用的提示词模板文件
    template = _load_prompt("deep_thinking_prompt.txt")
    # 依次替换模板中的 {question}、{sub_answers}、{web_context} 占位符
    prompt = (
        template
        .replace("{question}", state.question)           # 替换用户问题
        .replace("{sub_answers}", sub_answers_formatted) # 替换知识库答案
        .replace("{web_context}", web_context if web_context else "")  # 替换网络搜索结果（若无则替换为空串）
    )
    return prompt


# 定义 generate_thinking 函数：以同步方式调用 LLM 生成深度思考内容
def generate_thinking(state: MedAgentState) -> str:
    """Generate deep thinking content synchronously.
    # 同步生成深度思考内容

    Returns the thinking text or empty string if deep thinking disabled.
    # 返回思考文本，若深度思考被禁用则返回空字符串
    """
    # 如果深度思考功能未启用，直接返回空字符串
    if not state.deep_thinking_enabled:
        return ""

    # 构建深度思考提示词
    prompt = _build_thinking_prompt(state)
    try:
        # 调用 LLM 生成思考内容（温度 0.7，最多 2048 token，超时 90 秒）
        return _llm_call(prompt, temperature=0.7, max_tokens=2048, timeout=90)
    except Exception as e:
        # 若生成失败则记录警告并返回空字符串
        logger.warning("Deep thinking generation failed: %s", e)
        return ""


# 定义 generate_thinking_stream 函数：以流式方式生成深度思考内容，逐个产出 token
def generate_thinking_stream(state: MedAgentState):
    """Generate deep thinking content as a stream of tokens.
    # 以流式方式生成深度思考内容

    Yields (token: str) for each token, or empty if disabled.
    # 逐个产出 token 字符串，若被禁用则无产出
    """
    # 如果深度思考功能未启用，直接返回（生成器无产出）
    if not state.deep_thinking_enabled:
        return

    # 构建深度思考提示词
    prompt = _build_thinking_prompt(state)
    try:
        # 调用流式 LLM 接口，逐个 token 产出
        for token in _llm_call_stream(prompt, temperature=0.7, max_tokens=2048):
            yield token
    except Exception as e:
        # 若流式生成失败，记录警告并产出一条错误提示
        logger.warning("Deep thinking stream failed: %s", e)
        yield f"（深度思考过程遇到错误: {e}）"


# 定义 _run_sub_agent 函数：执行单个子智能体任务（检索 + LLM 生成），返回包含答案的字典
def _run_sub_agent(kb_id: int, kb_name: str, question: str,
                   chunks: List[dict], prompt_file: str,
                   history_text: str = "") -> dict:
    """Execute a single sub-agent: retrieve context -> LLM generate -> return."""
    # 执行单个子智能体：加载上下文 -> LLM 生成 -> 返回结果

    # 将所有文本块内容用分隔线连接，构成上下文文本
    context_text = "\n\n---\n\n".join(
        [c["content"] for c in chunks]
    ) if chunks else ""

    # 如果上下文文本为空（没有检索到任何相关文本块）
    if not context_text.strip():
        # 返回表示"未找到相关信息"的答案字典
        return {
            "kb_id": kb_id,
            "kb_name": kb_name,
            "answer": f"（知识库「{kb_name}」中未找到相关信息）",  # 中文提示无相关结果
            "chunk_count": 0,  # 相关段落数为 0
        }

    # 加载与问题类型对应的提示词模板
    template = _load_prompt(prompt_file)
    # 将模板中的 {context} 替换为检索到的上下文文本，{question} 替换为用户问题
    prompt_text = template.replace("{context}", context_text).replace("{question}", question)
    # 如果有历史对话，将历史文本注入提示词
    if history_text:
        # 如果模板中本来就有 {history} 占位符，则直接替换
        if "{history}" in template:
            prompt_text = prompt_text.replace("{history}", history_text)
        else:
            # 否则在提示词最前面插入历史对话部分
            prompt_text = f"**对话历史:**\n{history_text}\n\n---\n\n" + prompt_text

    try:
        # 调用 LLM 生成回答（温度 0.5，最多 1024 token，超时 60 秒）
        answer = _llm_call(prompt_text, temperature=0.5, max_tokens=1024, timeout=60)
    except Exception as e:
        # 若生成失败，返回包含错误信息的答案
        answer = f"（知识库「{kb_name}」回答生成失败: {str(e)}）"

    # 返回包含答案信息的字典
    return {
        "kb_id": kb_id,          # 知识库 ID
        "kb_name": kb_name,      # 知识库名称
        "answer": answer,         # LLM 生成的答案文本
        "chunk_count": len(chunks),  # 使用的相关文本块数量
    }


# 定义 sub_agent_generate_and_aggregate 函数：阶段一并行执行子智能体，阶段二由主聚合器综合所有答案
def sub_agent_generate_and_aggregate(state: MedAgentState) -> MedAgentState:
    """Phase 1: spawn sub-agents (one per KB with chunks) in parallel.
    # 阶段一：并行启动子智能体（每个有文本块的知识库对应一个子智能体）

    Phase 2: feed all sub-answers to the aggregator agent.
    # 阶段二：将所有子答案馈送给主聚合器智能体

    Supports multimodal attachments (images + documents).
    # 支持多模态附件（图片 + 文档）
    """
    # 获取 LLM API 密钥
    api_key = settings.LLM_API_KEY
    # 如果 API 密钥未配置，则返回错误信息给用户
    if not api_key:
        state.raw_answer = "LLM API key not configured. Please set LLM_API_KEY in .env"
        return state

    # 根据问题类型确定要使用的提示词模板文件
    prompt_file = _get_prompt_file(state.question_type)
    # 构建历史对话文本
    history_text = _build_history_text(state.history_messages)

    # ---- 阶段一：并行子智能体生成 ----
    # 初始化子答案列表
    sub_answers: List[dict] = []
    # 初始化 Future 列表，用于管理并行任务
    futures = []

    # 构建需要执行的任务列表：每个包含文本块的知识库作为一个子智能体任务
    kb_tasks = []
    for kb_id in state.kb_ids:
        # 获取该知识库的检索文本块
        chunks = state.per_kb_chunks.get(kb_id, [])
        # 获取知识库的可读名称
        kb_name = state.get_kb_name(kb_id)
        # 将三元组（kb_id, kb_name, chunks）加入任务列表
        kb_tasks.append((kb_id, kb_name, chunks))

    # 创建线程池，最多 8 个并行工作线程
    with ThreadPoolExecutor(max_workers=min(len(kb_tasks), 8)) as executor:
        # 提交所有子智能体任务到线程池
        for kb_id, kb_name, chunks in kb_tasks:
            # 提交 _run_sub_agent 函数到执行器，传入各参数
            future = executor.submit(
                _run_sub_agent, kb_id, kb_name, state.question, chunks, prompt_file, history_text,
            )
            # 将返回的 Future 对象加入列表
            futures.append(future)

        # 遍历已完成的 Future，收集子智能体的执行结果
        for future in as_completed(futures):
            try:
                # 获取任务结果，加入子答案列表
                sub_answers.append(future.result())
            except Exception as e:
                # 若某个子智能体执行失败，添加错误信息占位
                sub_answers.append({
                    "kb_id": 0,               # 错误时知识库 ID 设为 0
                    "kb_name": "unknown",      # 错误时名称设为 unknown
                    "answer": f"（子Agent执行失败: {str(e)}）",  # 错误提示
                    "chunk_count": 0,          # 相关段落数为 0
                })

    # 将子答案列表存入状态
    state.sub_answers = sub_answers

    # ---- 阶段 1.5：深度思考（可选） ----
    # 如果启用了深度思考模式，生成推理过程
    if state.deep_thinking_enabled:
        try:
            # 调用同步生成函数获取思考内容
            state.thinking_content = generate_thinking(state)
        except Exception as e:
            # 若生成失败记录警告，并将思考内容置空
            logger.warning("Deep thinking failed: %s", e)
            state.thinking_content = ""

    # ---- 阶段二：主聚合器 ----
    # 格式化各子智能体的答案，准备输入聚合器
    sub_answer_texts = []
    for sa in sub_answers:
        # 为每个子答案添加带知识库名称和段落数的标题行
        header = f"【{sa['kb_name']}】({sa['chunk_count']} 条相关段落)"
        sub_answer_texts.append(f"{header}\n{sa['answer']}")

    # 如果存在网络搜索结果，将其作为"虚拟子答案"加入
    if state.web_search_results:
        # 导入网络搜索结果格式化工具
        from app.utils.web_search import format_search_results
        web_text = format_search_results(state.web_search_results)
        if web_text:
            # 添加网络搜索结果的格式化文本
            sub_answer_texts.append(f"【🌐 网络搜索结果】({len(state.web_search_results)} 条结果)\n{web_text}")

    # 将所有子答案文本用分隔线连接
    sub_answers_formatted = "\n\n---\n\n".join(sub_answer_texts)

    # 如果没有任何子答案文本（所有知识库均未返回信息）
    if not sub_answers_formatted.strip():
        sub_answers_formatted = "（所有知识库均未返回相关信息）"

    # 加载聚合器提示词模板
    aggregator_template = _load_prompt("aggregator_prompt.txt")
    # 替换模板中的 {question} 和 {sub_answers} 占位符
    aggregator_prompt = (
        aggregator_template
        .replace("{question}", state.question)           # 替换用户问题
        .replace("{sub_answers}", sub_answers_formatted) # 替换子答案汇总
    )
    # 如果有历史对话，将历史文本注入聚合器提示词
    if history_text:
        # 如果模板中有 {history} 占位符，直接替换
        if "{history}" in aggregator_template:
            aggregator_prompt = aggregator_prompt.replace("{history}", history_text)
        else:
            # 否则在提示词最前面插入历史对话部分
            aggregator_prompt = f"**对话历史:**\n{history_text}\n\n---\n\n" + aggregator_prompt

    # 检查是否有图片附件——有则使用多模态 LLM 调用
    image_attachments = [a for a in state.attachments if a.get("type") == "image"]
    # 检查是否有文档附件
    doc_attachments = [a for a in state.attachments if a.get("type") == "document"]

    # 处理包含图片附件的情况（使用多模态调用）
    if image_attachments:
        # 导入多模态内容构建和文档描述工具
        from app.utils.chat_attachments import build_multimodal_content, describe_attachments_for_prompt

        # 如果有文档附件，将文档内容描述添加到提示词末尾
        if doc_attachments:
            doc_desc = describe_attachments_for_prompt(doc_attachments)
            aggregator_prompt += f"\n\n用户上传的文档内容:\n{doc_desc}"

        # 构建多模态内容（文本提示 + 图片数据）
        content = build_multimodal_content(aggregator_prompt, image_attachments)

        try:
            # 使用多模态 LLM 接口生成答案
            state.raw_answer = _llm_call_multimodal(content, temperature=0.5, max_tokens=2048, timeout=90)
        except Exception as e:
            # 多模态调用失败时，直接拼接子答案作为降级方案
            fallback_parts = [f"## {sa['kb_name']}\n{sa['answer']}" for sa in sub_answers if sa.get('answer')]
            if fallback_parts:
                # 若有子答案，直接拼接各知识库的回答
                state.raw_answer = "\n\n".join(fallback_parts)
            else:
                # 无任何子答案时返回通用错误信息
                state.raw_answer = (
                    f"I apologize, but I encountered an error generating the answer. "
                    f"Please try again later. (Error: {str(e)})"
                )
    else:
        # 无图片附件，使用纯文本 LLM 调用
        try:
            state.raw_answer = _llm_call(aggregator_prompt, temperature=0.5, max_tokens=2048, timeout=90)
        except Exception as e:
            # 调用失败时，直接拼接子答案作为降级方案
            fallback_parts = [f"## {sa['kb_name']}\n{sa['answer']}" for sa in sub_answers if sa.get('answer')]
            if fallback_parts:
                # 若有子答案，直接拼接各知识库的回答
                state.raw_answer = "\n\n".join(fallback_parts)
            else:
                # 无任何子答案时返回通用错误信息
                state.raw_answer = (
                    f"I apologize, but I encountered an error generating the answer. "
                    f"Please try again later. (Error: {str(e)})"
                )

    # 返回更新了原始答案的状态对象
    return state


# ---------------------------------------------------------------------------
# 4. Safety check
# 4. 安全检查节点
# ---------------------------------------------------------------------------

# 定义 safety_check_node 函数：对生成的原始答案进行安全性和合规性检查
def safety_check_node(state: MedAgentState) -> MedAgentState:
    """Check answer for safety issues."""  # 检查回答是否存在安全问题
    # 将原始答案转为小写，便于进行不区分大小写的关键词匹配
    answer_lower = state.raw_answer.lower()

    # 定义越界行为指示器关键词列表——这些词表明模型可能越过了安全边界
    boundary_indicators = [
        "diagnosis:",       # 诊断（英文冒号）
        "diagnosis：",      # 诊断（中文冒号）
        "prescribe",        # 开药方
        "prescription",     # 处方
        "stop taking",      # 停止服药
        "discontinue",      # 停药
        "adjust your dosage",  # 调整剂量
    ]

    # 遍历越界关键词列表
    for indicator in boundary_indicators:
        # 如果答案中包含越界关键词
        if indicator in answer_lower:
            # 设置安全标记为越界警告
            state.safety_flag = "boundary_warning"
            # 在原始答案后追加安全提醒声明
            state.safe_answer = (
                state.raw_answer
                + "\n\n---\n⚠️ **Safety Notice:** The above response may contain information that should not be used "
                  "for self-diagnosis or self-treatment. Please consult a qualified healthcare professional."
                # 安全提示：以上回复可能包含不应用于自我诊断或自我治疗的信息，请咨询专业医疗人员
            )
            # 返回更新后的状态
            return state

    # 调用安全服务检查用户问题是否涉及高风险话题（如自杀、自残等）
    is_high_risk, matched = safety_service.check_high_risk(state.question)
    # 如果问题被判定为高风险
    if is_high_risk:
        # 设置安全标记为高风险
        state.safety_flag = "high_risk"
        # 使用安全服务获取预设的高风险标准回复
        state.safe_answer = safety_service.get_high_risk_response(matched)
        # 返回更新后的状态
        return state

    # 以上检查均通过，标记为安全
    state.safety_flag = "safe"
    # 安全答案直接使用原始答案
    state.safe_answer = state.raw_answer
    # 返回更新后的状态
    return state


# ---------------------------------------------------------------------------
# 5. Response formatting (updated for multi-agent references)
# 5. 响应格式化节点（支持多智能体引用的更新版本）
# ---------------------------------------------------------------------------

# 定义 format_response_node 函数：将安全答案与引用信息、免责声明组合为最终的用户可见响应
def format_response_node(state: MedAgentState) -> MedAgentState:
    """Format the final response with references and disclaimer."""  # 格式化最终响应，包含引用和免责声明
    # 从安全服务获取标准的免责声明文本
    disclaimer = safety_service.get_disclaimer()

    # 如果安全标记为高风险，直接返回安全服务的标准回复，不附加其他信息
    if state.safety_flag == "high_risk":
        state.final_response = state.safe_answer
    # 如果安全标记为越界警告，直接返回带警告声明的安全答案
    elif state.safety_flag == "boundary_warning":
        state.final_response = state.safe_answer
    else:
        # 正常情况：构建引用信息部分
        references_text = ""
        # 如果存在子答案（各知识库的回答）
        if state.sub_answers:
            ref_lines = []
            # 遍历每个子答案，收集有贡献的知识库信息
            for sa in state.sub_answers:
                # 如果该知识库贡献了相关文本块（chunk_count > 0）
                if sa.get("chunk_count", 0) > 0:
                    # 格式化引用行：知识库名称 + 贡献段落数
                    ref_lines.append(f"- **{sa['kb_name']}**: 贡献了 {sa['chunk_count']} 条相关段落")
            if ref_lines:
                # 将引用行组合成文本块
                references_text = "\n\n**各知识库贡献:**\n" + "\n".join(ref_lines)

        # 判断是否所有知识库都没有贡献相关信息
        if not state.sub_answers or all(sa.get("chunk_count", 0) == 0 for sa in state.sub_answers):
            # 如果没有任何相关的知识库文档，添加说明性文字
            no_context_msg = (
                "\n\n**Note:** No relevant documents were found in the knowledge base for this question. "
                "The answer above is based on general knowledge and may not be specific to your situation."
                # 提示：未在知识库中找到与问题相关的文档，以上回答基于通用知识
            )
            # 最终响应 = 安全答案 + 无上下文提示 + 分隔线 + 免责声明
            state.final_response = state.safe_answer + no_context_msg + "\n\n---\n" + disclaimer
        else:
            # 有知识库贡献信息：最终响应 = 安全答案 + 知识库贡献列表 + 分隔线 + 免责声明
            state.final_response = state.safe_answer + references_text + "\n---\n" + disclaimer

    # 返回更新了最终响应的状态对象
    return state
