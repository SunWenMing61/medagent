"""
RQ Worker 入口点，用于处理异步文档任务（如文档解析、向量化等）。

该脚本启动一个 RQ（Redis Queue）工作进程，监听 "default" 队列中的任务。
由单独的进程运行，与 FastAPI 应用进程解耦。
"""
# 导入 os 模块，用于文件和路径操作
import os
# 导入 sys 模块，用于修改 Python 模块搜索路径
import sys
import logging
import threading

# 将当前文件所在目录添加到 Python 模块搜索路径的最前面
# 确保脚本可以直接导入项目中的模块（如 app 包）
sys.path.insert(0, os.path.dirname(__file__))

# 从 redis 库导入 Redis 客户端类，用于连接 Redis 服务器
from redis import Redis
# 从 rq（Redis Queue）库导入 Worker（工作进程）和 Queue（任务队列）类
from rq import Worker, Queue, SimpleWorker

# 导入应用配置，获取 Redis 连接地址等参数
from app.core.config import settings
from app.services.outbox_service import dispatch_pending_outbox

# 定义要监听的队列名称列表，这里只监听 "default" 队列
listen = ["default"]

# 从应用的 Redis 配置 URL 创建 Redis 连接实例
redis_conn = Redis.from_url(settings.REDIS_URL)

logger = logging.getLogger(__name__)


def dispatch_outbox_forever(stop_event: threading.Event) -> None:
    """持续恢复 API/Redis 短暂中断期间遗留的文档上传事件。"""
    interval = max(int(settings.OUTBOX_DISPATCH_INTERVAL_SECONDS), 1)
    while not stop_event.is_set():
        try:
            result = dispatch_pending_outbox(limit=1000)
            if result["dispatched"] or result["failed"]:
                logger.info("Outbox dispatch result: %s", result)
        except Exception:
            logger.exception("Periodic outbox dispatch failed")
        stop_event.wait(interval)

if __name__ == "__main__":
    """
    当该脚本作为主程序直接运行时（而非被导入），创建并启动 RQ Worker。

    运行逻辑：
    1. 根据 listen 列表中的队列名称，为每个队列创建 Queue 对象
    2. 将所有 Queue 对象绑定到同一个 Redis 连接
    3. 创建 Worker 实例，传入队列列表和 Redis 连接
    4. 调用 worker.work() 进入事件循环，持续监听并处理队列中的任务
    """
    logging.basicConfig(level=logging.INFO)
    redis_conn.ping()

    # Windows 没有 fork/wait4，RQ 的 Worker/SpawnWorker 都依赖 Unix 进程 API；
    # 使用带 TimerDeathPenalty 的 SimpleWorker，仍由当前独立 worker 进程执行。
    # Linux/macOS 和容器继续使用隔离性更好的标准 Worker。
    worker_class = SimpleWorker if os.name == "nt" else Worker
    stop_event = threading.Event()
    dispatcher = threading.Thread(
        target=dispatch_outbox_forever,
        args=(stop_event,),
        name="document-outbox-dispatcher",
        daemon=True,
    )
    dispatcher.start()
    try:
        worker = worker_class([Queue(name, connection=redis_conn) for name in listen])
        worker.work()  # 启动工作进程，开始监听和处理任务（阻塞调用）
    finally:
        stop_event.set()
        dispatcher.join(timeout=2)
