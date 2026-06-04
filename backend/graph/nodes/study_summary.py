import json
from graph.state import AgentGraphState


async def study_summary_node(state: AgentGraphState) -> dict:
    outputs = state.get("workflow_outputs", [])
    analysis = state.get("profile_analysis", {})

    summary = {
        "workflow": "study",
        "topic": state["user_message"],
        "level": analysis.get("current_level", "未知"),
        "stages": outputs,
    }

    return {
        "response": json.dumps(summary, ensure_ascii=False),
    }
