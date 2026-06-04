from graph.state import AgentGraphState
from agents.mindmap_agent import MindMapAgent
from agents.base import AgentState

_mindmap_agent = MindMapAgent()


async def study_mindmap_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
    )
    result = await _mindmap_agent.process(agent_state)
    mindmap = result.get("response", "")

    outputs = list(state.get("workflow_outputs") or [])
    outputs.append({"stage": "mindmap", "data": mindmap})

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "study_mindmap", "result_summary": "生成思维导图"})

    return {
        "generated_mindmap": mindmap,
        "agent_feedback": {
            "mindmap_generated": bool(mindmap),
            "needs_quiz": True,
            "task_completed": True,
        },
        "workflow_outputs": outputs,
        "completed_tasks": completed,
    }
