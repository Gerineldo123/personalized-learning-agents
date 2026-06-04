import json
from graph.state import AgentGraphState
from core.llm_client import chat_completion

PATH_PROMPT = """你是一个学习规划专家。根据评估结果和学生画像，建议下一步学习路径。

评估报告：{report}
学生画像：{profile}

返回简洁的学习路径建议（3-5 条），每条包含知识点和建议学习方式。"""


async def path_suggest_node(state: AgentGraphState) -> dict:
    report = state.get("evaluation_report", {})
    profile = state.get("profile")

    profile_text = json.dumps({
        "major": getattr(profile, "major", ""),
        "weak_points": getattr(profile, "weak_points", []),
        "learning_goal": getattr(profile, "learning_goal", ""),
    }, ensure_ascii=False) if profile else "暂无"

    resp = await chat_completion([
        {"role": "user", "content": PATH_PROMPT.format(
            report=json.dumps(report, ensure_ascii=False),
            profile=profile_text,
        )}
    ], temperature=0.5)

    suggestion = resp.choices[0].message.content

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "path_suggest", "result_summary": "生成学习路径建议"})

    return {
        "path_suggestion": suggestion,
        "response": suggestion,
        "agent_feedback": {"task_completed": True},
        "completed_tasks": completed,
    }
