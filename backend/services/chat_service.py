import json
import aiosqlite
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from graph.builder import compile_graph
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
from services.safety_service import check_text_input

_CHECKPOINT_DB = "checkpoints.db"
_graph_no_cp = compile_graph()

_NODE_MODULE = {
    "profile_analysis": "profile", "profile": "profile", "profile_update": "profile",
    "study_content": "resource", "quiz_gen": "resource", "study_mindmap": "resource",
    "content_gen": "resource", "mindmap": "resource",
    "mistake_analysis": "mistake",
    "chat": "chat",
    "evaluation": "evaluation", "path_suggest": "evaluation",
}


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
        "task_plan": [],
        "agent_feedback": {},
        "completed_tasks": [],
        "all_modules_data": {},
    }

    async def event_stream():
        if session_id:
            async with aiosqlite.connect(_CHECKPOINT_DB) as conn:
                checkpointer = AsyncSqliteSaver(conn)
                graph = compile_graph(checkpointer=checkpointer)
                config = {"configurable": {"thread_id": session_id}}
                async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
                    async for item in _yield_chunk(chunk):
                        yield item
        else:
            async for chunk in _graph_no_cp.astream(initial_state, stream_mode="updates"):
                async for item in _yield_chunk(chunk):
                    yield item

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


async def resume_workflow(session_id: str, decision: str):
    async def event_stream():
        async with aiosqlite.connect(_CHECKPOINT_DB) as conn:
            checkpointer = AsyncSqliteSaver(conn)
            graph = compile_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": session_id}}
            async for chunk in graph.astream(Command(resume=decision), config, stream_mode="updates"):
                async for item in _yield_chunk(chunk):
                    yield item

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


async def _yield_chunk(chunk: dict):
    for node_name, update in chunk.items():
        if node_name == "intent_classifier":
            continue
        # 输出进度事件（含模块标识，供前端联动显示）
        module = _NODE_MODULE.get(node_name)
        if module and "workflow_outputs" in update:
            outputs = update["workflow_outputs"]
            latest = outputs[-1] if isinstance(outputs, list) and outputs else {}
            yield json.dumps({
                "type": "stage",
                "stage": latest.get("stage", node_name),
                "module": module,
                "data": latest.get("data", ""),
            }, ensure_ascii=False)
        response = update.get("response", "")
        if response:
            yield response


def _load_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()
    finally:
        db.close()
