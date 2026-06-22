# 导入类型注解：Dict（字典）、List（列表）、Optional（可选类型）、Any（任意类型）
from typing import Dict, List, Optional, Any


# 定义 MedAgentState 类，用于管理多智能体医疗问答工作流的全部状态数据
class MedAgentState:
    """State object for the MedAgent multi-agent workflow."""  # MedAgent 多智能体工作流的状态对象

    # 初始化方法，定义工作流中所有可能的状态字段及其默认值
    def __init__(
        self,
        question: str = "",                # 用户提出的原始问题字符串
        user_id: int = 0,                  # 用户的唯一标识编号
        session_id: int = 0,               # 当前对话会话的唯一标识编号
        kb_ids: Optional[List[int]] = None,  # 需要查询的知识库 ID 列表（可选，默认 None）
        kb_name_map: Optional[Dict[int, str]] = None,  # 知识库 ID 到人类可读名称的映射字典（可选）
        history_messages: Optional[List[dict]] = None,  # 历史对话消息列表，用于维持多轮对话上下文（可选）
        question_type: str = "unknown",     # 问题分类结果，可选值：medical_qa / drug_qa / health_consult / paper_qa / unknown
        retrieved_chunks: Optional[List[dict]] = None,  # 从知识库向量检索中返回的相关文本块列表（可选）
        references: Optional[List[dict]] = None,  # 最终回答中需要引用的来源信息列表，包含文档ID、知识库、内容片段等（可选）
        per_kb_chunks: Optional[Dict[int, List[dict]]] = None,  # 按知识库 ID 分组的检索结果，键为 kb_id，值为该知识库的文本块列表（可选）
        sub_answers: Optional[List[dict]] = None,  # 各子智能体（每个知识库一个）独立生成的答案字典列表（可选）
        raw_answer: str = "",               # 聚合器 LLM 综合各子答案后生成的原始回答文本
        safe_answer: str = "",              # 经过安全节点检查和处理后的安全版本回答
        safety_flag: Optional[str] = None,  # 安全状态标记：None=未检查 / safe=安全 / boundary_warning=越界警告 / high_risk=高风险 / error_xxx=节点错误
        final_response: str = "",           # 经过格式化后的最终响应文本，直接返回给用户
        attachments: Optional[List[dict]] = None,  # 用户上传的附件列表，支持图片（image）和文档（document）类型（可选）
        web_search_enabled: bool = False,    # 是否启用网络搜索增强功能，启用后将在检索阶段额外查询网络（布尔值）
        web_search_results: Optional[List[dict]] = None,  # 网络搜索引擎返回的结果列表，包含标题、摘要、URL 等（可选）
        deep_thinking_enabled: bool = False,  # 是否启用深度思考模式，启用后将在回答前生成逐步推理过程（布尔值）
        thinking_content: str = "",          # 深度思考模式生成的推理链文本，包含问题分析、信息评估、推理过程和回答规划
    ):
        # 存储用户原始问题字符串
        self.question = question
        # 存储用户的唯一标识编号
        self.user_id = user_id
        # 存储当前会话的唯一标识编号
        self.session_id = session_id
        # 存储需要查询的知识库 ID 列表，若传入 None 则初始化为空列表
        self.kb_ids = kb_ids or []
        # 存储知识库 ID 到名称的映射字典，若传入 None 则初始化为空字典
        self.kb_name_map = kb_name_map or {}
        # 存储历史对话消息列表，若传入 None 则初始化为空列表
        self.history_messages = history_messages or []
        # 存储问题分类结果类型字符串
        self.question_type = question_type
        # 存储从知识库检索到的文本块列表，若传入 None 则初始化为空列表
        self.retrieved_chunks = retrieved_chunks or []
        # 存储引用来源信息列表，若传入 None 则初始化为空列表
        self.references = references or []
        # 存储按知识库 ID 分组的检索结果字典，若传入 None 则初始化为空字典
        self.per_kb_chunks = per_kb_chunks or {}
        # 存储子智能体生成的答案列表，若传入 None 则初始化为空列表
        self.sub_answers = sub_answers or []
        # 存储原始的回答文本
        self.raw_answer = raw_answer
        # 存储经过安全检查后的安全回答文本
        self.safe_answer = safe_answer
        # 存储安全检查的状态标记
        self.safety_flag = safety_flag
        # 存储最终要返回给用户的格式化响应文本
        self.final_response = final_response
        # 存储附件列表，若传入 None 则初始化为空列表
        self.attachments = attachments or []
        # 存储网络搜索启用状态
        self.web_search_enabled = web_search_enabled
        # 存储网络搜索结果列表，若传入 None 则初始化为空列表
        self.web_search_results = web_search_results or []
        # 存储深度思考启用状态
        self.deep_thinking_enabled = deep_thinking_enabled
        # 存储深度思考生成的推理过程内容
        self.thinking_content = thinking_content

    # 将状态对象的核心字段序列化为 Python 字典，用于 API 响应返回
    def to_dict(self) -> dict:
        return {
            "question": self.question,              # 用户原始问题
            "user_id": self.user_id,                # 用户 ID
            "session_id": self.session_id,           # 会话 ID
            "kb_ids": self.kb_ids,                  # 查询的知识库 ID 列表
            "kb_name_map": self.kb_name_map,         # 知识库名称映射字典
            "question_type": self.question_type,     # 问题分类类型
            "retrieved_chunks": self.retrieved_chunks,  # 检索到的文本块列表
            "references": self.references,           # 引用来源列表
            "sub_answers": self.sub_answers,         # 子智能体生成的答案列表
            "raw_answer": self.raw_answer,           # 原始回答文本
            "safe_answer": self.safe_answer,         # 安全版本回答
            "safety_flag": self.safety_flag,         # 安全状态标记
            "final_response": self.final_response,   # 最终格式化响应
        }

    # 根据知识库 ID 解析其人类可读名称，若映射中不存在则返回带 ID 的通用标签
    def get_kb_name(self, kb_id: int) -> str:
        """Resolve KB name from kb_name_map, falling back to a generic label."""  # 从 kb_name_map 映射中解析知识库名称，若未找到则使用通用标签
        # 在 kb_name_map 字典中查找 kb_id，若不存在则返回 "知识库 #{kb_id}" 作为默认显示名称
        return self.kb_name_map.get(kb_id, f"知识库 #{kb_id}")

    # （方法重复定义）根据知识库 ID 解析知识库名称，若映射中不存在则返回带 ID 的通用标签
    def get_kb_name(self, kb_id: int) -> str:
        """Resolve KB name from kb_name_map, falling back to a generic label."""  # 从 kb_name_map 映射中解析知识库名称，若未找到则使用通用标签
        # 在 kb_name_map 字典中查找 kb_id，若不存在则返回 "知识库 #{kb_id}" 作为默认显示名称
        return self.kb_name_map.get(kb_id, f"知识库 #{kb_id}")
