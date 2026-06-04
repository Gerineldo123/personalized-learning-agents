import json
from graph.state import AgentGraphState
from agents.evaluation_agent import EvaluationAgent
from agents.base import AgentState

_evaluation_agent = EvaluationAgent()


async def evaluation_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await _evaluation_agent.process(agent_state)
    response = result.get("response", "")

    # 解析评估报告供下游节点使用
    evaluation_report = {}
    try:
        parsed = json.loads(response)
        evaluation_report = {
            "overall_score": parsed.get("overall_score", 0),
            "strengths": parsed.get("strengths", []),
            "weaknesses": parsed.get("weaknesses", []),
            "suggestions": parsed.get("suggestions", []),
            "summary": parsed.get("summary", ""),
        }
    except (json.JSONDecodeError, TypeError):
        evaluation_report = {"summary": response}

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "evaluation", "result_summary": f"评分:{evaluation_report.get('overall_score', 0)}"})

    return {
        "response": response,
        "evaluation_report": evaluation_report,
        "agent_feedback": {
            "weaknesses_found": evaluation_report.get("weaknesses", []),
            "task_completed": True,
        },
        "messages": [{"role": "assistant", "content": response}],
        "completed_tasks": completed,
    }
