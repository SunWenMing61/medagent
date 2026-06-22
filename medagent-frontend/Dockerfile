# ===== 构建阶段（Build Stage） =====
# 使用 Node.js 18 Alpine 作为构建环境（轻量且包含 npm）
FROM node:18-alpine AS build

# 设置容器内工作目录
WORKDIR /app

# 复制包管理配置文件到镜像
# 先复制 package.json 和 tsconfig.json，利用 Docker 分层缓存：只要这两个文件不变，后续的 npm install 可复用缓存
COPY package.json tsconfig.json ./

# 安装前端项目依赖（从 npm 仓库下载）
RUN npm install

# 复制源代码文件到镜像
COPY public/ public/     # 静态资源目录（favicon、index.html、manifest 等）
COPY src/ src/           # React 源代码目录（组件、样式、工具函数等）

# 构建前端应用（执行 React 构建脚本，生成优化的静态文件到 build/ 目录）
RUN npm run build

# ===== 生产运行阶段（Production Stage） =====
# 使用 Nginx Alpine 作为生产环境 Web 服务器（比完整版更小，更安全）
FROM nginx:alpine

# 从构建阶段复制构建产物到 Nginx 的 HTML 目录
COPY --from=build /app/build /usr/share/nginx/html

# 动态创建 Nginx 配置文件（支持 SPA 单页应用路由）
# 因为 Dockerfile 中不能直接复制宿主机文件到特定目录，所以用 echo 内联生成配置
RUN echo 'server { \
    listen 80; \                                              # 监听 80 端口
    server_name localhost; \                                  # 服务器名称
    root /usr/share/nginx/html; \                             # 静态文件根目录
    index index.html; \                                       # 默认首页
    location / { \                                            # 根路径配置
        try_files $uri $uri/ /index.html; \                   # SPA 回退：所有路径尝试 index.html
    } \
    location /api/ { \                                        # API 反向代理
        proxy_pass http://backend:8000; \                     # 代理到后端服务
        proxy_set_header Host $host; \                        # 传递 Host 头
        proxy_set_header X-Real-IP $remote_addr; \            # 传递客户端真实 IP
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \  # 传递代理链
        proxy_set_header X-Forwarded-Proto $scheme; \         # 传递协议
    } \
    location /static/ { \                                     # 静态资源缓存配置
        expires 1y; \                                         # 缓存过期时间设为 1 年（强缓存）
        add_header Cache-Control "public, immutable"; \       # 标记为不可变缓存（内容哈希后永不改变）
    } \
}' > /etc/nginx/conf.d/default.conf

# 声明容器监听端口（Nginx HTTP 端口）
EXPOSE 80

# 以非 daemon 模式启动 Nginx（容器需要前台进程保持运行）
CMD ["nginx", "-g", "daemon off;"]
