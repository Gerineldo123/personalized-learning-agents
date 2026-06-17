from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_agent = ContentGenAgent()


async def quiz_gen_node(state: AgentGraphState) -> dict:
    analysis = state.get("profile_analysis", {})
    level = analysis.get("current_level", "中级")
    difficulty_map = {"初级": "简单", "中级": "中等", "高级": "困难"}

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        resource_type="quiz",
        difficulty=difficulty_map.get(level, "中等"),
        question_count=5,
    )
    result = await _content_agent.process(agent_state)
    quiz = result.get("response", "")
    resource_db_id = result.get("resource_db_id")

    outputs = list(state.get("workflow_outputs") or [])
    outputs.append({"stage": "quiz", "data": quiz, "resource_db_id": resource_db_id, "resource_type": "quiz", "title": state["user_message"]})

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "quiz_gen", "result_summary": "生成练习题"})

    return {
        "generated_quiz": quiz,
        "agent_feedback": {
            "quiz_generated": bool(quiz),
            "quiz_difficulty": difficulty_map.get(level, "中等"),
            "all_tasks_done": True,
            "task_completed": True,
        },
        "workflow_outputs": outputs,
        "completed_tasks": completed,
    }
