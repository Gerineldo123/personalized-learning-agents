from graph.state import AgentGraphState
from agents.mindmap_agent import MindMapAgent
from agents.base import AgentState

_mindmap_agent = MindMapAgent()


async def mindmap_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await _mindmap_agent.process(agent_state)
    response = result.get("response", "")

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "mindmap", "result_summary": "思维导图生成完成"})

    return {
        "response": response,
        "agent_feedback": {"task_completed": True, "all_tasks_done": True},
        "messages": [{"role": "assistant", "content": response}],
        "completed_tasks": completed,
    }
