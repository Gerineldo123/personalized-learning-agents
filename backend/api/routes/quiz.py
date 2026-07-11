from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from api.deps import get_db
from models.quiz_record import QuizRecord
from models.mistake_question import MistakeQuestion
from schemas.chat import QuizSubmitRequest
from services.event_service import emit
from services.profile_update_service import apply_quiz_result


class CodeJudgeRequest(BaseModel):
    question_id: int
    code: str
    test_cases: list[dict]
    code_lang: str = "python"

router = APIRouter(prefix="/api/quiz", tags=["答题"])


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _binding_kps(value) -> list[str]:
    bindings = value if isinstance(value, list) else []
    kps: list[str] = []
    for item in bindings:
        if isinstance(item, dict):
            kps.extend([str(kp).strip() for kp in _as_list(item.get("knowledge_points")) if str(kp).strip()])
    return list(dict.fromkeys(kps))


def _resource_binding_kps(resource) -> list[str]:
    content = resource.content if resource and isinstance(resource.content, dict) else {}
    return _binding_kps(content.get("course_bindings")) or _as_list(getattr(resource, "knowledge_points", []))


def _question_kps(question: dict, resource) -> list[str]:
    return (
        _binding_kps(question.get("course_bindings"))
        or _as_list(question.get("knowledge_points"))
        or _resource_binding_kps(resource)
    )


def _normalized_options(question: dict) -> list[dict]:
    raw_options = question.get("options") if isinstance(question.get("options"), list) else []
    normalized = []
    for index, option in enumerate(raw_options):
        fallback_key = chr(65 + index)
        if isinstance(option, str):
            text = option.strip()
            key = text[:1].upper() if text[:1].upper() in {"A", "B", "C", "D"} else fallback_key
            if key == text[:1].upper() and len(text) > 1 and text[1] in ".．、)） ":
                text = text[2:].strip()
            normalized.append({"key": key, "text": text, "label": f"{key}. {text}"})
        elif isinstance(option, dict):
            key = str(option.get("key") or fallback_key).strip().upper()[:1]
            text = str(option.get("text") or option.get("label") or "").strip()
            normalized.append({"key": key, "text": text, "label": f"{key}. {text}"})
    return [item for item in normalized if item.get("key") in {"A", "B", "C", "D"}]


def _choice_answer_key(question: dict) -> str:
    raw = str(question.get("answer") or "").strip()
    leading = raw[:1].upper()
    if leading in {"A", "B", "C", "D"}:
        return leading
    for option in _normalized_options(question):
        if raw in {option.get("text"), option.get("label")}:
            return str(option.get("key") or raw)
    return raw


def _is_wrong_answer(question: dict, user_ans: str) -> bool:
    q_type = str(question.get("type") or "single_choice").lower()
    if q_type in {"fill_blank", "short_answer"}:
        return user_ans.strip().lower() != str(question.get("answer") or "").strip().lower()
    if q_type == "coding":
        try:
            return float(user_ans) < 1.0
        except ValueError:
            return True
    return user_ans.strip().upper() != _choice_answer_key(question)


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
    question_kp_scores: dict[str, list[float]] = {}
    wrong_questions: list[dict] = []
    for q in questions:
        qid = q.get('id')
        if qid is None:
            continue
        qid_str = str(qid)
        user_ans = str(submitted_answers.get(qid_str, submitted_answers.get(qid, '')))
        correct_ans = str(q.get('answer', ''))
        is_wrong = _is_wrong_answer(q, user_ans)
        q_kps = _question_kps(q, resource)
        for kp in q_kps:
            if kp:
                question_kp_scores.setdefault(kp, []).append(0.0 if is_wrong else 1.0)
        if not user_ans or not is_wrong:
            continue
        wrong_questions.append({
            "question": q,
            "knowledge_points": q_kps,
            "user_answer": user_ans,
            "correct_answer": correct_ans,
        })
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

    # Prefer question-level graph tags; question helper already falls back to resource-level tags per question.
    kp_scores = {}
    if question_kp_scores:
        kp_scores = {
            kp: sum(scores) / max(len(scores), 1)
            for kp, scores in question_kp_scores.items()
        }

    if resource:
        resource.learning_status = "completed"
        resource.progress = 1.0
        resource.completed_at = datetime.utcnow()

    mastery_result = apply_quiz_result(
        db,
        req.user_id,
        kp_scores,
        wrong_questions,
        req.score,
        resource_id=req.resource_id,
    )

    updated_points = mastery_result.get("updated_knowledge_points", [])
    await emit("quiz.submitted", {
        "user_id": req.user_id,
        "resource_id": req.resource_id,
        "score": req.score,
        "mastery_updated": bool(updated_points),
        "updated_knowledge_points": updated_points,
    })

    return {
        "ok": True,
        "id": record.id,
        "score": req.score,
        "mastery_updated": bool(updated_points),
        "updated_knowledge_points": updated_points,
        "knowledge_mastery_delta": mastery_result.get("knowledge_mastery_delta", {}),
    }
