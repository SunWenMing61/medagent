# 从 FastAPI 导入 APIRouter 类，用于创建路由分组
from fastapi import APIRouter

# 从各个 API 模块导入子路由，用于挂载到主路由下
from app.api.v1 import auth, users, knowledge_base, documents, chat, feedback, admin, tasks, graph, agent_runs, tooling, memory, retrieval_debug, evaluation

# 创建主路由实例，所有 API 路径以 /api 为前缀
router = APIRouter(prefix="/api")

# 挂载认证相关的路由，前缀为 /api/auth，在 Swagger 文档中归类为 "Auth"
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
# 挂载用户管理相关的路由，前缀为 /api/users，归类为 "Users"
router.include_router(users.router, prefix="/users", tags=["Users"])
# 挂载知识库管理相关的路由，前缀为 /api/kb，归类为 "Knowledge Base"
router.include_router(knowledge_base.router, prefix="/kb", tags=["Knowledge Base"])
# 挂载文档管理相关的路由，前缀为 /api/documents，归类为 "Documents"
router.include_router(documents.router, prefix="/documents", tags=["Documents"])
# 挂载聊天相关的路由，前缀为 /api/chat，归类为 "Chat"
router.include_router(chat.router, prefix="/chat", tags=["Chat"])
# 挂载反馈相关的路由，前缀为 /api/feedback，归类为 "Feedback"
router.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])
# 挂载管理员功能相关的路由，前缀为 /api/admin，归类为 "Admin"
router.include_router(admin.router, prefix="/admin", tags=["Admin"])
# 挂载 GraphRAG 图检索增强生成相关的路由，前缀为 /api/graph，归类为 "GraphRAG"
router.include_router(graph.router, prefix="/graph", tags=["GraphRAG"])
# 挂载后台任务管理相关的路由，归类为 "Tasks"
router.include_router(tasks.router, tags=["Tasks"])
router.include_router(agent_runs.router, prefix="/agent-runs", tags=["Agent Runs"])
router.include_router(tooling.router, prefix="/admin/tools", tags=["Tool Governance"])
router.include_router(memory.router, prefix="/memory", tags=["Agent Memory"])
router.include_router(memory.session_router, prefix="/sessions", tags=["Session Memory"])
router.include_router(retrieval_debug.router, prefix="/retrieval", tags=["Retrieval Observability"])
router.include_router(evaluation.router, prefix="/evaluation", tags=["AI Evaluation"])
