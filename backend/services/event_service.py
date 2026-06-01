import asyncio
import json
from typing import Callable

_listeners: list[asyncio.Queue] = []
_callbacks: dict[str, list[Callable]] = {}


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _listeners.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    if q in _listeners:
        _listeners.remove(q)


def on(event: str):
    def decorator(func):
        _callbacks.setdefault(event, []).append(func)
        return func
    return decorator


async def emit(event: str, data: dict):
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    dead = []
    for q in _listeners:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _listeners.remove(q)

    for callback in _callbacks.get(event, []):
        try:
            await callback(data)
        except Exception:
            pass
