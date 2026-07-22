import threading
from typing import Any, Callable, Dict

from loguru import logger

from app.models import const


class TaskManager:
    def __init__(self, max_concurrent_tasks: int):
        if not isinstance(max_concurrent_tasks, int) or max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be a positive integer")
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_tasks = 0
        self.lock = threading.Lock()
        self.queue = self.create_queue()

    def create_queue(self):
        raise NotImplementedError()

    def add_task(self, func: Callable, *args: Any, **kwargs: Any):
        should_execute = False
        with self.lock:
            if self.current_tasks < self.max_concurrent_tasks:
                # Reserve the slot while holding the lock. Incrementing inside the
                # worker created a race where many submissions could all observe
                # the same available capacity.
                self.current_tasks += 1
                should_execute = True
                logger.info(
                    f"starting task {func.__name__}; active={self.current_tasks}"
                )
            else:
                logger.info(
                    f"queueing task {func.__name__}; active={self.current_tasks}"
                )
                self.enqueue({"func": func, "args": args, "kwargs": kwargs})

        if should_execute:
            self.execute_task(func, *args, **kwargs)

    def execute_task(self, func: Callable, *args: Any, **kwargs: Any):
        thread = threading.Thread(
            target=self.run_task,
            args=(func, *args),
            kwargs=kwargs,
            name=f"task-{func.__name__}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            with self.lock:
                self.current_tasks = max(0, self.current_tasks - 1)
            raise

    def run_task(self, func: Callable, *args: Any, **kwargs: Any):
        try:
            func(*args, **kwargs)  # call the function here, passing *args and **kwargs.
        except Exception as error:
            logger.exception(f"background task {func.__name__} failed: {error}")
            task_id = kwargs.get("task_id")
            if task_id:
                try:
                    from app.services import state as state_manager

                    state_manager.state.update_task(
                        task_id=task_id,
                        state=const.TASK_STATE_FAILED,
                        progress=100,
                        error=str(error),
                        failed_stage="background_task",
                    )
                except Exception as state_error:
                    logger.exception(
                        f"failed to persist task failure for {task_id}: {state_error}"
                    )
        finally:
            self.task_done()

    def check_queue(self):
        task_info = None
        with self.lock:
            if (
                self.current_tasks < self.max_concurrent_tasks
                and not self.is_queue_empty()
            ):
                task_info = self.dequeue()
                if task_info:
                    self.current_tasks += 1

        if task_info:
            func = task_info["func"]
            args = task_info.get("args", ())
            kwargs = task_info.get("kwargs", {})
            self.execute_task(func, *args, **kwargs)

    def task_done(self):
        with self.lock:
            self.current_tasks = max(0, self.current_tasks - 1)
        self.check_queue()

    def enqueue(self, task: Dict):
        raise NotImplementedError()

    def dequeue(self):
        raise NotImplementedError()

    def is_queue_empty(self):
        raise NotImplementedError()
