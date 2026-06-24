from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from api.deps import get_db
from models.mistake_question import MistakeQuestion
from models.student import StudentProfile
from models.resource import LearningResource
from core.llm_client import chat_completion
import json

router = APIRouter(prefix="/api/mistakes", tags=["错题本"])


@router.get("")
def list_mistakes(user_id: str, sort: str = "time", order: str = "desc", db: Session = Depends(get_db)):
    q = (
        db.query(MistakeQuestion, LearningResource.title)
        .outerjoin(LearningResource, MistakeQuestion.resource_id == LearningResource.id)
        .filter(MistakeQuestion.user_id == user_id)
    )
    desc = order != "asc"
    if sort == "count":
        col1 = MistakeQuestion.wrong_count
        col2 = func.coalesce(MistakeQuestion.last_wrong_at, MistakeQuestion.created_at)
    else:
        col1 = func.coalesce(MistakeQuestion.last_wrong_at, MistakeQuestion.created_at)
        col2 = MistakeQuestion.id
    if desc:
        q = q.order_by(col1.desc(), col2.desc())
    else:
        q = q.order_by(col1.asc(), col2.asc())
    rows = q.limit(500).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": x.id,
                "resource_id": x.resource_id,
                "resource_title": resource_title or "",
                "question_id": x.question_id,
                "reason": x.reason,
                "question": x.question,
                "user_answer": x.user_answer,
                "correct_answer": x.correct_answer,
                "wrong_count": x.wrong_count or 1,
                "created_at": x.created_at.isoformat() if x.created_at else None,
                "last_wrong_at": (x.last_wrong_at or x.created_at).isoformat() if (x.last_wrong_at or x.created_at) else None,
            }
            for x, resource_title in rows
        ],
    }


@router.post("/add")
def add_mistake(
    user_id: str,
    resource_id: int,
    question_id: int,
    reason: str,
    question: str,
    user_answer: str,
    correct_answer: str,
    db: Session = Depends(get_db),
):
    import json

    exists = (
        db.query(MistakeQuestion)
        .filter(
            MistakeQuestion.user_id == user_id,
            MistakeQuestion.resource_id == resource_id,
            MistakeQuestion.question_id == question_id,
        )
        .first()
    )
    if exists:
        exists.reason = reason
        exists.question = json.loads(question)
        exists.user_answer = user_answer
        exists.correct_answer = correct_answer
        exists.wrong_count = (exists.wrong_count or 1) + 1
        exists.last_wrong_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(exists)
        return {"ok": True, "id": exists.id, "updated": True}

    item = MistakeQuestion(
        user_id=user_id,
        resource_id=resource_id,
        question_id=question_id,
        reason=reason,
        question=json.loads(question),
        user_answer=user_answer,
        correct_answer=correct_answer,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"ok": True, "id": item.id, "updated": False}


@router.post("/{mistake_id}/redo-incorrect")
def redo_incorrect(mistake_id: int, user_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(MistakeQuestion)
        .filter(MistakeQuestion.id == mistake_id, MistakeQuestion.user_id == user_id)
        .first()
    )
    if not item:
        return {"ok": False, "error": "错题不存在"}
    item.wrong_count = (item.wrong_count or 1) + 1
    db.commit()
    return {"ok": True, "wrong_count": item.wrong_count}


@router.delete("/{mistake_id}")
def delete_mistake(mistake_id: int, user_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(MistakeQuestion)
        .filter(MistakeQuestion.id == mistake_id, MistakeQuestion.user_id == user_id)
        .first()
    )
    if not item:
        return {"ok": True, "deleted": False}
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted": True}


@router.delete("")
def clear_mistakes(user_id: str, db: Session = Depends(get_db)):
    n = db.query(MistakeQuestion).filter(MistakeQuestion.user_id == user_id).delete()
    db.commit()
    return {"ok": True, "deleted": n}


MISTAKE_ANALYZE_PROMPT = """你是一位学习分析导师。请分析学生的错题，找出知识薄弱点。

题目：{question}
正确答案：{correct}
学生答案：{student}

{is_wrong}

请以JSON格式返回（只返回JSON，不要其他文字）：
{{
  "error_analysis": "学生错误原因分析（50字以内，如果答对了这部分写'无'）",
  "confused_points": ["混淆的知识点1", "混淆的知识点2"],
  "weak_points": ["未掌握的知识点1", "未掌握的知识点2"],
  "key_concepts": ["本题涉及的核心知识点"]
}}
"""


