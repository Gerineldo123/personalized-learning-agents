from graph.state import AgentGraphState
from agents.video_agent import VideoAgent
from agents.base import AgentState

_video_agent = VideoAgent()


async def video_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        profile_analysis=state.get("profile_analysis") or {},
    )
    result = await _video_agent.process(agent_state)
    response = result.get("response", "")

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "video", "result_summary": "视频搜索完成"})

    return {
        "response": response,
        "agent_feedback": {"task_completed": True, "all_tasks_done": True},
        "messages": [{"role": "assistant", "content": response}],
        "completed_tasks": completed,
        "workflow_outputs": [{"stage": "video_search", "data": response}],
    }
