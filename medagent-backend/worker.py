"""RQ Worker entry point for processing async document tasks."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from redis import Redis
from rq import Worker, Queue

from app.core.config import settings

listen = ["default"]

redis_conn = Redis.from_url(settings.REDIS_URL)

if __name__ == "__main__":
    worker = Worker([Queue(name, connection=redis_conn) for name in listen])
    worker.work()
