from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging

_LOG_DEPTH: ContextVar[int] = ContextVar("log_depth", default=0)


def _indent() -> str:
    return "  " * _LOG_DEPTH.get()


class IndentFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.indent = _indent()
        return True


@contextmanager
def log_indent() -> None:
    token = _LOG_DEPTH.set(_LOG_DEPTH.get() + 1)
    try:
        yield
    finally:
        _LOG_DEPTH.reset(token)
