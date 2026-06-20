# MedAgent Backend

基于 Python FastAPI + LangChain + LangGraph 的医学知识库问答与健康咨询辅助平台后端。

## 技术栈

- **后端**: Python 3.11, FastAPI, SQLAlchemy, Pydantic v2
- **关系数据库**: MySQL 8.0（用户、文档、会话等业务数据）
- **向量数据库**: PostgreSQL 16 + pgvector（文档块向量搜索）
- **缓存/队列**: Redis, RQ (Redis Queue)
- **AI**: LangChain, LangGraph, OpenAI API
- **前端**: React 18, TypeScript, Ant Design
- **部署**: Docker, Docker Compose, Kubernetes

## 快速开始

### 前置条件

- Python 3.11+
- MySQL 8.0+
- PostgreSQL 16+ (with pgvector)
- Redis 7+
- Node.js 18+（前端开发）
- Docker & Docker Compose（容器化部署）

### 1. 后端本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量 (修改 .env 中的 LLM_API_KEY)
cp .env.example .env

# 初始化数据库
python -c "from app.db.init_db import init_database; init_database()"

# 启动后端服务
uvicorn app.main:app --reload --port 8000
```

### 2. 启动 RQ Worker (文档处理)

```bash
python worker.py
```

### 3. 前端本地开发

```bash
cd ../medagent-frontend
npm install
npm start
```

### 4. Docker Compose 一键部署

```bash
docker-compose up -d
```

访问 http://localhost:3000

### 5. Kubernetes 部署

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

## 默认管理员账号

- 用户名: admin
- 密码: admin123

## 项目结构

```
medagent-backend/
  requirements.txt         # Python 依赖
  Dockerfile               # 容器构建
  docker-compose.yml       # 本地编排
  worker.py                # RQ Worker 入口

  app/
    main.py                # FastAPI 应用入口
    core/                  # 配置、安全、依赖注入
    db/                    # 数据库会话 (MySQL + PostgreSQL)
    models/                # SQLAlchemy 数据模型
    schemas/               # Pydantic 请求/响应模型
    api/v1/                # API 路由
    services/              # 业务逻辑层
    tasks/                 # RQ 异步任务
    graphs/                # LangGraph 工作流
    utils/                 # 工具函数
    prompts/               # LLM Prompt 模板

  tests/                   # 测试
  k8s/                     # Kubernetes 部署文件
  alembic/                 # 数据库迁移
  uploads/                 # 上传文件存储
```

## API 文档

启动后端后访问 http://localhost:8000/docs 查看 Swagger UI。

## 医学安全边界

本系统为医学知识辅助工具：

- ❌ 不提供疾病诊断
- ❌ 不生成处方
- ❌ 不建议停药、换药、调整剂量
- ❌ 不替代医生诊断
- ✅ 基于上传文档的 RAG 问答
- ✅ 健康知识解释
- ✅ 就医前信息整理
- ✅ 药品说明书内容解释
