# 阿里云前后端分离部署与 7×24 运维

生产结构为：Nginx 托管前端静态文件并反向代理 `/api`，FastAPI 仅监听
`127.0.0.1:8000`，RQ Worker 独立运行；MySQL 保存业务数据，PostgreSQL/pgvector
保存向量，MongoDB 保存多轮会话记忆，Redis 保存任务队列。

## 部署

1. 将项目放到 `/opt/medagent`，创建 `medagent` 系统用户和 Python 虚拟环境
   `/opt/medagent/.venv`，安装 `medagent-backend/requirements.txt`。
2. 在 `medagent-backend/.env` 配置数据库、MongoDB、Redis、模型接口和随机
   `SECRET_KEY`。生产环境设置 `SESSION_MEMORY_BACKEND=mongodb` 与
   `MONGODB_REQUIRED=true`。
3. 在前端执行 `npm ci && npm run build`，将 `dist/` 内容复制到
   `/var/www/medagent/`。
4. 将 `deploy/alicloud/nginx-medagent.conf` 安装到 Nginx 站点目录，先执行
   `nginx -t`，再 reload。
5. 将三个 `.service`/`.timer` 文件复制到 `/etc/systemd/system/`，然后执行：

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now medagent-backend medagent-worker medagent-healthcheck.timer nginx
   ```

## SSE 稳定性

聊天流和 Agent 事件流使用独立 Nginx location，关闭代理缓冲、缓存和 gzip，
设置 `X-Accel-Buffering: no` 与一小时读写超时。后端也返回相同防缓冲响应头，
避免 Nginx 聚合事件后造成前端长时间不更新。

## 健康检查与恢复

- `/health/ready` 检查 MySQL、PostgreSQL 和必需的 MongoDB 会话记忆后端。
- `/health/session-memory` 单独显示当前记忆存储状态和是否降级。
- systemd 使用 `Restart=always` 自动拉起 API/Worker；timer 每分钟检查 readiness，
  异常时重启后端。
- 日志查看：`journalctl -u medagent-backend -u medagent-worker -f`。

生产启用 HTTPS 时，将证书配置在 Nginx，安全组只开放 80/443；8000、3306、
5432、6379、27017 均不应直接暴露到公网。
