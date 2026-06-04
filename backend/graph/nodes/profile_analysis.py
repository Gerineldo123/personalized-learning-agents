import json
from graph.state import AgentGraphState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.student import StudentProfile

ANALYSIS_PROMPT = """你是一个学习诊断专家。根据学生画像，分析其当前知识水平并给出学习建议。

学生画像：{profile}
学习主题：{topic}

返回JSON：
{{
  "current_level": "初级/中级/高级",
  "relevant_knowledge": ["已掌握的相关知识点"],
  "gaps": ["需要补充的前置知识"],
  "recommended_depth": "入门/进阶/深入",
  "focus_points": ["建议重点学习的方面"]
}}
只返回JSON。"""


async def profile_analysis_node(state: AgentGraphState) -> dict:
    profile = state.get("profile")
    profile_text = json.dumps({
        "major": getattr(profile, "major", "未知"),
        "grade": getattr(profile, "grade", "未知"),
        "knowledge_base": getattr(profile, "knowledge_base", {}),
        "weak_points": getattr(profile, "weak_points", []),
    }, ensure_ascii=False) if profile else "暂无画像"

    resp = await chat_completion([
        {"role": "user", "content": ANALYSIS_PROMPT.format(
            profile=profile_text, topic=state["user_message"]
        )}
    ], temperature=0.3)

    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        analysis = {
            "current_level": "中级",
            "relevant_knowledge": [],
            "gaps": [],
            "recommended_depth": "进阶",
            "focus_points": [],
        }

    # 将分析出的 gaps 持久化到 StudentProfile.weak_points
    gaps = analysis.get("gaps", [])
    if gaps and profile:
        db = SessionLocal()
        try:
            p = db.query(StudentProfile).filter(
                StudentProfile.user_id == state["user_id"]
            ).first()
            if p:
                existing = set(p.weak_points or [])
                existing.update(gaps)
                p.weak_points = list(existing)
                db.commit()
        finally:
            db.close()

    completed = list(state.get("completed_tasks") or [])
    completed.append({"agent": "profile_analysis", "result_summary": f"水平:{analysis.get('current_level','未知')}"})

    return {
        "profile_analysis": analysis,
        "agent_feedback": {"level": analysis.get("current_level"), "gaps": gaps, "task_completed": True},
        "workflow_outputs": [{"stage": "profile_analysis", "data": analysis}],
        "completed_tasks": completed,
    }
