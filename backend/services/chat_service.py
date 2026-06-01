from fastapi.responses import StreamingResponse

from graph.builder import compile_graph
from graph.state import AgentGraphState
from agents.registry import get_agent
from agents.base import AgentState
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
from services.safety_service import check_text, check_text_input


# 编译图（模块级单例，避免每次请求重复编译）
_graph = compile_graph()


async def route_to_agent(user_id: str, message: str, history: list[dict] | None = None):
    safe_message, ok = check_text_input(message)
    if not ok:
        async def deny():
            yield "抱歉，您的输入包含不当内容，请重新提问。"

        return StreamingResponse(
            sse_stream(deny()),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    profile = _load_profile(user_id)

    # 构建初始 state
    initial_state: AgentGraphState = {
        "user_id": user_id,
        "user_message": safe_message,
        "profile": profile,
        "history": history or [],
        "messages": [],
        "response": "",
        "agent_name": "",
    }

    # 通过 LangGraph 图执行：intent_classifier → agent_node → END
    # 使用 astream 以 updates 模式获取每个节点的输出
    async def event_stream():
        async for chunk in _graph.astream(initial_state, stream_mode="updates"):
            # chunk 格式: {node_name: state_update_dict}
            for node_name, update in chunk.items():
                if node_name == "intent_classifier":
                    # 意图分类节点不产生用户可见输出
                    continue
                # Agent 节点的输出
                response = update.get("response", "")
                if response:
                    yield response

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _load_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()
    finally:
        db.close()
