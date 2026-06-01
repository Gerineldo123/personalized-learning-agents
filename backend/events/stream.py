import json
import asyncio
from collections import defaultdict

_user_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


def publish(user_id: str, event_type: str, data: dict):
    msg = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    for uid in list(_user_queues.keys()):
        try:
            _user_queues[uid].put_nowait(msg)
        except asyncio.QueueFull:
            pass


async def subscribe(user_id: str):
    queue = _user_queues[user_id]
    while True:
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=25)
            yield msg
        except asyncio.TimeoutError:
            yield '{"type":"ping"}'


def unsubscribe(user_id: str):
    _user_queues.pop(user_id, None)
