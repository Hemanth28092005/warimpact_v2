"""Retry helpers shared by ingestion fetchers."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_with_backoff(operation: Callable[[], T], delays: tuple[int, ...] = (1, 2, 4)) -> T:
    last_error: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == len(delays):
                break
            time.sleep(delays[attempt])
    if last_error is None:
        raise RuntimeError("retry operation failed without an exception")
    raise last_error


if __name__ == "__main__":
    print("retry helper ready")
