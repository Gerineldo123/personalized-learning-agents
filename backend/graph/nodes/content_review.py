from langgraph.types import interrupt
from graph.state import AgentGraphState


async def content_review_node(state: AgentGraphState) -> dict:
    article = state.get("generated_article", "")
    quality = state.get("agent_feedback", {}).get("content_quality", 1.0)

    # 高质量内容自动通过
    if quality >= 0.8 or not article:
        return {"agent_feedback": {**state.get("agent_feedback", {}), "review_passed": True}}

    # 低质量内容暂停，等待用户决策
    decision = interrupt({
        "action": "review_content",
        "preview": article[:300],
        "quality": quality,
        "question": "内容质量偏低，请选择：accept（接受）或 retry（重新生成）",
        "options": ["accept", "retry"],
    })

    if decision == "retry":
        return {"agent_feedback": {**state.get("agent_feedback", {}), "needs_regeneration": True, "review_passed": False}}
    return {"agent_feedback": {**state.get("agent_feedback", {}), "review_passed": True}}
