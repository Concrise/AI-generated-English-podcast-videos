import ast
import threading
import time
from abc import ABC, abstractmethod

from app.config import config
from app.models import const


# Base class for state management
class BaseState(ABC):
    @abstractmethod
    def update_task(self, task_id: str, state: int, progress: int = 0, **kwargs):
        pass

    @abstractmethod
    def get_task(self, task_id: str):
        pass

    @abstractmethod
    def get_all_tasks(self, page: int, page_size: int):
        pass


# Memory state management
class MemoryState(BaseState):
    def __init__(self):
        self._tasks = {}
        self._lock = threading.RLock()

    def get_all_tasks(self, page: int, page_size: int):
        start = (page - 1) * page_size
        end = start + page_size
        with self._lock:
            tasks = [dict(task) for task in self._tasks.values()]
        tasks.sort(
            key=lambda task: (task.get("created_at", 0), task.get("task_id", "")),
            reverse=True,
        )
        total = len(tasks)
        return tasks[start:end], total

    def update_task(
        self,
        task_id: str,
        state: int = const.TASK_STATE_PROCESSING,
        progress: int = 0,
        **kwargs,
    ):
        progress = max(0, min(100, int(progress)))
        with self._lock:
            existing = self._tasks.get(task_id, {})
            created_at = existing.get("created_at", time.time())
            self._tasks[task_id] = {
                **existing,
                "task_id": task_id,
                "state": state,
                "progress": progress,
                "created_at": created_at,
                "updated_at": time.time(),
                **kwargs,
            }

    def get_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def delete_task(self, task_id: str):
        with self._lock:
            self._tasks.pop(task_id, None)


# Redis state management
class RedisState(BaseState):
    TASK_KEY_PREFIX = "task:state:"
    TASK_INDEX_KEY = "task:index"

    def __init__(self, host="localhost", port=6379, db=0, password=None):
        import redis

        self._redis = redis.StrictRedis(host=host, port=port, db=db, password=password)

    @classmethod
    def _task_key(cls, task_id: str) -> str:
        return f"{cls.TASK_KEY_PREFIX}{task_id}"

    def get_all_tasks(self, page: int, page_size: int):
        start = (page - 1) * page_size
        end = start + page_size - 1
        total = self._redis.zcard(self.TASK_INDEX_KEY)
        task_ids = self._redis.zrevrange(self.TASK_INDEX_KEY, start, end)
        pipeline = self._redis.pipeline(transaction=False)
        for task_id in task_ids:
            decoded_task_id = task_id.decode("utf-8")
            pipeline.hgetall(self._task_key(decoded_task_id))
        task_rows = pipeline.execute() if task_ids else []

        tasks = []
        for task_data in task_rows:
            if not task_data:
                continue
            tasks.append(
                {
                    key.decode("utf-8"): self._convert_to_original_type(value)
                    for key, value in task_data.items()
                }
            )
        return tasks, total

    def update_task(
        self,
        task_id: str,
        state: int = const.TASK_STATE_PROCESSING,
        progress: int = 0,
        **kwargs,
    ):
        progress = max(0, min(100, int(progress)))
        task_key = self._task_key(task_id)
        existing_created_at = self._redis.hget(task_key, "created_at")
        created_at = (
            float(existing_created_at.decode("utf-8"))
            if existing_created_at
            else time.time()
        )

        fields = {
            "task_id": task_id,
            "state": state,
            "progress": progress,
            "created_at": created_at,
            "updated_at": time.time(),
            **kwargs,
        }
        encoded_fields = {field: str(value) for field, value in fields.items()}
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.hset(task_key, mapping=encoded_fields)
        pipeline.zadd(self.TASK_INDEX_KEY, {task_id: created_at})
        pipeline.execute()

    def get_task(self, task_id: str):
        task_data = self._redis.hgetall(self._task_key(task_id))
        if not task_data:
            return None

        task = {
            key.decode("utf-8"): self._convert_to_original_type(value)
            for key, value in task_data.items()
        }
        return task

    def delete_task(self, task_id: str):
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.delete(self._task_key(task_id))
        pipeline.zrem(self.TASK_INDEX_KEY, task_id)
        pipeline.execute()

    @staticmethod
    def _convert_to_original_type(value):
        """
        Convert the value from byte string to its original data type.
        You can extend this method to handle other data types as needed.
        """
        value_str = value.decode("utf-8")

        try:
            # try to convert byte string array to list
            return ast.literal_eval(value_str)
        except (ValueError, SyntaxError):
            pass

        if value_str.isdigit():
            return int(value_str)
        # Add more conversions here if needed
        return value_str


# Global state
_enable_redis = config.app.get("enable_redis", False)
_redis_host = config.app.get("redis_host", "localhost")
_redis_port = config.app.get("redis_port", 6379)
_redis_db = config.app.get("redis_db", 0)
_redis_password = config.app.get("redis_password", None)

state = (
    RedisState(
        host=_redis_host, port=_redis_port, db=_redis_db, password=_redis_password
    )
    if _enable_redis
    else MemoryState()
)
