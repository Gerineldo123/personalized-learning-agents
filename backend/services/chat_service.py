from core.llm_client import chat_completion
from agents.registry import get_agent, get_all_agents
from core.sse import sse_stream
from agents.base import AgentState
from core.database import SessionLocal
from models.student import StudentProfile
from services.safety_service import check_text, check_text_input
from fastapi.responses import StreamingResponse

INTENT_PROMPT = """根据对话历史和用户消息，判断应调用哪个智能体。

可选智能体（名称: 描述 — 必须严格返回名称列的值）：
{agent_list}

对话历史：{history}
用户消息：{message}

只能返回上面列出的智能体名称本身（纯英文），不要任何其他文字、标点、解释。"""


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

    agents = get_all_agents()
    agent_desc = "\n".join([f"'{a.name}': {a.description}" for a in agents])
    history_text = _format_history(history)

    intent_resp = await chat_completion([
        {"role": "system", "content": INTENT_PROMPT.format(
            agent_list=agent_desc, history=history_text, message=message
        )},
        {"role": "user", "content": message}
    ])
    agent_name = _clean_agent_name(intent_resp.choices[0].message.content)
    agent = _resolve_agent(agent_name, agents)

    profile = _load_profile(user_id)

    state = AgentState(
        user_id=user_id,
        user_message=message,
        profile=profile,
        history=history or [],
    )
    result = agent.stream(state)

    async def safe_result():
        collected = ""
        async for chunk in result:
            collected += chunk
            yield chunk
        safe_text, ok = await check_text(collected)
        if not ok:
            state["response"] = safe_text

    return StreamingResponse(
        sse_stream(safe_result()),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _clean_agent_name(raw: str) -> str:
    name = raw.strip().strip('"').strip("'").strip("`").strip(".")
    name = name.split("\n")[0].split(":")[0].split("：")[0].strip()
    return name


def _resolve_agent(name: str, agents):
    name_lower = name.lower()

    for a in agents:
        if a.name.lower() == name_lower:
            return a

    for a in agents:
        if a.name.lower() in name_lower or name_lower in a.name.lower():
            return a

    return get_agent("chat")


def _load_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()
    finally:
        db.close()


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return "（无历史对话）"
    recent = history[-10:]
    lines = []
    for h in recent:
        role = "用户" if h.get("role") == "user" else "助手"
        content = h.get("content", "")[:200]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
