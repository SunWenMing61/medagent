# ===== 基础镜像阶段 =====
# 基于 Python 3.11 的精简版镜像（slim 版本比完整版更小，适合生产部署）
FROM python:3.11-slim

# 设置容器内工作目录为 /app（后续所有命令都在此目录下执行）
WORKDIR /app

# 安装系统级依赖库
# --no-install-recommends：仅安装必要的包，不安装推荐包，减小镜像体积
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \                    # PostgreSQL 客户端库（psycopg2 编译所需）
    && rm -rf /var/lib/apt/lists/* # 清理 apt 缓存，减小镜像层体积

# 将项目的 requirements.txt 复制到镜像中
# 先复制依赖文件再安装依赖，利用 Docker 分层缓存加速构建（requirements.txt 未变时复用此层缓存）
COPY requirements.txt .

# 安装 Python 依赖包
# --no-cache-dir：不缓存 pip 包，减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 将整个项目代码复制到镜像的工作目录中
COPY . .

# 声明容器运行时监听的端口（仅作文档说明，实际端口映射在 docker-compose.yml 中配置）
EXPOSE 8000

# 容器启动时执行的默认命令
# uvicorn：ASGI 服务器，运行 FastAPI 应用
# app.main:app —— 从 app.main 模块导入名为 app 的 FastAPI 实例
# --host 0.0.0.0 —— 监听所有网络接口（使容器外部可访问）
# --port 8000 —— 监听 8000 端口
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
