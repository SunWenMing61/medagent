# 导入类型注解：Dict（字典）、List（列表）、Optional（可选类型）、Generator（生成器）
from typing import Dict, List, Optional, Generator

# 导入 MedAgentState 状态类，用于在工作流各节点之间传递和共享上下文数据
from app.graphs.graph_state import MedAgentState
# 导入工作流五个阶段的节点处理函数
from app.graphs.nodes import (
    classify_question_node,             # 节点1：LLM 问题分类节点，判断问题属于 medical_qa / drug_qa / health_consult / paper_qa
    sub_agent_retrieve_node,            # 节点2：子智能体检索节点，按知识库独立执行向量检索
    sub_agent_generate_and_aggregate,    # 节点3：子智能体生成 + 主聚合器节点，并行生成各知识库答案后合成最终回答
    safety_check_node,                  # 节点4：安全检查节点，检测回答中是否包含越界或高风险内容
    format_response_node,               # 节点5：响应格式化节点，按知识库引用信息整理最终输出格式
)


# 定义 MedAgentWorkflow 类，编排多智能体医疗问答的完整工作流执行流水线
class MedAgentWorkflow:
    """
    MedAgent multi-agent workflow orchestrator.  # MedAgent 多智能体工作流编排器

    Pipeline:  # 工作流执行流水线：
      1. Classify question (or skip if force_type is set)  # 1. 对用户问题进行 LLM 分类（若设置了 force_type 则直接跳过）
      2. Per-KB retrieval — each KB searched independently  # 2. 按知识库独立检索——每个知识库单独执行向量搜索
      3. Per-KB sub-agent generation (parallel) + main aggregator  # 3. 各知识库子智能体并行生成回答 + 主聚合器合成统一回答
      4. Safety check  # 4. 对生成的答案进行安全边界检查
      5. Format response with per-KB references  # 5. 格式化最终响应，附上各知识库的引用信息
    """

    # 初始化方法，目前无需要初始化的实例属性
    def __init__(self):
        pass  # 无需额外初始化逻辑

    # 执行完整的端到端多智能体工作流，接收用户输入及配置参数，返回包含最终回答和引用的字典
    def run(
        self,
        question: str,                    # 用户提交的原始问题文本
        user_id: int = 0,                # 用户唯一标识（可选，默认 0）
        session_id: int = 0,             # 对话会话唯一标识（可选，默认 0）
        kb_ids: Optional[List[int]] = None,  # 需要检索的知识库 ID 列表（可选，默认 None 表示无知识库）
        kb_name_map: Optional[Dict[int, str]] = None,  # 知识库 ID 到显示名称的映射字典（可选）
        history_messages: Optional[List[dict]] = None,  # 历史对话消息列表，用于多轮对话上下文理解（可选）
        force_type: Optional[str] = None,  # 强制指定问题类型，若提供则跳过 LLM 分类步骤（可选）
        attachments: Optional[List[dict]] = None,  # 用户上传的附件列表，支持图片和文档类型（可选）
        web_search_enabled: bool = False,  # 是否启用网络搜索增强（默认关闭，启用后检索时额外搜索网络）
        deep_thinking_enabled: bool = False,  # 是否启用深度思考模式（默认关闭，启用后在回答前先生成逐步推理）
    ) -> dict:
        """
        Run the full multi-agent workflow.  # 运行完整的多智能体工作流

        Args:  # 参数说明：
            question: User's question  # 用户提出的问题
            user_id: User ID  # 用户的唯一标识
            session_id: Chat session ID  # 聊天会话的标识
            kb_ids: Knowledge base IDs to search  # 要检索的知识库 ID 列表
            kb_name_map: Mapping from kb_id to human-readable name  # kb_id 到可读名称的映射
            history_messages: Previous chat messages for context  # 历史聊天消息，提供对话上下文
            force_type: Force question type (skip classification)  # 强制问题类型（跳过 LLM 分类环节）
            attachments: Optional list of file attachments (images/docs)  # 可选的上传附件列表（图片/文档）
            web_search_enabled: Whether to augment with web search results  # 是否用网络搜索结果增强回答质量
            deep_thinking_enabled: Whether to generate step-by-step reasoning before answer  # 是否在回答前生成逐步推理过程

        Returns:  # 返回值说明：
            Dict with final_response, references, safety_flag  # 包含最终回答文本、引用来源列表和安全标记的字典
        """
        # 创建 MedAgentState 状态实例，用传入参数初始化各字段
        state = MedAgentState(
            question=question,                          # 用户问题
            user_id=user_id,                            # 用户 ID
            session_id=session_id,                      # 会话 ID
            kb_ids=kb_ids or [],                        # 知识库 ID 列表（None 时使用空列表）
            kb_name_map=kb_name_map or {},              # 知识库名称映射（None 时使用空字典）
            history_messages=history_messages or [],    # 历史消息列表（None 时使用空列表）
            attachments=attachments or [],              # 附件列表（None 时使用空列表）
            web_search_enabled=web_search_enabled,      # 网络搜索启用标志
            deep_thinking_enabled=deep_thinking_enabled,  # 深度思考启用标志
        )

        # ---- 第 1 步：问题分类 ----
        # 如果调用者提供了 force_type 参数，则直接使用该类型，跳过 LLM 分类调用
        if force_type:
            # 直接使用强制指定的类型值
            state.question_type = force_type
        else:
            # 否则，调用分类节点，由 LLM 对问题进行分类
            state = self._run_node(classify_question_node, state, "classify")

        # ---- 第 2 步：按知识库独立检索 ----
        # 为每个知识库分别执行向量检索，结果存入 per_kb_chunks 和 references
        state = self._run_node(sub_agent_retrieve_node, state, "retrieve")

        # ---- 第 3 步：子智能体生成 + 主聚合器合成 ----
        # 先并行触发各知识库子智能体独立生成回答，再由主聚合器 LLM 综合所有子答案
        state = self._run_node(sub_agent_generate_and_aggregate, state, "generate")

        # ---- 第 4 步：安全检查 ----
        # 对聚合后的答案进行安全合规检查，识别越界陈述和高风险内容
        state = self._run_node(safety_check_node, state, "safety")

        # ---- 第 5 步：格式化最终响应 ----
        # 将安全答案与引用信息、免责声明组装成最终的用户可见响应
        state = self._run_node(format_response_node, state, "format")

        # 将 MedAgentState 对象转换为字典后返回给调用者
        return state.to_dict()

    # 执行单个工作流节点函数，并包裹统一的异常处理逻辑，防止单个节点崩溃导致整个工作流中断
    def _run_node(self, node_func, state: MedAgentState, node_name: str) -> MedAgentState:
        """Execute a single node with error handling."""  # 执行单个节点并统一处理异常
        try:
            # 调用节点函数，传入当前状态对象，接收处理后的新状态
            return node_func(state)
        except Exception as e:  # 捕获节点执行期间的所有异常
            # 设置安全标记为 "error_{节点名称}"，标识工作流在哪个阶段出错
            state.safety_flag = f"error_{node_name}"
            # 生成用户友好的错误提示信息作为最终响应
            state.final_response = (
                f"I encountered an error during the {node_name} step. "  # 在 {节点名称} 阶段遇到了错误
                f"Please try again or contact support. Error: {str(e)}"  # 请重试或联系技术支持。错误详情：{异常信息}
            )
            # 返回已设置错误状态的状态对象，使工作流能继续返回而不崩溃
            return state
