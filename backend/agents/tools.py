from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable


def search_learning_resources(query: str, user_id: str) -> list[dict]:
    from services.rag_service import search_rag
    result = search_rag(query, user_id, top_k=3)
    docs = result.get("documents", [])
    ids = result.get("ids", [])
    return [{"content": d[:500], "id": i} for d, i in zip(docs, ids)]


def query_mistake_history(user_id: str, topic: str = "") -> list[dict]:
    from core.database import SessionLocal
    from models.mistake_question import MistakeQuestion
    db = SessionLocal()
    try:
        q = db.query(MistakeQuestion).filter(MistakeQuestion.user_id == user_id)
        records = q.order_by(MistakeQuestion.created_at.desc()).limit(20).all()
        return [{"question": r.question, "user_answer": r.user_answer, "correct_answer": r.correct_answer} for r in records]
    finally:
        db.close()


def get_student_profile(user_id: str) -> dict:
    from core.database import SessionLocal
    from models.student import StudentProfile
    db = SessionLocal()
    try:
        p = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        if not p:
            return {}
        return {"major": p.major, "grade": p.grade, "knowledge_base": p.knowledge_base,
                "weak_points": p.weak_points, "learning_goal": p.learning_goal}
    finally:
        db.close()


TOOLS = [
    Tool("search_resources", "搜索学习资源库", search_learning_resources),
    Tool("query_mistakes", "查询学生错题记录", query_mistake_history),
    Tool("get_profile", "获取学生画像", get_student_profile),
]

TOOL_MAP = {t.name: t.handler for t in TOOLS}
TOOL_DESC = "\n".join([f"- {t.name}: {t.description}" for t in TOOLS])