@router.post("/{mistake_id}/analyze")
async def analyze_mistake(mistake_id: int, user_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(MistakeQuestion)
        .filter(MistakeQuestion.id == mistake_id, MistakeQuestion.user_id == user_id)
        .first()
    )
    if not item:
        return {"ok": False, "error": "错题不存在"}

    if item.analysis:
        return {"ok": True, "analysis": item.analysis}

    question_text = item.question.get("question", "") if item.question else ""
    correct = item.correct_answer or ""
    student = item.user_answer or ""
    is_wrong = "学生答错了，请分析错误原因。" if correct != student else "学生答对了，只需列出本题核心知识点。"

    prompt = MISTAKE_ANALYZE_PROMPT.format(
        question=question_text,
        correct=correct,
        student=student,
        is_wrong=is_wrong,
    )

    resp = await chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
    try:
        result = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        text = resp.choices[0].message.content.strip()
        text = text[text.find("{"):text.rfind("}")+1] if "{" in text and "}" in text else text
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {
                "error_analysis": "分析生成失败",
                "confused_points": [],
                "weak_points": [],
                "key_concepts": [],
            }

    item.analysis = result
    db.commit()

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if profile and result.get("weak_points"):
        from services.recommendation_service import upsert_weak_points_batch
        upsert_weak_points_batch(user_id, result["weak_points"])
        existing = list(profile.weak_points or [])
        for pt in result["weak_points"]:
            if pt not in existing:
                existing.append(pt)
        profile.weak_points = existing[-10:]
        db.commit()

    return {"ok": True, "analysis": result}


SIMILAR_PROMPT = """你是一位出题老师。请根据以下错题，出2道类似的练习题帮学生巩固。

原题：{question}
正确答案：{correct}
相关知识点：{concepts}

要求：
1. 题目类型和难度与原题保持一致
2. 用不同的具体数值或场景
3. 每道题包含题目、4个选项（A/B/C/D）、正确答案、每个选项的解析（说明为什么对/错）
4. 返回JSON：{{"problems": [{{"question": "题目", "options": ["A. xx", "B. xx", "C. xx", "D. xx"], "correct": "A", "explanation": "总解析", "option_explanations": {{"A": "A选项解析","B": "B选项解析","C": "C选项解析","D": "D选项解析"}}}}]}}
"""


@router.post("/{mistake_id}/similar")
async def get_similar_problems(mistake_id: int, user_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(MistakeQuestion)
        .filter(MistakeQuestion.id == mistake_id, MistakeQuestion.user_id == user_id)
        .first()
    )
    if not item:
        return {"ok": False, "error": "错题不存在"}

    question_text = item.question.get("question", "") if item.question else ""
    correct = item.correct_answer or ""
    concepts = "、".join((item.question.get("explanation", "")[:50] if item.question else "").split("。")[:2])

    prompt = SIMILAR_PROMPT.format(
        question=question_text,
        correct=correct,
        concepts=concepts or "未指定",
    )

    resp = await chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
    try:
        result = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        text = resp.choices[0].message.content.strip()
        text = text[text.find("{"):text.rfind("}")+1] if "{" in text and "}" in text else text
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {"problems": []}

    return {"ok": True, "problems": result.get("problems", [])}


class SimilarAnalyzeRequest(BaseModel):
    user_id: str
    question: str = ""
    correct_answer: str = ""
    user_answer: str = ""


@router.post("/analyze-similar")
async def analyze_similar_mistake(req: SimilarAnalyzeRequest, db: Session = Depends(get_db)):
    prompt = MISTAKE_ANALYZE_PROMPT.format(
        question=req.question,
        correct=req.correct_answer,
        student=req.user_answer,
        is_wrong="学生答错了，请分析错误原因。",
    )

    resp = await chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
    try:
        result = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        text = resp.choices[0].message.content.strip()
        text = text[text.find("{"):text.rfind("}")+1] if "{" in text and "}" in text else text
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {"error_analysis": "分析失败", "weak_points": [], "confused_points": [], "key_concepts": []}

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == req.user_id).first()
    if profile and result.get("weak_points"):
        from services.recommendation_service import upsert_weak_points_batch
        upsert_weak_points_batch(req.user_id, result["weak_points"])
        existing = list(profile.weak_points or [])
        for pt in result["weak_points"]:
            if pt not in existing:
                existing.append(pt)
        profile.weak_points = existing[-10:]
        db.commit()

    return {"ok": True, "analysis": result}
