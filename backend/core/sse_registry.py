"""全局 SSE 队列注册表，用于 skill 实时进度推送"""
import asyncio

_sse_queues: dict[str, asyncio.Queue] = {}
_live_token_steps: dict[str, set] = {}  # session_id -> set of step_ids already streamed live


def register(session_id: str, q: asyncio.Queue):
    _sse_queues[session_id] = q
    _live_token_steps[session_id] = set()


def unregister(session_id: str):
    _sse_queues.pop(session_id, None)
    _live_token_steps.pop(session_id, None)


def get(session_id: str) -> asyncio.Queue | None:
    return _sse_queues.get(session_id)


def mark_live_token_step(session_id: str, step_id: str):
    """标记某 step_id 的 token 已被实时直推，run_graph 应跳过"""
    s = _live_token_steps.get(session_id)
    if s is not None:
        s.add(step_id)


def get_live_token_steps(session_id: str) -> set:
    return _live_token_steps.get(session_id, set())
