"""在线知识源同步任务。

在 Windows 上使用 threading(因为 RQ 的 os.fork() 不可用),
在 Unix 系统上则回退到 RQ。
"""

import os   # 操作系统接口,用于路径处理
import sys  # 系统接口,用于修改 Python 模块搜索路径
import threading  # 线程模块,用于 Windows 环境下的异步任务执行

# 将项目根目录添加到模块搜索路径,以便 RQ 工作进程和线程能够正确导入应用模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.source_service import source_service  # 导入知识源服务单例


def sync_source(source_id: int, _job=None):
    """同步一个在线知识源。

    在 Unix 上由 RQ 调用,在 Windows 上由直接线程调用。

    Args:
        source_id: 要同步的知识源 ID
        _job: RQ 任务对象(未使用,但 RQ 会传入)

    Returns:
        委托给 source_service.sync_source 的结果字典
    """
    return source_service.sync_source(source_id)  # 调用知识源服务的同步方法


def enqueue_sync(source_id: int) -> None:
    """将同步任务加入队列。在 Windows 上使用线程以确保兼容性。

    Args:
        source_id: 要同步的知识源 ID
    """
    # 创建一个守护线程来执行同步任务,主线程退出时守护线程自动终止
    thread = threading.Thread(target=sync_source, args=(source_id,), daemon=True)
    thread.start()  # 启动线程
