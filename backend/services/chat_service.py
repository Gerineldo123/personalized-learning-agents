import aiosqlite
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph.builder import compile_graph
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
from services.safety_service import check_text_input

_CHECKPOINT_DB = "checkpoints.db"
_graph_no_cp = compile_graph()


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

    initial_state: AgentGraphState = {
        "user_id": user_id,
        "user_message": safe_message,
        "profile": profile,
        "history": history or [],
        "messages": [],
        "response": "",
        "agent_name": "",
    }

    async def event_stream():
        if session_id:
            async with aiosqlite.connect(_CHECKPOINT_DB) as conn:
                checkpointer = AsyncSqliteSaver(conn)
                graph = compile_graph(checkpointer=checkpointer)
                config = {"configurable": {"thread_id": session_id}}
                async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
                    for node_name, update in chunk.items():
                        if "response" in update and update["response"]:
                            yield update["response"]
        else:
            async for chunk in _graph_no_cp.astream(initial_state, stream_mode="updates"):
                for node_name, update in chunk.items():
                    if "response" in update and update["response"]:
                        yield update["response"]

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
