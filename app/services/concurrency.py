"""Bounded concurrency helpers for independent generation requests."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Generic, Sequence, TypeVar, cast


ResultType = TypeVar("ResultType")


@dataclass(frozen=True)
class GenerationTask(Generic[ResultType]):
    """A named unit of independent work."""

    name: str
    execute: Callable[[], ResultType]


class GenerationTaskError(RuntimeError):
    """Raised when one concurrent generation task fails."""


def run_generation_tasks(
    tasks: Sequence[GenerationTask[ResultType]],
    *,
    concurrent: bool,
    max_workers: int,
) -> list[ResultType]:
    """Run tasks serially or concurrently while preserving input order.

    Serial execution remains the default-compatible path. Concurrent execution
    is bounded and fail-fast: a failed task cancels work that has not started and
    raises a stage-aware error instead of returning a partial, misordered result.
    """
    if not isinstance(max_workers, int) or max_workers < 1:
        raise ValueError("max_workers must be a positive integer")
    if not tasks:
        return []

    if not concurrent or max_workers == 1 or len(tasks) == 1:
        results = []
        for task in tasks:
            try:
                results.append(task.execute())
            except Exception as error:
                raise GenerationTaskError(
                    f"generation task failed: {task.name}: {error}"
                ) from error
        return results

    worker_count = min(max_workers, len(tasks))
    unassigned = object()
    ordered_results: list[ResultType | object] = [unassigned] * len(tasks)

    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="generation",
    ) as executor:
        future_to_task: dict[Future[ResultType], tuple[int, GenerationTask[ResultType]]] = {
            executor.submit(task.execute): (index, task)
            for index, task in enumerate(tasks)
        }

        try:
            for future in as_completed(future_to_task):
                index, task = future_to_task[future]
                try:
                    ordered_results[index] = future.result()
                except Exception as error:
                    for pending_future in future_to_task:
                        if pending_future is not future:
                            pending_future.cancel()
                    raise GenerationTaskError(
                        f"generation task failed: {task.name}: {error}"
                    ) from error
        finally:
            for future in future_to_task:
                if not future.done():
                    future.cancel()

    if any(result is unassigned for result in ordered_results):
        raise GenerationTaskError("one or more generation tasks returned no result")
    return cast(list[ResultType], ordered_results)
