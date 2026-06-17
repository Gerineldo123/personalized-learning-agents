import json
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.student import StudentProfile
from models.quiz_record import QuizRecord
from models.conversation import Conversation, ChatMessage
from models.profile_history import ProfileHistory

EXTRACT_PROFILE_PROMPT = """你是一个学生画像分析专家。根据提供的多维数据，更新学生画像，只返回JSON：

数据来源：
- 当前画像：{old_profile}
- 对话历史摘要：{chat_summary}
- 答题统计：{quiz_stats}
- 专注行为数据：{focus_stats}

{{
  "major": "专业名称",
  "grade": "年级",
  "knowledge_base": {{"学科": 0.0-1.0评分}},
  "cognitive_style": "视觉型/听觉型/实践型",
  "weak_points": ["薄弱知识点"],
  "learning_goal": "学习目标描述",
  "preferred_format": ["偏好资源格式"],
  "focus_stamina_score": 1-10,
  "focus_peak_hours": [9, 10, 15],
  "focus_interrupt_rate": 0.0-1.0
}}

规则：
- knowledge_base 评分基于答题正确率：全对→0.9+，全错→0.1-，无数据保持原值
- weak_points 根据答题错误和对话中的困惑抽取
- focus_stamina_score: 周均>300分钟且中断率<10%→8-10；周均100-300分钟→5-7；周均<100分钟或中断率>30%→1-4；无数据不填
- focus_peak_hours: 从专注数据的高效时段直接取值，无数据不填
- focus_interrupt_rate: 从专注数据的中断率直接取值，无数据不填
- 已有画像中非空字段保留，新分析仅在置信度高时覆盖
- 只返回JSON，不要其他内容"""


