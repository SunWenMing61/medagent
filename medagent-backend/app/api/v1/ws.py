"""WebSocket 处理器 —— 实时推送后台任务进度。

通过 Redis Pub/Sub 监听任务事件，经 WebSocket 推送给前端。
支持 JWT 令牌认证和按 task_id 订阅过滤。
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.services.task_manager import task_manager, _get_redis, TASK_CHANNEL

logger = logging.getLogger(__name__)

# 创建一个独立的 APIRouter，用于挂载 WebSocket 端点
# 该路由不会包含在 router.py 中，而是在 main.py 中直接挂载
router = APIRouter()


@router.websocket("/ws/tasks")
async def task_ws(websocket: WebSocket):
    """WebSocket 端点：实时推送任务进度。

    连接方式：ws://host/api/ws/tasks?token=<JWT_TOKEN>&subscribe=task_id1,task_id2

    查询参数：
        token (必填): JWT 认证令牌
        subscribe (可选): 要订阅的 task_id 列表，逗号分隔。为空则推送该用户所有任务。

    事件格式（服务器 -> 客户端）：
        {"type": "task_progress", "task_id": "...", "status": "...", "progress": 50, "message": "..."}
        {"type": "heartbeat", "timestamp": "..."}
        {"type": "error", "message": "..."}
    """
    await websocket.accept()

    # ── 验证 JWT 令牌 ────────────────────────────────────────────────────
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.send_json({"type": "error", "message": "缺少认证令牌"})
        await websocket.close(code=4001)
        return

    payload = decode_access_token(token)
    if payload is None:
        await websocket.send_json({"type": "error", "message": "令牌无效或已过期"})
        await websocket.close(code=4001)
        return

    user_id = int(payload.get("sub", 0))
    logger.info("WebSocket 用户 %s 已连接", user_id)

    # ── 解析订阅列表 ──────────────────────────────────────────────────────
    subscribe_param = websocket.query_params.get("subscribe", "")
    subscribed_ids: Set[str] = set()
    if subscribe_param:
        subscribed_ids = {tid.strip() for tid in subscribe_param.split(",") if tid.strip()}

    # ── 订阅 Redis Pub/Sub ────────────────────────────────────────────────
    r = _get_redis()
    pubsub = None
    if r:
        try:
            pubsub = r.pubsub()
            pubsub.subscribe(TASK_CHANNEL)
            logger.debug("WebSocket 已订阅 Redis 频道: %s", TASK_CHANNEL)
        except Exception as e:
            logger.warning("WebSocket Redis pubsub 订阅失败: %s", e)

    try:
        heartbeat_ticks = 0

        while True:
            # ── 从 Redis Pub/Sub 读取任务事件 ──────────────────────────────
            if pubsub:
                try:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        task_id = data.get("task_id", "")

                        # 权限过滤：只推送属于该用户的任务
                        task = task_manager.get_task(task_id)
                        if not task:
                            continue

                        uid = task.get("user_id")
                        if isinstance(uid, bytes):
                            uid = int(uid.decode())

                        # 检查用户权限 + 订阅列表
                        if uid != user_id:
                            continue
                        if subscribed_ids and task_id not in subscribed_ids:
                            continue

                        await websocket.send_json(data)
                except Exception as e:
                    logger.debug("Pubsub 读取错误: %s", e)

            # ── 每 30 秒发送一次心跳 ─────────────────────────────────────
            heartbeat_ticks += 1
            if heartbeat_ticks >= 30:  # 约 30 次循环（每次 sleep 1s）
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    break
                heartbeat_ticks = 0

            # ── 接收客户端消息（用于断开检测和 ping/pong） ──────────────
            try:
                client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if client_msg == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                logger.info("WebSocket 用户 %s 断开连接", user_id)
                break

    except WebSocketDisconnect:
        logger.info("WebSocket 用户 %s 断开连接", user_id)
    except Exception as e:
        logger.warning("WebSocket 错误: %s", e)
    finally:
        # ── 清理资源 ───────────────────────────────────────────────────────
        if pubsub:
            try:
                pubsub.unsubscribe(TASK_CHANNEL)
                pubsub.close()
            except Exception:
                pass
        logger.info("WebSocket 用户 %s 连接已关闭", user_id)
