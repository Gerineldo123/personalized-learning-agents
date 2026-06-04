from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_agent = ContentGenAgent()


async def study_content_node(state: AgentGraphState) -> dict:
    analysis = state.get("profile_analysis", {})
    mistake = state.get("mistake_analysis", {})

    # 联动：合并 profile_analysis + mistake_analysis + profile 的薄弱点
    profile = state.get("profile")
    profile_weak = list(getattr(profile, "weak_points", None) or [])
    mistake_weak = list(mistake.get("weak_topics", []))
    all_weak = list(dict.fromkeys(mistake_weak + profile_weak))  # 去重保序

    if analysis:
        depth = analysis.get("recommended_depth", "进阶")
        focus_points = analysis.get("focus_points", [])
        gaps = analysis.get("gaps", [])
        focus = "、".join(all_weak + [p for p in focus_points if p not in all_weak]) or "全面覆盖"
    elif mistake:
        depth = "进阶"
        gaps = []
        focus = "、".join(all_weak) or mistake.get("priority_topic", "全面覆盖")
    else:
        depth = "进阶"
        gaps = []
        focus = "、".join(all_weak) or "全面覆盖"

    enhanced_message = (
        f"{state['user_message']}（难度：{depth}，"
        f"重点关注：{focus or '全面覆盖'}）"
    )

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=enhanced_message,
        profile=state.get("profile"),
        resource_type="article",
    )
    result = await _content_agent.process(agent_state)
    article = result.get("response", "")

    feedback = {
        "content_generated": bool(article),
        "content_quality": _estimate_quality(article),
        "needs_regeneration": len(article) < 100,
        "needs_mindmap": depth in ("入门", "进阶"),
        "gaps_in_content": gaps,
        "task_completed": True,
    }

    outputs = list(state.get("workflow_outputs") or [])
    outputs.append({"stage": "content_gen", "data": article})

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "study_content", "result_summary": f"生成 {len(article)} 字{depth}级别内容"})

    return {
        "generated_article": article,
        "agent_feedback": feedback,
        "workflow_outputs": outputs,
        "completed_tasks": completed,
    }


def _estimate_quality(text: str) -> float:
    if not text:
        return 0.0
    score = 0.5
    if len(text) > 200:
        score += 0.2
    if "##" in text:
        score += 0.15
    if len(text) > 500:
        score += 0.1
    return min(score, 1.0)
