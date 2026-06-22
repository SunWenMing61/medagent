"""
RQ Worker 入口点，用于处理异步文档任务（如文档解析、向量化等）。

该脚本启动一个 RQ（Redis Queue）工作进程，监听 "default" 队列中的任务。
由单独的进程运行，与 FastAPI 应用进程解耦。
"""
# 导入 os 模块，用于文件和路径操作
import os
# 导入 sys 模块，用于修改 Python 模块搜索路径
import sys

# 将当前文件所在目录添加到 Python 模块搜索路径的最前面
# 确保脚本可以直接导入项目中的模块（如 app 包）
sys.path.insert(0, os.path.dirname(__file__))

# 从 redis 库导入 Redis 客户端类，用于连接 Redis 服务器
from redis import Redis
# 从 rq（Redis Queue）库导入 Worker（工作进程）和 Queue（任务队列）类
from rq import Worker, Queue

# 导入应用配置，获取 Redis 连接地址等参数
from app.core.config import settings

# 定义要监听的队列名称列表，这里只监听 "default" 队列
listen = ["default"]

# 从应用的 Redis 配置 URL 创建 Redis 连接实例
redis_conn = Redis.from_url(settings.REDIS_URL)

if __name__ == "__main__":
    """
    当该脚本作为主程序直接运行时（而非被导入），创建并启动 RQ Worker。

    运行逻辑：
    1. 根据 listen 列表中的队列名称，为每个队列创建 Queue 对象
    2. 将所有 Queue 对象绑定到同一个 Redis 连接
    3. 创建 Worker 实例，传入队列列表和 Redis 连接
    4. 调用 worker.work() 进入事件循环，持续监听并处理队列中的任务
    """
    worker = Worker([Queue(name, connection=redis_conn) for name in listen])
    worker.work()  # 启动工作进程，开始监听和处理任务（阻塞调用）
