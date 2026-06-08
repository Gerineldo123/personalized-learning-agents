import aiosqlite
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph.builder import compile_graph
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
from services.safety_service import check_text_input
from agents.chat_agent import ChatAgent
from agents.base import AgentState

_CHECKPOINT_DB = "checkpoints.db"
_graph_no_cp = compile_graph()
_chat_agent = ChatAgent()


async def route_to_agent(
    user_id: str,
    message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
):
    safe_message, ok = check_text_input(message)
    if not ok:
        async def deny():
            yield "抱歉，您的输入包含不当内容，请重新提问。"
        return StreamingResponse(
            sse_stream(deny()),
            media_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    profile = _load_profile(user_id)

    agent_state = AgentState(
        user_id=user_id,
        user_message=safe_message,
        profile=profile,
        history=history or [],
    )

    async def event_stream():
        async for chunk in _chat_agent.stream(agent_state):
            yield chunk

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _load_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()
    finally:
        db.close()