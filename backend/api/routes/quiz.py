from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.deps import get_db
from models.quiz_record import QuizRecord
from models.mistake_question import MistakeQuestion
from schemas.chat import QuizSubmitRequest
from services.event_service import emit


class CodeJudgeRequest(BaseModel):
    question_id: int
    code: str
    test_cases: list[dict]
    code_lang: str = "python"

router = APIRouter(prefix="/api/quiz", tags=["答题"])


@router.post("/judge")
async def judge_code(req: CodeJudgeRequest):
    """执行编程题代码，返回测试用例通过情况"""
    from utils.code_runner import run_code_against_tests
    result = run_code_against_tests(req.code, req.test_cases, req.code_lang)
    return result


@router.get("/records")
def get_records(user_id: str, db: Session = Depends(get_db)):
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.user_id == user_id)
        .order_by(QuizRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "resource_id": r.resource_id,
                "score": r.score,
                "time_spent": r.time_spent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }


@router.get("/stats")
def get_quiz_stats(user_id: str, db: Session = Depends(get_db)):
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.user_id == user_id)
        .all()
    )
    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "avg_score": 0,
            "avg_score_percent": 0,
            "latest_score": None,
            "latest_score_percent": None,
        }

    avg_score = sum(r.score for r in records) / total
    latest = max(records, key=lambda r: r.created_at)
    latest_score = latest.score if latest else None

    return {
        "total": total,
        "avg_score": avg_score,
        "avg_score_percent": round(avg_score * 100, 2),
        "latest_score": latest_score,
        "latest_score_percent": round(latest_score * 100, 2) if latest_score is not None else None,
    }


@router.get("/latest")
def get_latest_record(user_id: str, resource_id: int, db: Session = Depends(get_db)):
    r = (
        db.query(QuizRecord)
        .filter(
            QuizRecord.user_id == user_id,
            QuizRecord.resource_id == resource_id,
        )
        .order_by(QuizRecord.created_at.desc())
        .first()
    )
    if not r:
        return {"found": False}
    return {
        "found": True,
        "record": {
            "id": r.id,
            "resource_id": r.resource_id,
            "answers": r.answers,
            "score": r.score,
            "time_spent": r.time_spent,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        },
    }


@router.post("/submit")
async def submit_quiz(
    req: QuizSubmitRequest,
    db: Session = Depends(get_db),
):
    record = QuizRecord(
        user_id=req.user_id,
        resource_id=req.resource_id,
        answers=req.answers,
        score=req.score,
        time_spent=req.time_spent,
    )
    db.add(record)
    db.commit()

    # auto add wrong answers to mistake book
    questions = []
    resource = None
    try:
        from models.resource import LearningResource
        resource = db.query(LearningResource).filter(LearningResource.id == req.resource_id).first()
        questions = (resource.content or {}).get('questions', []) if resource else []
    except Exception:
        questions = []

    submitted_answers = record.answers or {}
    for q in questions:
        qid = q.get('id')
        if qid is None:
            continue
        qid_str = str(qid)
        user_ans = str(submitted_answers.get(qid_str, submitted_answers.get(qid, '')))
        correct_ans = str(q.get('answer', ''))
        q_type = q.get('type', 'single_choice')
        # fill_blank: case-insensitive strip comparison
        if q_type == 'fill_blank':
            is_wrong = user_ans.strip().lower() != correct_ans.strip().lower()
        elif q_type == 'coding':
            # coding answers stored as score ratio string like "0.5"; treat <1.0 as wrong
            try:
                is_wrong = float(user_ans) < 1.0
            except ValueError:
                is_wrong = True
        else:
            is_wrong = user_ans != correct_ans
        if not user_ans or not is_wrong:
            continue
        exists = (
            db.query(MistakeQuestion)
            .filter(
                MistakeQuestion.user_id == req.user_id,
                MistakeQuestion.resource_id == req.resource_id,
                MistakeQuestion.question_id == int(qid),
            )
            .first()
        )
        if exists:
            exists.reason = 'auto_wrong'
            exists.question = q
            exists.user_answer = user_ans
            exists.correct_answer = correct_ans
        else:
            db.add(MistakeQuestion(
                user_id=req.user_id,
                resource_id=req.resource_id,
                question_id=int(qid),
                reason='auto_wrong',
                question=q,
                user_answer=user_ans,
                correct_answer=correct_ans,
            ))
    db.commit()

    await emit("quiz.submitted", {
        "user_id": req.user_id,
        "resource_id": req.resource_id,
        "score": req.score,
    })

    # 方案二：从 resource.title + tags 匹配知识点，滑动平均更新掌握度
    from services.kp_service import match_kp, update_knowledge_base
    kp_text = (resource.title or "") + " " + " ".join(resource.tags or []) if resource else ""
    matched_kps = match_kp(kp_text)
    if matched_kps:
        update_knowledge_base(db, req.user_id, {kp: req.score for kp in matched_kps})

    # 异步更新画像：根据最新答题情况重新分析知识水平和薄弱点
    import asyncio as _asyncio
    from agents.profile_agent import ProfileAgent
    from agents.base import AgentState as _AgentState
    _asyncio.create_task(ProfileAgent().process(_AgentState(
        user_id=req.user_id,
        user_message=f"根据最新答题更新画像（本次得分：{req.score:.0%}）",
    )))

    return {"ok": True, "id": record.id}
