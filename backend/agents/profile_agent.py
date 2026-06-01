import json
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.student import StudentProfile
from models.quiz_record import QuizRecord
from models.conversation import Conversation, ChatMessage

EXTRACT_PROFILE_PROMPT = """你是一个学生画像分析专家。根据提供的多维数据，更新学生画像，只返回JSON：

数据来源：
- 当前画像：{old_profile}
- 对话历史摘要：{chat_summary}
- 答题统计：{quiz_stats}

{{
  "major": "专业名称",
  "grade": "年级",
  "knowledge_base": {{"学科": 0.0-1.0评分}},
  "cognitive_style": "视觉型/听觉型/实践型",
  "weak_points": ["薄弱知识点"],
  "learning_goal": "学习目标描述",
  "preferred_format": ["偏好资源格式"]
}}

规则：
- knowledge_base 评分基于答题正确率：全对→0.9+，全错→0.1-，无数据保持原值
- weak_points 根据答题错误和对话中的困惑抽取
- 已有画像中非空字段保留，新分析仅在置信度高时覆盖
- 只返回JSON，不要其他内容"""


class ProfileAgent(BaseAgent):
    name = "profile"
    description = "通过对话构建和更新学生学习画像"

    async def process(self, state: AgentState) -> AgentState:
        user_id = state.user_id

        db = SessionLocal()
        try:
            old_profile = db.query(StudentProfile).filter(
                StudentProfile.user_id == user_id
            ).first()

            quiz_stats = self._get_quiz_stats(db, user_id)
            chat_summary = self._get_chat_summary(db, user_id)

            resp = await chat_completion([
                {"role": "system", "content": EXTRACT_PROFILE_PROMPT.format(
                    old_profile=self._profile_json(old_profile),
                    chat_summary=chat_summary,
                    quiz_stats=quiz_stats,
                )},
                {"role": "user", "content": state.user_message}
            ], temperature=0.3)

            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            extracted = json.loads(raw)

            if old_profile:
                self._merge_profile(old_profile, extracted)
            else:
                old_profile = StudentProfile(user_id=user_id, **extracted)
                db.add(old_profile)

            db.commit()
            db.refresh(old_profile)

            state["response"] = json.dumps({
                "agent": self.name,
                "action": "profile_updated",
                "profile": self._profile_dict(old_profile),
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
            wp = list(set((profile.weak_points or []) + extracted["weak_points"]))
            profile.weak_points = wp
        if extracted.get("learning_goal"):
            profile.learning_goal = extracted["learning_goal"]
        if extracted.get("preferred_format"):
            pf = list(set((profile.preferred_format or []) + extracted["preferred_format"]))
            profile.preferred_format = pf


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