class ProfileAgent(BaseAgent):
    name = "profile"
    description = "通过对话构建和更新学生学习画像"

    async def process(self, state: AgentState, trigger: str = "chat") -> AgentState:
        user_id = state.user_id

        db = SessionLocal()
        try:
            old_profile = db.query(StudentProfile).filter(
                StudentProfile.user_id == user_id
            ).first()

            quiz_stats = self._get_quiz_stats(db, user_id)
            chat_summary = self._get_chat_summary(db, user_id)
            focus_stats = self._get_focus_stats(db, user_id)

            resp = await chat_completion([
                {"role": "system", "content": EXTRACT_PROFILE_PROMPT.format(
                    old_profile=self._profile_json(old_profile),
                    chat_summary=chat_summary,
                    quiz_stats=quiz_stats,
                    focus_stats=focus_stats,
                )},
                {"role": "user", "content": state.user_message}
            ], temperature=0.3)

            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            extracted = json.loads(raw)

            old_snapshot = self._profile_dict(old_profile) if old_profile else {}

            if old_profile:
                self._merge_profile(old_profile, extracted)
            else:
                safe = {k: v for k, v in extracted.items() if k in (
                    "major", "grade", "knowledge_base", "cognitive_style",
                    "weak_points", "learning_goal", "preferred_format",
                )}
                old_profile = StudentProfile(user_id=user_id, **safe)
                self._merge_profile(old_profile, extracted)
                db.add(old_profile)

            db.commit()
            db.refresh(old_profile)

            # 写历史快照（记录本次变化的维度）
            new_snapshot = self._profile_dict(old_profile)
            delta = {
                k: {"from": old_snapshot.get(k), "to": new_snapshot.get(k)}
                for k in ("knowledge_base", "weak_points", "ability_scores",
                          "focus_stamina_score", "cognitive_style")
                if old_snapshot.get(k) != new_snapshot.get(k)
            }
            db.add(ProfileHistory(
                user_id=user_id,
                trigger=trigger,
                snapshot={
                    "ability_scores": new_snapshot.get("ability_scores") or {},
                    "knowledge_base": new_snapshot.get("knowledge_base") or {},
                    "weak_points": new_snapshot.get("weak_points") or [],
                    "focus_stamina_score": new_snapshot.get("focus_stamina_score"),
                },
                delta=delta,
            ))
            db.commit()

            state["response"] = json.dumps({
                "agent": self.name,
                "action": "profile_updated",
                "profile": new_snapshot,
            }, ensure_ascii=False)
            state["profile"] = old_profile

            import asyncio as _asyncio
            from services.event_service import emit as _emit
            _asyncio.create_task(_emit("profile.updated", {"user_id": user_id}))

            return state
        finally:
            db.close()

    def _get_chat_summary(self, db, user_id: str) -> str:
        convs = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.updated_at.desc()).limit(10).all()
        if not convs:
            return "暂无对话记录"
        parts = []
        for conv in convs:
            msgs = db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv.id
            ).order_by(ChatMessage.created_at.asc()).limit(20).all()
            for m in msgs:
                prefix = "用户" if m.role == "user" else "助手"
                parts.append(f"{prefix}: {m.content[:200]}")
        return "\n".join(parts[-50:]) if parts else "暂无对话记录"

    def _get_quiz_stats(self, db, user_id: str) -> str:
        records = db.query(QuizRecord).filter(
            QuizRecord.user_id == user_id
        ).order_by(QuizRecord.created_at.desc()).limit(50).all()
        if not records:
            return "暂无答题记录"
        total = len(records)
        avg_score = sum(r.score for r in records) / max(total, 1)
        return f"共{total}次答题，平均正确率{avg_score:.0%}"

    def _get_focus_stats(self, db, user_id: str) -> str:
        from models.focus import FocusSession
        from collections import Counter

        sessions = (
            db.query(FocusSession)
            .filter(FocusSession.user_id == user_id)
            .order_by(FocusSession.started_at.desc())
            .all()
        )
        if not sessions:
            return "暂无专注记录"

        total = len(sessions)
        completed = sum(1 for s in sessions if s.completed)
        total_min = sum(s.duration_min for s in sessions)
        interrupt_rate = round((total - completed) / total * 100, 1)

        hour_counts = Counter(s.started_at.hour for s in sessions if s.completed)
        peak_hours = sorted([h for h, _ in hour_counts.most_common(3)])

        return json.dumps({
            "总专注次数": total,
            "完成次数": completed,
            "中断率": f"{interrupt_rate}%",
            "累计专注分钟": total_min,
            "高效时段(小时)": peak_hours,
        }, ensure_ascii=False)

    def _profile_json(self, p: StudentProfile | None) -> str:
        if not p:
            return "{}"
        return json.dumps(self._profile_dict(p), ensure_ascii=False)

    def _profile_dict(self, p: StudentProfile) -> dict:
        return {
            "major": p.major or "",
            "grade": p.grade or "",
            "knowledge_base": p.knowledge_base or {},
            "cognitive_style": p.cognitive_style or "",
            "weak_points": p.weak_points or [],
            "learning_goal": p.learning_goal or "",
            "preferred_format": p.preferred_format or [],
            "focus_stamina_score": p.focus_stamina_score,
            "focus_peak_hours": p.focus_peak_hours or [],
            "focus_interrupt_rate": p.focus_interrupt_rate,
            "focus_weekly_avg_min": p.focus_weekly_avg_min,
        }

    def _merge_profile(self, profile: StudentProfile, extracted: dict):
        if extracted.get("major"):
            profile.major = extracted["major"]
        if extracted.get("grade"):
            profile.grade = extracted["grade"]
        if extracted.get("knowledge_base"):
            kb = {**(profile.knowledge_base or {}), **extracted["knowledge_base"]}
            profile.knowledge_base = kb
        if extracted.get("cognitive_style"):
            profile.cognitive_style = extracted["cognitive_style"]
        if extracted.get("weak_points"):
            from services.recommendation_service import upsert_weak_points_batch
            upsert_weak_points_batch(profile.user_id, extracted["weak_points"])
            profile.weak_points = list(set((profile.weak_points or []) + extracted["weak_points"]))[-15:]
        if extracted.get("learning_goal"):
            profile.learning_goal = extracted["learning_goal"]
        if extracted.get("preferred_format"):
            pf = list(set((profile.preferred_format or []) + extracted["preferred_format"]))
            profile.preferred_format = pf
        if extracted.get("focus_stamina_score") is not None:
            profile.focus_stamina_score = extracted["focus_stamina_score"]
        if extracted.get("focus_peak_hours"):
            profile.focus_peak_hours = extracted["focus_peak_hours"]
        if extracted.get("focus_interrupt_rate") is not None:
            profile.focus_interrupt_rate = extracted["focus_interrupt_rate"]


if __name__ == "__main__":
    import sys
    import asyncio

    sys.stdout.reconfigure(encoding="utf-8")
    agent = ProfileAgent()
    state = AgentState(
        user_id="test",
        user_message="我是大二计算机专业，Python基础不错但机器学习完全没接触过"
    )
    result = asyncio.run(agent.process(state))
    print(result.get("response", ""))
