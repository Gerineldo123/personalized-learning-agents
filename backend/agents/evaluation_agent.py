import json
from datetime import datetime, timezone
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.student import StudentProfile
from models.resource import LearningResource
from models.course_path import CoursePath
from services.safety_service import check_text, hallu_rules

EVALUATION_PROMPT = """你是一个学习评估专家。根据学生的学习数据分析其掌握情况，并给出改进建议。

学生画像：{profile}
学习资源使用情况：{resources}
学习路径进度：{path_progress}
用户反馈：{feedback}

返回JSON格式：
{{
  "overall_score": 0.0-100.0,
  "strengths": ["已掌握的强项"],
  "weaknesses": ["薄弱环节"],
  "suggestions": ["具体改进建议"],
  "updated_knowledge_base": {{"学科": 0.0-1.0评分}},
  "next_goal": "建议的下一步学习目标",
  "summary": "综合评价文字"
}}
{hallu}
只返回JSON，不要其他内容。"""


class EvaluationAgent(BaseAgent):
    name = "evaluation"
    description = "评估学习效果并动态调整学习策略"

    async def process(self, state: AgentState) -> AgentState:
        user_id = state.user_id
        feedback = state.user_message
        db = SessionLocal()
        try:
            profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
            resources = db.query(LearningResource).filter(LearningResource.user_id == user_id).all()
            paths = db.query(CoursePath).filter(
                CoursePath.user_id == user_id,
                CoursePath.status.in_(["active", "completed"]),
            ).all()
            profile_text = self._profile_text(profile)
            resource_text = self._resources_summary(resources)
            path_text = self._path_progress_text(paths)
            resp = await chat_completion([
                {"role": "user", "content": EVALUATION_PROMPT.format(profile=profile_text, resources=resource_text, path_progress=path_text, feedback=feedback, hallu=hallu_rules())}
            ], temperature=0.4)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            report = json.loads(raw)
            if "summary" in report:
                safe_summary, _ = await check_text(report["summary"])
                report["summary"] = safe_summary
            if profile and report.get("updated_knowledge_base"):
                self._update_profile(profile, report["updated_knowledge_base"])
            self._save_evaluation(db, user_id, report)
            db.commit()
            self._try_emit_event("evaluation.completed", {"user_id": user_id, "overall_score": report.get("overall_score", 0)})
            state["response"] = json.dumps({
                "agent": self.name, "action": "evaluation_completed",
                "overall_score": report.get("overall_score", 0),
                "strengths": report.get("strengths", []),
                "weaknesses": report.get("weaknesses", []),
                "suggestions": report.get("suggestions", []),
                "summary": report.get("summary", ""),
            }, ensure_ascii=False)
            return state
        finally:
            db.close()

    def _profile_text(self, profile):
        if not profile:
            return "暂无画像"
        return json.dumps({"major": profile.major, "grade": profile.grade, "knowledge_base": profile.knowledge_base, "weak_points": profile.weak_points, "learning_goal": profile.learning_goal}, ensure_ascii=False)

    def _resources_summary(self, resources):
        if not resources:
            return "暂无学习资源"
        by_type = {}
        for r in resources:
            by_type[r.resource_type] = by_type.get(r.resource_type, 0) + 1
        return f"共{len(resources)}个资源：" + ", ".join(f"{t}:{c}个" for t, c in by_type.items())

    def _path_progress_text(self, paths):
        if not paths:
            return "暂无学习路径"
        total_paths = len(paths)
        total_steps = sum(len(p.steps or []) for p in paths)
        done_steps = sum(sum(1 for s in (p.steps or []) if s.get("status") == "done") for p in paths)
        return f"课程路径共{total_paths}条，步骤完成 {done_steps}/{total_steps}"

    def _update_profile(self, profile, kb):
        existing = profile.knowledge_base or {}
        merged = {}
        for key in set(existing) | set(kb):
            merged[key] = round((existing.get(key, 0) + kb.get(key, 0)) / 2, 2)
        profile.knowledge_base = merged
        profile.updated_at = datetime.now(timezone.utc)

    def _save_evaluation(self, db, user_id, report):
        resource = LearningResource(user_id=user_id, resource_type="evaluation", title=f"学习评估报告 ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})", content=report, tags=["evaluation"])
        db.add(resource)

    def _try_emit_event(self, event, data):
        import asyncio
        from services.event_service import emit
        asyncio.create_task(emit(event, data))


if __name__ == "__main__":
    import sys, asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    agent = EvaluationAgent()
    state = AgentState(user_id="test_user_1", user_message="学习了一段时间，感觉装饰器还是有些模糊")
    result = asyncio.run(agent.process(state))
    print(result.get("response", "")[:500])
