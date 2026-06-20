<div align="center">
  <h1>🏥 MedAgent-QDS</h1>
  <p><em>A Multi-Agent Full-Stack Medical Question Answering and Decision Support Platform Powered by a Medical Knowledge Base</em></p>
</div>

---

## 📋 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速启动](#快速启动)
  - [Docker Compose 一键部署](#1-docker-compose-一键部署)
  - [本地开发](#2-本地开发)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [在线知识源](#在线知识源)
- [医学安全边界](#医学安全边界)
- [部署](#部署)

---

## 项目概述

MedAgent 是一个面向医疗场景的 **RAG（检索增强生成）知识问答平台**。它允许用户上传医学文档或接入在线知识源，通过 LLM + 向量检索的架构实现精准的医学知识问答与健康咨询辅助。

**核心架构**：用户提问 → 向量检索（PostgreSQL + pgvector）→ 检索结果注入 Prompt → LLM 生成回答 → 安全合规过滤

### 适用场景

- 📄 基于私有医学文档的问答
- 🔗 在线知识源（PubMed、MSD Manual、FDA 药品标签）的知识检索
- 💬 多轮医学健康咨询对话
- 🏛️ 医疗机构内部知识库管理

---

## 核心功能

| 模块 | 功能 |
|------|------|
| **文档管理** | 上传 PDF/DOCX/TXT/MD，自动解析、分块、向量化；在线预览；批量操作；线上/线下文档分类统计 |
| **知识库管理** | 多知识库隔离，支持公开/私有可见性；内置全局对话历史知识库，自动记录所有对话并实时向量化 |
| **在线知识源** | 接入 PubMed、MSD Manual、FDA Drug Label 等权威医学来源，同步后自动纳入检索 |
| **智能问答** | 基于 RAG 的多轮对话，流式输出，参考资料溯源 |
| **健康咨询** | 基于 LangGraph 工作流的症状导诊，含安全审查节点 |
| **会话管理** | 历史会话保存与回溯，满意度反馈 |
| **管理系统** | 用户管理、模型参数配置、系统监控；管理概览 30 秒自动轮询刷新 |
| **后台任务** | RQ 异步处理文档向量化、知识源同步 |
| **主题定制** | 自定义背景图片，支持亮色/暗色模式，遮罩透明度可调 |

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
| **前端** | React 18, TypeScript, Ant Design 5 |
| **容器化** | Docker, Docker Compose |
| **编排** | Kubernetes（含完整 YAML 配置） |
| **文档解析** | PyMuPDF (PDF), python-docx (DOCX), BeautifulSoup (HTML) |

---

## 项目结构

```
medagent/
├── requirements.txt              # Python 依赖
│
├── medagent-backend/             # FastAPI 后端
│   ├── app/
│   │   ├── main.py               # 应用入口、生命周期、路由注册
│   │   ├── core/
│   │   │   ├── config.py         # 配置管理（Pydantic Settings）
│   │   │   ├── security.py       # JWT、密码哈希
│   │   │   └── dependencies.py   # 依赖注入（鉴权、数据库）
│   │   ├── db/
│   │   │   ├── base.py           # 声明式基类（MySQL + PostgreSQL）
│   │   │   ├── session.py        # 数据库会话工厂
│   │   │   └── init_db.py        # 初始化脚本
│   │   ├── models/               # SQLAlchemy 数据模型
│   │   │   ├── user.py           # 用户
│   │   │   ├── knowledge_base.py # 知识库
│   │   │   ├── document.py       # 文档
│   │   │   ├── document_chunk.py # 文档块（pgvector 向量）
│   │   │   ├── knowledge_source.py # 在线知识源
│   │   │   ├── chat.py           # 会话 & 消息
│   │   │   ├── feedback.py       # 反馈
│   │   │   ├── model_config.py   # 模型配置
│   │   │   └── system_log.py     # 系统日志
│   │   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── api/v1/               # API 路由
│   │   │   ├── auth.py           # 登录、注册、刷新 Token
│   │   │   ├── users.py          # 用户信息
│   │   │   ├── knowledge_base.py # 知识库 CRUD（含 chat_history 保护）
│   │   │   ├── documents.py      # 文档上传/列表/删除/预览
│   │   │   ├── sources.py        # 在线知识源管理
│   │   │   ├── chat.py           # 问答对话（RAG + 流式 + 对话历史自动存档）
│   │   │   ├── feedback.py       # 反馈提交
│   │   │   └── admin.py          # 管理后台接口（实时统计）
│   │   ├── services/             # 业务逻辑
│   │   │   ├── vector_service.py # 向量检索服务
│   │   │   ├── safety_service.py # 医学安全审查（LLM 输出合规过滤）
│   │   │   ├── source_service.py # 知识源同步管理
│   │   │   └── chat_history_service.py # 全局对话历史知识库（自动存档+向量化+定期清理）
│   │   ├── graphs/               # LangGraph 工作流
│   │   │   ├── medagent_graph.py # 健康咨询 LangGraph
│   │   │   ├── nodes.py          # 图节点
│   │   │   └── graph_state.py    # 状态定义
│   │   ├── tasks/                # RQ 后台任务
│   │   │   ├── document_tasks.py # 文档向量化任务
│   │   │   └── source_tasks.py   # 知识源同步任务
│   │   ├── adapters/             # 在线知识源适配器
│   │   │   ├── base.py           # 抽象基类
│   │   │   ├── pubmed.py         # PubMed 适配器
│   │   │   ├── msd_manual.py     # MSD Manual 适配器
│   │   │   └── drug_label.py     # FDA Drug Label 适配器
│   │   └── prompts/              # LLM 提示词模板
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 自动化测试
│   ├── k8s/                      # Kubernetes 部署文件
│   ├── worker.py                 # RQ Worker 入口
│   ├── Dockerfile                # 后端容器构建
│   └── docker-compose.yml        # 本地编排
│
└── medagent-frontend/            # React 前端
    ├── src/
    │   ├── App.tsx               # 根组件（布局、路由、自定义背景图）
    │   ├── pages/                # 页面组件
    │   │   ├── Login.tsx / Register.tsx
    │   │   ├── Dashboard.tsx
    │   │   ├── MedicalQA.tsx     # 知识库问答（含对话历史 KB 自动检索）
    │   │   ├── HealthConsult.tsx # 健康咨询
    │   │   ├── DocumentManagement.tsx # 文档管理（线上/线下分类统计）
    │   │   ├── KBManagement.tsx  # 知识库管理（含内置对话历史 KB，30 秒自动刷新）
    │   │   ├── SourceManagement.tsx
    │   │   ├── AdminDashboard.tsx # 管理概览（30 秒自动轮询）
    │   │   ├── AdminUsers.tsx
    │   │   ├── AdminConfig.tsx
    │   │   └── AdminFeedback.tsx
    │   ├── components/
    │   │   ├── ChatInterface.tsx  # 通用对话组件（背景图片透传）
    │   │   └── ThemeSettings.tsx  # 主题/背景图片设置
    │   ├── contexts/ThemeContext.tsx
    │   └── services/api.ts       # API 客户端（Axios）
    ├── package.json
    ├── Dockerfile                # Nginx 生产镜像
    └── .env.example
```

---

## 快速启动

### 1. Docker Compose 一键部署

```bash
# 克隆项目
git clone <repo-url> && cd medagent

# 配置 API Key（后端）
cp medagent-backend/.env.example medagent-backend/.env
# 编辑 .env，填入 LLM_API_KEY（支持 OpenAI、DeepSeek 等）

# 启动所有服务（MySQL + PostgreSQL + Redis + 后端 + Worker + 前端）
cd medagent-backend
docker-compose up -d

# 等待启动后访问
# http://localhost:3000
```

> 首次启动会自动初始化数据库表结构、默认管理员账号和全局对话历史知识库。

### 2. 本地开发

#### 前置条件

| 依赖 | 版本 |
|------|------|
| Python | 3.11+ |
| MySQL | 8.0+ |
| PostgreSQL | 16+（需安装 pgvector 扩展） |
| Redis | 7+ |
| Node.js | 18+ |

#### 2.1 后端

```bash
cd medagent-backend

# 创建虚拟环境
python -m venv .venv && source .venv/bin/activate
# Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 等配置

# 初始化数据库
python -c "from app.db.init_db import init_database; init_database()"

# 启动后端服务
uvicorn app.main:app --reload --port 8000
```

#### 2.2 RQ Worker（文档处理）

```bash
# 新开终端，同目录下
cd medagent-backend
source .venv/bin/activate
python worker.py
```

#### 2.3 前端

```bash
# 新开终端
cd medagent-frontend
npm install

# 配置后端地址（默认即可）
cp .env.example .env

# 启动开发服务器
npm start
# 访问 http://localhost:3000
```

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
| `SECRET_KEY` | JWT 签名密钥（请务必修改） | `change-this-to-a-secure-random-key` |
| `TOP_K` | 向量检索返回条数 | `5` |
| `SIMILARITY_THRESHOLD` | 向量检索相似度阈值 | `0.5` |

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
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/refresh` | 刷新 Token |
| GET | `/api/kb` | 知识库列表（含对话历史知识库） |
| POST | `/api/kb` | 创建知识库 |
| DELETE | `/api/kb/{id}` | 删除知识库（chat_history 类型禁止删除） |
| GET | `/api/documents` | 文档列表（可选按知识库筛选） |
| POST | `/api/documents/upload` | 上传文档 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| POST | `/api/chat` | 发送问答消息（自动检索对话历史） |
| GET | `/api/chat/stream` | 流式问答（SSE） |
| GET | `/api/sessions` | 历史会话列表 |
| GET | `/api/sessions/{id}` | 会话详情 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/feedback` | 提交反馈 |
| GET | `/api/sources` | 在线知识源列表 |
| POST | `/api/sources` | 创建在线知识源 |
| POST | `/api/sources/{id}/sync` | 触发同步 |
| GET | `/api/admin/stats` | 管理概览统计（含线上/线下文档分类） |

---

## 在线知识源

MedAgent 支持通过适配器架构接入在线医学知识源，作为文档上传之外的补充内容来源。

| 知识源 | 适配器 | 说明 |
|--------|--------|------|
| **PubMed** | `PubMedAdapter` | 通过 NCBI E-utilities API 搜索并获取医学文献摘要 |
| **MSD Manual** | `MSDManualAdapter` | 爬取 MSD 诊疗手册（专业版）章节内容 |
| **FDA Drug Label** | `DrugLabelAdapter` | 通过 openFDA API 获取药品说明书标签 |

> 在线知识源同步后的文档会被向量化并纳入 RAG 检索范围，与上传文档统一检索。

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

---

## 部署

### Docker Compose

```bash
cd medagent-backend
docker-compose up -d --build
```

启动的服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| `frontend` | 3000 | Nginx 静态文件服务 |
| `backend` | 8000 | FastAPI 应用 |
| `worker` | — | RQ Worker（文档处理） |
| `mysql` | 3306 | 关系数据库 |
| `postgres` | 5432 | 向量数据库 |
| `redis` | 6379 | 缓存与消息队列 |

### Kubernetes

```bash
cd medagent-backend/k8s
kubectl apply -f namespace.yaml
kubectl apply -f .
```

---

## 默认管理员账号

| 用户名 | `admin` |
| 密码 | （初始化时设置，请咨询管理员） |

> ⚠️ 生产环境请务必修改默认密码。

---

## 开发

```bash
# 运行后端测试
cd medagent-backend
pytest tests/ -v

# 前端构建
cd medagent-frontend
npm run build
```

---

## 许可证

[MIT](LICENSE)
