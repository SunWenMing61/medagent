<div align="center">
  <h1>🏥 MedAgent-QDS</h1>
  <p><em>Multi-Agent Full-Stack Medical QA Platform — RAG + GraphRAG + Knowledge Graph</em></p>
</div>

---

## 📋 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [架构亮点](#架构亮点)
- [项目结构](#项目结构)
- [快速启动](#快速启动)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [RAG 评估体系](#rag-评估体系)
- [医学安全边界](#医学安全边界)
- [部署](#部署)
- [开发与测试](#开发与测试)

---

## 项目概述

MedAgent 是一个面向医疗场景的 **RAG（检索增强生成）+ GraphRAG（知识图谱增强检索）知识问答平台**。它允许用户上传医学文档，通过 多Agent 协同 + 向量检索 + 语义精排 + 知识图谱 的架构实现精准的医学知识问答与健康咨询辅助。

**核心架构**：用户提问 → 向量检索（PostgreSQL + pgvector）→ **Cross-Encoder 精排** → **知识图谱上下文增强** → LLM 生成回答 → 安全合规过滤

### 适用场景

- 📄 基于私有医学文档的问答
- 💬 多轮医学健康咨询对话
- 🏛️ 医疗机构内部知识库管理
- 🧠 医学知识图谱构建与推理

---

## 核心功能

| 模块 | 功能 |
|------|------|
| **文档管理** | 上传 PDF/DOCX/TXT/MD，自动解析、**智能语义分块**、向量化；在线预览；批量操作；文档统计 |
| **PDF 清洗入库** | 逐页分类、OCR/混合提取、医学文本保真清洗、跨页表格、Raw/Clean/Chunk 追踪，清洗后直接向量化 |
| **知识库管理** | 多知识库隔离，支持公开/私有可见性 |
| **智能问答** | 基于 RAG + GraphRAG 的多轮对话，流式输出，参考资料溯源，**LaTeX 公式渲染** |
| **语义精排** | **Cross-Encoder 重排序管道**（BGE Reranker / LLM 降级），显著提升检索精度 |
| **知识图谱** | **GraphRAG 引擎**：自动抽取医学实体（疾病/药物/症状），构建关系图谱，图+向量混合检索 |
| **深度思考** | 流式展示 AI 推理过程，支持深度思考模式 |
| **多模态问答** | 支持图片/PDF/DOCX 附件上传，**剪贴板粘贴截图**，**拖拽上传**，多模态 LLM 分析 |
| **消息编辑** | 用户可编辑自己的消息，支持重新提问 |
| **会话管理** | 历史会话保存与回溯，按时间分组（近三天/近一周/近30天），满意度反馈 |
| **管理系统** | 用户管理、模型参数配置、系统监控、管理概览 30 秒自动轮询刷新 |
| **工具治理** | 注册表、Agent/scope 策略、服务端身份注入、超时重试、缓存、熔断、审计与健康监控 |
| **后台任务** | RQ 异步处理文档向量化、知识源同步，**WebSocket 实时进度推送**，**前端任务状态监控** |
| **主题定制** | 自定义背景图片，支持亮色/暗色模式，遮罩透明度可调 |
| **速率限制** | 内存滑动窗口限速器（Auth: 10次/分，Chat: 30次/分），防止 API 滥用 |
| **Embedding 缓存** | LRU 缓存嵌入向量结果，减少重复 API 调用 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 |
| **关系数据库** | MySQL 8.0（用户、知识库、文档、会话、反馈等业务数据） |
| **向量数据库** | PostgreSQL 16 + pgvector（文档块嵌入向量检索） |
| **缓存 & 队列** | Redis 7, RQ (Redis Queue) |
| **AI / LLM** | LangChain, LangGraph, OpenAI 兼容 API（支持 DeepSeek、Qwen、本地 LLM） |
| **Embedding** | text-embedding-3-small 等向量模型 |
| **语义重排序** | **BAAI/bge-reranker-v2-m3**（Cross-Encoder）+ LLM 降级方案 |
| **前端** | React 18, TypeScript, Ant Design 5, **KaTeX**（LaTeX 公式渲染） |
| **容器化** | Docker, Docker Compose |
| **编排** | Kubernetes（含完整 YAML 配置） |
| **文档解析** | PyMuPDF (PDF), python-docx (DOCX), BeautifulSoup (HTML) |
| **工作流** | **LangGraph** 多 Agent 工作流编排 |
| **评估框架** | **内部 RAG 评估系统**（Precision/Recall/F1/MRR/NDCG/Faithfulness） |

---

## 架构亮点

### 受控 Supervisor 多 Agent（feature flag）

新工作流将规则优先输入安全、分诊、查询理解、并行检索、证据核验、引用绑定答案、输出安全和人工审核拆分为独立子图。只有 Supervisor 能选择下一节点；会话记忆不能作为医学证据；急症直接短路；所有循环、工具和总时长都有硬上限。详见 [架构说明](docs/MULTI_AGENT_ARCHITECTURE.md)、[生命周期 API](docs/AGENT_API.md)、[迁移指南](docs/MULTI_AGENT_MIGRATION_GUIDE.md) 和 [评测说明](docs/MULTI_AGENT_EVALUATION.md)。

PDF 清洗与工具体系的实现、直接向量入库流程和迁移说明见 [PDF 清洗与工具治理架构](docs/PDF_CLEANING_AND_TOOLING_ARCHITECTURE.md)；本地实际运行数值与基线对比见 [PDF/工具评测](docs/PDF_TOOLING_EVALUATION.md)。

Agent Memory 与检索 v2 将 Session/Semantic/Episodic/Procedural Memory、持久化 checkpoint 和医学证据通道隔离，并加入 Dense+Sparse+Exact、约束校验、冲突识别和脱敏追踪。详见 [架构说明](docs/AGENT_MEMORY_RETRIEVAL_V2.md)、[迁移指南](docs/AGENT_MEMORY_RETRIEVAL_MIGRATION.md) 与 [离线评测](docs/AGENT_MEMORY_RETRIEVAL_EVALUATION.md)。

### 🧠 多 Agent 工作流

```
用户问题 → 问题分类节点 → 多路知识库检索 → 子Agent并行生成 → Rerank精排
            ↓                                                  ↓
        medical_qa / drug_qa / health_consult / paper_qa     BGE Reranker
            ↓                                                  ↓
        GraphRAG 实体抽取 ←─── 向量检索结果 ←─── Cross-Encoder 重排序
            ↓
        聚合器 Agent → 安全检查 → 格式化响应 → 流式输出
```

### 🔀 GraphRAG — 图检索增强生成

```
文档/问答文本
    ↓
LLM 实体抽取（疾病/药物/症状/治疗/检查）
    ↓
内存知识图谱 + MySQL 持久化
    ↓
混合检索：向量搜索 + 图遍历（BFS）
    ↓
上下文融合 → LLM 生成
```

### 📊 异步任务系统

```
用户请求 → 任务注册（TaskManager）
              ↓
        Redis Hash 存储 + Pub/Sub 通知
              ↓
        WebSocket 实时推送进度
              ↓
        前端 TaskStatus 页面（3秒轮询）
```

---

## 项目结构

```
medagent/
├── requirements.txt              # Python 依赖
│
├── medagent-backend/             # FastAPI 后端
│   ├── app/
│   │   ├── main.py               # 应用入口、生命周期、路由注册（含 WebSocket）
│   │   ├── core/
│   │   │   ├── config.py         # 配置管理（Pydantic Settings）
│   │   │   ├── security.py       # JWT、密码哈希
│   │   │   └── dependencies.py   # 依赖注入（鉴权、数据库、速率限制）
│   │   ├── db/
│   │   │   ├── base.py           # 声明式基类（MySQL + PostgreSQL）
│   │   │   ├── session.py        # 数据库会话工厂
│   │   │   └── init_db.py        # 初始化脚本
│   │   ├── models/               # SQLAlchemy 数据模型
│   │   │   ├── user.py           # 用户
│   │   │   ├── knowledge_base.py # 知识库
│   │   │   ├── document.py       # 文档
│   │   │   ├── document_chunk.py # 文档块（pgvector 向量）
│   │   │   ├── knowledge_graph.py # ⭐ 知识图谱实体 & 关系
│   │   │   ├── chat.py           # 会话 & 消息
│   │   │   ├── feedback.py       # 反馈
│   │   │   ├── model_config.py   # 模型配置
│   │   │   └── system_log.py     # 系统日志
│   │   ├── schemas/              # Pydantic 请求/响应模型
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── ...
│   │   │   ├── graph.py          # ⭐ GraphRAG 请求/响应
│   │   │   └── task.py           # ⭐ 后台任务状态
│   │   ├── api/v1/               # API 路由
│   │   │   ├── auth.py           # 登录、注册（速率限制）
│   │   │   ├── users.py          # 用户信息
│   │   │   ├── knowledge_base.py # 知识库 CRUD
│   │   │   ├── documents.py      # 文档上传/列表/删除/预览
│   │   │   ├── chat.py           # 问答对话（RAG + 流式）
│   │   │   ├── feedback.py       # 反馈提交
│   │   │   ├── admin.py          # 管理后台接口
│   │   │   ├── graph.py          # ⭐ GraphRAG 端点（实体抽取/检索）
│   │   │   ├── tasks.py          # ⭐ 后台任务 REST API
│   │   │   └── ws.py             # ⭐ WebSocket 实时任务进度
│   │   ├── services/             # 业务逻辑
│   │   │   ├── retrieval_service.py # Dense + Sparse + RRF + Rerank 混合检索
│   │   │   ├── rerank_service.py # ⭐ Cross-Encoder 精排服务
│   │   │   ├── graph_service.py  # ⭐ GraphRAG 图检索增强服务
│   │   │   ├── task_manager.py   # ⭐ 后台任务管理器（Redis + 内存）
│   │   │   ├── safety_service.py # 医学安全审查
│   │   ├── graphs/               # 多 Agent 工作流
│   │   │   ├── root_graph.py     # 唯一受控 Supervisor 工作流
│   │   │   ├── retrieval_subgraph.py # 混合检索子图
│   │   │   └── graph_state.py    # 状态定义
│   │   ├── evaluation/           # ⭐ RAG 评估框架
│   │   │   ├── __init__.py       # 模块入口
│   │   │   ├── metrics.py        # 指标计算（Precision/Recall/F1/MRR/NDCG）
│   │   │   └── failure_taxonomy.py # 固定回归评测与故障归因
│   │   ├── tasks/                # RQ 后台任务
│   │   │   └── document_tasks.py # ⭐ 文档处理（含 5 步进度报告）
│   │   ├── utils/
│   │   │   ├── text_splitter.py  # ⭐ 智能分块（语义边界 + RecursiveCharacter）
│   │   │   ├── file_utils.py     # 文件文本提取
│   │   │   └── web_search.py     # 网络搜索
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 自动化测试
│   │   ├── test_api.py           # API 端点测试
│   │   ├── test_utils.py         # 工具函数测试
│   │   ├── test_hybrid_retrieval.py # 混合检索测试
│   │   └── test_controlled_multi_agent.py # 受控多 Agent 测试
│   ├── k8s/                      # Kubernetes 部署文件
│   ├── worker.py                 # RQ Worker 入口
│   ├── Dockerfile                # 后端容器构建
│   └── docker-compose.yml        # 本地编排
│
└── medagent-frontend/            # React 前端
    ├── src/
    │   ├── App.tsx               # 根组件（布局、路由、背景图、⭐ 知识图谱 / 任务页）
    │   ├── pages/
    │   │   ├── Login.tsx / Register.tsx
    │   │   ├── Dashboard.tsx
    │   │   ├── MedicalQA.tsx
    │   │   ├── HealthConsult.tsx
    │   │   ├── DocumentManagement.tsx
    │   │   ├── KBManagement.tsx
    │   │   ├── TaskStatus.tsx    # ⭐ 后台任务状态监控（进度条 + WebSocket）
    │   │   ├── AdminDashboard.tsx
    │   │   ├── AdminUsers.tsx
    │   │   ├── AdminConfig.tsx
    │   │   └── AdminFeedback.tsx
    │   ├── components/
    │   │   ├── ChatInterface.tsx  # ⭐ 消息编辑 / 剪贴板粘贴 / 引用高亮
    │   │   ├── EnhancedMarkdown.tsx # ⭐ LaTeX + Markdown 增强渲染器
    │   │   ├── FileDropZone.tsx  # ⭐ 拖拽上传 + 剪贴板粘贴组件
    │   │   └── ThemeSettings.tsx # 主题/背景图片设置
    │   ├── contexts/ThemeContext.tsx
    │   └── services/api.ts       # API 客户端（Axios）
    ├── package.json
    ├── Dockerfile
    └── .env.example
```

> ⭐ 标记本次迭代新增或增强的模块

---

## 快速启动

### 📋 完整启动流程（Windows / macOS / Linux）

本指南以 **Windows PowerShell** 为例，macOS/Linux 的命令同理。

#### 0️⃣ 前置准备

确保已安装以下服务并处于运行状态：

| 依赖 | 用途 | 验证命令 |
|------|------|---------|
| **MySQL 8.0+** | 业务数据库 | `mysql -u root -e "SELECT 1"` |
| **PostgreSQL 16+** | 向量数据库（需 pgvector） | `psql -U postgres -c "SELECT 1"` |
| **Redis 7+** | 缓存与任务队列 | `redis-cli ping` |
| **Python 3.11+** | 后端运行环境 | `python --version` |
| **Node.js 18+** | 前端运行环境 | `node --version` |

初次使用需要创建数据库（以 MySQL + PostgreSQL 为例）：

```bash
# Windows PowerShell: 创建 MySQL 数据库
mysql -u root -p
CREATE DATABASE medagent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'medagent'@'localhost' IDENTIFIED BY 'medagent123';
GRANT ALL PRIVILEGES ON medagent.* TO 'medagent'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# Windows PowerShell: 创建 PostgreSQL 数据库
psql -U postgres
CREATE DATABASE medagent;
CREATE USER medagent WITH PASSWORD 'medagent123';
GRANT ALL PRIVILEGES ON DATABASE medagent TO medagent;
\c medagent
CREATE EXTENSION IF NOT EXISTS vector;
EXIT;
```

#### 1️⃣ 后端

```bash
# ==== 1. 进入后端目录 ====
cd medagent-backend

# ==== 2. 创建并激活 Python 虚拟环境 ====
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

# ==== 3. 安装 Python 依赖 ====
pip install -r requirements.txt

# ==== 4. 配置环境变量 ====
cp .env.example .env
# ⚠️ 编辑 .env 文件，填入 LLM_API_KEY 和 EMBEDDING_API_KEY（见上方配置说明）

# ==== 5. 初始化数据库（创建表结构）====
python -c "from app.db.init_db import init_database; init_database()"

# ==== 6. 启动后端服务（新终端）====
# Windows PowerShell:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Linux / macOS:
# uvicorn app.main:app --reload --port 8000

# 后端运行在: http://localhost:8000
# API 文档:   http://localhost:8000/docs
```

#### 2️⃣ RQ Worker（文档处理）

```powershell
# 新开一个终端
cd medagent-backend
.venv\Scripts\activate
python worker.py
# 看到 "*** Listening on default..." 表示启动成功
```

#### 3️⃣ 前端

```powershell
# 新开一个终端
cd medagent-frontend

# 安装前端依赖（首次启动需要）
npm install

# 配置后端 API 地址（默认通过 Vite 代理到 localhost:8000）
copy .env.example .env

# 启动开发服务器（默认端口 3000，被占用则自动递增）
npm start

# ⚠️ 如果报错 "vite 不是内部或外部命令"（Windows 常见问题）:
node ./node_modules/vite/bin/vite.js --host 0.0.0.0

# 前端运行在: http://localhost:3000（3000 被占则顺延到 3001/3002...）
```

#### 4️⃣ 验证启动

```powershell
# 终端 1 - 后端 API（验证）
curl http://localhost:8000/health
# 返回: {"status":"ok","service":"MedAgent","version":"1.0.0"}

# 终端 2 - RQ Worker（看输出）
# 应显示: *** Listening on default...

# 浏览器打开（根据实际端口）:
# http://localhost:3000  或
# http://localhost:3001  或
# http://localhost:3002
# 看到登录页即表示成功
```

### 常见问题排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `vite 不是内部或外部命令` | Windows PowerShell PATH 问题 | 用 `node ./node_modules/vite/bin/vite.js --host 0.0.0.0` 代替 `npm start` |
| `ModuleNotFoundError: No module named 'app'` | 虚拟环境未激活 | 运行 `.venv\Scripts\activate` |
| `Connection refused: mysql` | MySQL 服务未启动 | `net start mysql` |
| `pgvector extension not found` | PostgreSQL 未安装 pgvector | `psql -U postgres -c "CREATE EXTENSION vector"` |
| `LLM_API_KEY not configured` | `.env` 未正确配置 | 检查 `.env` 文件中的 API Key 是否已填写 |
| `package.json JSON parse error` | JSON 格式损坏 | 检查 `package.json` 中的注释是否合规 |

---

## 配置说明

### 后端环境变量（`.env`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API 密钥（OpenAI/DeepSeek 等） | — |
| `LLM_API_BASE` | LLM API 地址 | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型名 | `gpt-4o-mini` |
| `EMBEDDING_API_KEY` | Embedding API 密钥 | — |
| `EMBEDDING_API_BASE` | Embedding API 地址 | `https://api.openai.com/v1` |
| `EMBEDDING_MODEL` | Embedding 模型名 | `text-embedding-3-small` |
| `DATABASE_URL` | PostgreSQL 连接串（向量存储） | `postgresql://medagent:your-password@localhost:5432/medagent` |
| `MYSQL_DATABASE_URL` | MySQL 连接串（业务数据） | `mysql+pymysql://medagent:your-password@localhost:3306/medagent` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT 签名密钥（**生产环境务必修改默认值**） | `change-this-to-a-secure-random-key` |
| `RETRIEVAL_CANDIDATE_K` | Dense/Sparse 各路候选召回上限 | `30` |
| `EVIDENCE_MAX_CHUNKS` | 动态截断允许的证据数上限 | `8` |
| `SIMILARITY_THRESHOLD` | Dense 召回相似度阈值 | `0.5` |

> 支持任何 OpenAI 兼容的 API 提供商（DeepSeek、Qwen、vLLM、Ollama 等），
> 只需修改 `LLM_API_BASE` 和 `LLM_MODEL` 即可。

### 前端环境变量（`medagent-frontend/.env`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REACT_APP_API_BASE_URL` | 后端 API 地址 | `http://localhost:8000/api` |

---

## API 文档

启动后端后访问：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录（速率限制：10次/分） |
| POST | `/api/auth/register` | 用户注册（速率限制：10次/分） |
| POST | `/api/auth/refresh` | 刷新 Token |
| GET | `/api/kb` | 知识库列表 |
| POST | `/api/kb` | 创建知识库 |
| DELETE | `/api/kb/{id}` | 删除知识库 |
| GET | `/api/documents` | 文档列表 |
| POST | `/api/documents/upload` | 上传文档 |
| GET | `/api/documents/{id}/preview` | 文档预览 |
| POST | `/api/chat/ask` | 非流式问答 |
| POST | `/api/chat/ask/stream` | **流式问答（SSE）** |
| POST | `/api/chat/health` | 健康咨询（安全审查） |
| GET | `/api/chat/sessions` | 历史会话列表 |
| GET | `/api/chat/sessions/{id}` | 会话详情 |
| DELETE | `/api/chat/sessions/{id}` | 删除会话 |
| POST | `/api/feedback` | 提交反馈 |
| **GET** | **`/api/graph/kb/{kb_id}`** | **⭐ 获取知识图谱** |
| **GET** | **`/api/graph/search`** | **⭐ 图谱搜索** |
| **POST** | **`/api/graph/query`** | **⭐ 图+向量混合检索** |
| **GET** | **`/api/tasks`** | **⭐ 后台任务列表** |
| **DELETE** | **`/api/tasks/{task_id}`** | **⭐ 删除任务** |
| **WS** | **`/api/ws/tasks?token=`** | **⭐ WebSocket 实时任务进度** |
| GET | `/api/admin/stats` | 管理概览统计 |

---

## RAG 评估体系

新增的固定故障归因测试集可以在更换提示词、模型或检索策略后，分别统计
检索失败、回答幻觉、工具参数错误和任务未完成，并与相同数据集 SHA-256 下的
基线报告比较。详见 [固定测试集与回归评测](docs/FAILURE_REGRESSION_EVALUATION.md)。

MedAgent 内置了一套完整的 RAG 评估框架，支持离线评估和优化迭代。

### 评估指标

| 类别 | 指标 | 说明 |
|------|------|------|
| **检索质量** | `Precision@k` | 检索结果中相关文档的比例 |
| | `Recall@k` | 覆盖了多少比例的相关文档 |
| | `F1@k` | 精确率和召回率的调和平均 |
| | `MRR` | 第一个相关结果的排名倒数 |
| | `Hit Rate@k` | top-k 中是否至少命中一个相关文档 |
| | `NDCG@k` | 考虑排序位置和相关性等级的归一化指标 |
| **生成质量** | `Faithfulness` | 回答内容是否被检索到的上下文所支持 |
| | `Answer Relevancy` | 回答是否直接针对用户问题 |
| | `Answer Correctness` | 回答与标准答案的匹配程度 |
| **分类质量** | `Accuracy` | 问题分类的准确率 |
| | `Macro F1` | 各类别 F1 的宏平均 |

### 固定测试数据集

固定回归集位于 `medagent-backend/evals/datasets/failure_taxonomy_v1.jsonl`，区分检索失败、回答幻觉、工具参数错误和任务未完成。

### 运行评估

```bash
# 运行固定回归评估
cd medagent-backend
python evals/runners/run_failure_regression_evals.py \
  --dataset evals/datasets/failure_taxonomy_v1.jsonl \
  --run evals/runs/current_model_baseline_v1.jsonl
```

### 优化建议生成

评估报告会自动输出优化建议，例如：

```
🔧 分类器准确率 65.0% < 90%，建议增加训练数据或优化规则
🔧 Precision@5 = 53.3%，建议引入 Rerank 精排
🔧 Faithfulness = 50.0%，建议优化 Prompt 约束回答范围
```

---

## 医学安全边界

MedAgent 定位为 **医学知识辅助工具**，并非诊疗设备。

| ✅ 支持 | ❌ 不支持 |
|---------|-----------|
| 基于上传文档的 RAG 问答 | 疾病诊断 |
| 健康知识解释与科普 | 处方生成 |
| 就医前信息整理 | 停药/换药/剂量调整建议 |
| 药品说明书内容解释 | 替代医生诊断 |
| 医学文献检索辅助 | 急诊或危重症处理 |

> 系统内置安全审查服务（`safety_service.py`），对 LLM 输出进行合规过滤以避免生成不当医疗建议。
> 系统还配备 **内存滑动窗口速率限制器**，防止 API 滥用。

---

## 部署

### Docker Compose

```bash
cd medagent-backend
docker compose up -d --build
```

启动前必须设置 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`POSTGRES_PASSWORD`、`SECRET_KEY` 和 `EMBEDDING_API_KEY`。后端启动入口会依次运行 PostgreSQL/MySQL Alembic 迁移；迁移失败时服务不会带着旧 schema 继续运行。

启动的服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| `frontend` | 3000 | Nginx 静态文件服务 |
| `backend` | 仅容器网络 | FastAPI 应用（含 WebSocket） |
| `worker` | — | RQ Worker（文档处理） |
| `mysql` | 仅容器网络 | 关系数据库 |
| `postgres` | 仅容器网络 | 向量数据库 |
| `redis` | 仅容器网络 | 缓存与消息队列 |

### Kubernetes

```bash
cd medagent-backend/k8s
kubectl apply -f namespace.yaml
kubectl apply -f .
```

---

## 开发与测试

```bash
# 运行所有后端测试
cd medagent-backend
python -m pytest -q

# 运行特定测试模块
pytest tests/test_hybrid_retrieval.py -v     # 混合检索
pytest tests/test_controlled_multi_agent.py -v # 受控多 Agent
pytest tests/test_failure_regression_evaluation.py -v # 固定回归指标
pytest tests/test_api.py -v                  # API 端点测试

# 前端构建
cd medagent-frontend
npm run typecheck
npm run build
npm test -- --passWithNoTests
```

---

## 管理员初始化与运维文档

系统不再创建带默认密码的管理员。完成迁移后，在安全终端中运行：

```bash
python -m app.cli.create_admin --username your-admin --email admin@example.com
```

重构架构、威胁模型、迁移和故障恢复说明见 [`docs/`](docs/)；其中 [`OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) 给出了扫描 PDF、任务和检索故障的处置步骤。

---

## 许可证

[MIT](LICENSE)
