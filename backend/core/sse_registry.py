"""全局 SSE 队列注册表，用于 skill 实时进度推送"""
import asyncio

_sse_queues: dict[str, asyncio.Queue] = {}


def register(session_id: str, q: asyncio.Queue):
    _sse_queues[session_id] = q


def unregister(session_id: str):
    _sse_queues.pop(session_id, None)


def get(session_id: str) -> asyncio.Queue | None:
    return _sse_queues.get(session_id)
