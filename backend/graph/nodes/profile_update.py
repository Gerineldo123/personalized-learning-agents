from graph.state import AgentGraphState
from agents.profile_agent import ProfileAgent
from agents.base import AgentState

_profile_agent = ProfileAgent()


async def profile_update_node(state: AgentGraphState) -> dict:
    report = state.get("evaluation_report", {})
    summary = report.get("summary", "")
    weaknesses = ", ".join(report.get("weaknesses", []))

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=f"根据评估更新画像：{summary}。薄弱环节：{weaknesses}",
        profile=state.get("profile"),
    )
    result = await _profile_agent.process(agent_state)

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "profile_update", "result_summary": "画像已更新"})

    return {
        "profile": result.get("profile"),
        "agent_feedback": {"profile_updated": True, "task_completed": True},
        "completed_tasks": completed,
    }
