import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from core.database import SessionLocal
from models.profile_history import ProfileHistory
from models.profile_onboarding import ProfileOnboardingSession
from models.student import StudentProfile
from schemas.student import ProfileResponse
from services.curriculum_service import (
    get_course_kp_graph,
    infer_current_semester,
    load_curriculum_by_major,
    semester_rank,
)
from services.event_service import emit
from services.micro_quiz_service import generate_micro_quiz
from services.profile_update_service import apply_quiz_result

router = APIRouter(prefix="/api/profile/onboarding", tags=["对话式画像建档"])

INTERVIEW_QUESTIONS = [
    "你这阶段最想解决的学习目标是什么？例如通过考试、补基础、做项目或准备竞赛。",
    "过去学习这些课程时，哪些内容让你最卡住？可以说具体概念、题型或实验。",
    "你更喜欢哪类学习资源？例如图解、短视频、PPT、文章、代码案例或题库。",
    "你通常什么时候学习效率最高？一次能保持多久专注？",
    "你做题或实践时最常见的问题是什么？例如记不住、没思路、看懂但不会做。",
    "如果系统接下来给你安排学习资源，你希望节奏偏基础巩固、快速提分还是项目实战？",
]


class OnboardingStartRequest(BaseModel):
    user_id: str
    course_names: list[str] = Field(default_factory=list)
    mode: str = "first_build"


class OnboardingAnswerRequest(BaseModel):
    session_id: str
    step: str
    payload: dict[str, Any] = Field(default_factory=dict)


class OnboardingFinishRequest(BaseModel):
    session_id: str


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _course_priority(course: dict, current_semester: int) -> tuple[int, float]:
    rank = semester_rank(course.get("semester"))
    if rank == current_semester:
        return (0, rank)
    if 0 < rank < current_semester:
        return (1, -rank)
    return (2, rank or 99)


def _safe_kp_graph(course_name: str, major: str = "") -> dict:
    try:
        return get_course_kp_graph(course_name, major)
    except Exception:
        return {"nodes": [], "links": [], "categories": []}


def _available_courses(profile: StudentProfile | None) -> list[dict]:
    if not profile or not profile.major:
        return []
    curriculum = load_curriculum_by_major(profile.major if profile else "")
    current_semester = infer_current_semester(
        profile.grade if profile else "",
        profile.current_semester if profile else None,
    )
    available = []
    for course in curriculum.get("courses", []):
        if not course.get("kp_file"):
            continue
        graph = _safe_kp_graph(course.get("name") or "", profile.major if profile else "")
        kps = [node.get("id") for node in graph.get("nodes", []) if node.get("id")]
        if not kps:
            continue
        item = {
            "course_id": course.get("id"),
            "course_name": course.get("name"),
            "semester": course.get("semester"),
            "category": course.get("category"),
            "module": course.get("module"),
            "kp_file": course.get("kp_file"),
            "kp_count": len(kps),
            "priority": _course_priority(course, current_semester)[0],
        }
        available.append(item)
    available.sort(key=lambda item: (item["priority"], semester_rank(item.get("semester"))))
    return available


def _is_correct(question: dict, answer: Any) -> bool:
    value = str(answer or "").strip()
    correct = str(question.get("answer") or "").strip()
    if value == correct:
        return True
    options = question.get("options") or []
    for option in options:
        if option.get("key") == correct and value == option.get("text"):
            return True
    return False


def _answer_score(question: dict, answer: Any) -> float:
    return 1.0 if _is_correct(question, answer) else 0.0


def _diagnose(micro_quiz: dict, answers: dict) -> dict:
    kp_scores: dict[str, float] = {}
    course_scores: dict[str, list[float]] = defaultdict(list)
    wrong_points: list[str] = []
    wrong_courses: dict[str, list[str]] = defaultdict(list)
    details = []

    for question in micro_quiz.get("questions", []):
        qid = str(question.get("id"))
        course = question.get("course_name") or ""
        kp = question.get("knowledge_point") or ""
        score = _answer_score(question, answers.get(qid))
        correct = score >= 0.6
        if kp:
            kp_scores[kp] = score
        if course:
            course_scores[course].append(score)
        if score < 0.5 and kp:
            wrong_points.append(kp)
            wrong_courses[course].append(kp)
        details.append({
            "id": qid,
            "course_name": course,
            "knowledge_point": kp,
            "correct": correct,
            "score": score,
        })

    course_mastery = {
        course: round(sum(scores) / len(scores), 4)
        for course, scores in course_scores.items()
        if scores
    }
    return {
        "knowledge_base": kp_scores,
        "course_mastery": course_mastery,
        "weak_points": list(dict.fromkeys(wrong_points)),
        "wrong_courses": dict(wrong_courses),
        "details": details,
    }


def _infer_profile_from_interview(answers: list[dict]) -> dict:
    text = " ".join(str(item.get("answer") or "") for item in answers)
    first_answer = str(answers[0].get("answer") or "").strip() if answers else ""

    preferred: list[str] = []
    if any(key in text for key in ["图", "图解", "可视化", "思维导图"]):
        preferred.append("图解/思维导图")
    if any(key in text for key in ["视频", "动画", "演示"]):
        preferred.append("视频/动画")
    if any(key in text for key in ["代码", "实验", "项目", "案例", "实操"]):
        preferred.append("代码案例/实践项目")
    if any(key in text for key in ["题", "练习", "考试", "刷题", "测验"]):
        preferred.append("题库练习")
    if any(key in text for key in ["PPT", "课件", "幻灯片"]):
        preferred.append("PPT课件")
    if not preferred:
        preferred = ["文章讲解", "题库练习"]

    if any(key in text for key in ["图", "图解", "可视化", "思维导图", "视频", "动画", "演示"]):
        cognitive_style = "视觉型"
    elif any(key in text for key in ["代码", "项目", "实验", "案例", "实操"]):
        cognitive_style = "实践型"
    else:
        cognitive_style = "混合型"

    mistake_tags: list[str] = []
    if "记不住" in text or "背" in text:
        mistake_tags.append("记忆不牢")
    if "没思路" in text or "不会做" in text or "看懂但不会" in text:
        mistake_tags.append("解题思路不足")
    if "代码" in text or "实验" in text or "实操" in text:
        mistake_tags.append("实践迁移困难")
    if "太杂" in text or "重点" in text or "体系" in text:
        mistake_tags.append("知识组织困难")

    return {
        "learning_goal": first_answer or "扎实基础，补齐薄弱点",
        "cognitive_style": cognitive_style,
        "preferred_format": preferred,
        "mistake_tendency": {
            "tags": mistake_tags or ["待持续观察"],
            "source": "AI学习面试官",
        },
        "ability_summary": "已完成对话式画像建档，系统将优先围绕薄弱课程和知识点推荐资源。",
    }

def _apply_graph_marks(diagnosis: dict, graph_marks: dict) -> tuple[dict, list[str]]:
    weak_points = list(diagnosis.get("weak_points") or [])
    high_risk = []
    for kp, mark in (graph_marks or {}).items():
        if mark in {"unfamiliar", "focus"}:
            if kp not in weak_points:
                weak_points.append(kp)
        if mark == "familiar" and kp in weak_points:
            high_risk.append(kp)
    diagnosis["weak_points"] = weak_points
    diagnosis["high_risk_points"] = high_risk
    return diagnosis, weak_points


def _weak_courses_from_diagnosis(diagnosis: dict) -> list[dict]:
    wrong_courses = diagnosis.get("wrong_courses") or {}
    course_mastery = diagnosis.get("course_mastery") or {}
    items = []
    for course, mastery in course_mastery.items():
        if mastery >= 0.65 and not wrong_courses.get(course):
            continue
        weak_kps = wrong_courses.get(course) or []
        items.append({
            "name": course,
            "knowledge_points": "、".join(weak_kps) if weak_kps else "基础概念",
            "difficulty_types": ["概念理解不透彻"] if weak_kps else ["待进一步诊断"],
            "impacts": ["后续课程听不懂"],
            "goal": "扎实基础",
            "strategies": ["概念精讲", "专项练习"],
            "course_ability_scores": {
                "知识记忆": 6,
                "逻辑推理": 6,
                "应用实践": 5,
                "信息整合": 6,
                "应试能力": 6,
            },
        })
    return items[:6]


def _knowledge_graphs_for_courses(diagnostic_courses: list[dict], major: str = "") -> dict:
    return {
        course["course_name"]: _safe_kp_graph(course["course_name"], major)
        for course in diagnostic_courses
        if course.get("course_name")
    }


def _course_name_key(courses: list[dict]) -> tuple[str, ...]:
    return tuple(sorted(str(course.get("course_name") or "") for course in courses if course.get("course_name")))


def _cached_micro_quiz(db: Session, user_id: str, diagnostic_courses: list[dict]) -> dict | None:
    target_key = _course_name_key(diagnostic_courses)
    if not target_key:
        return None
    sessions = (
        db.query(ProfileOnboardingSession)
        .filter(
            ProfileOnboardingSession.user_id == user_id,
            ProfileOnboardingSession.status.in_(["started", "finished"]),
        )
        .order_by(ProfileOnboardingSession.created_at.desc())
        .limit(12)
        .all()
    )
    for session in sessions:
        if _course_name_key(session.diagnostic_courses or []) != target_key:
            continue
        micro_quiz = session.micro_quiz or {}
        if micro_quiz.get("questions"):
            cached = dict(micro_quiz)
            meta = dict(cached.get("meta") or {})
            meta["cached"] = True
            cached["meta"] = meta
            return cached
    return None


def _session_payload(session: ProfileOnboardingSession, knowledge_graphs: dict | None = None) -> dict:
    payload = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "mode": session.mode,
        "status": session.status,
        "stage": session.stage,
        "available_courses": session.available_courses or [],
        "diagnostic_courses": session.diagnostic_courses or [],
        "micro_quiz": session.micro_quiz or {},
        "interview_answers": session.interview_answers or [],
        "graph_marks": session.graph_marks or {},
        "diagnosis": session.diagnosis or {},
        "interview_question": INTERVIEW_QUESTIONS[len(session.interview_answers or [])]
        if len(session.interview_answers or []) < len(INTERVIEW_QUESTIONS) else None,
    }
    payload["knowledge_graphs"] = knowledge_graphs or {}
    if session.status == "generating":
        payload["message"] = "正在生成多课程微测验，请稍候"
        payload["progress"] = 0.18
        payload["interview_question"] = None
    elif session.status == "blocked" and not payload.get("message"):
        payload["message"] = "未生成合格诊断题，请检查 LLM 配置或稍后重试"
        payload["interview_question"] = None
    return payload


def _is_stale_generating(session: ProfileOnboardingSession, seconds: int = 180) -> bool:
    if session.status != "generating":
        return False
    updated_at = session.updated_at or session.created_at
    if not updated_at:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated_at > timedelta(seconds=seconds)


async def _generate_micro_quiz_job(session_id: str) -> None:
    db = SessionLocal()
    try:
        session = db.query(ProfileOnboardingSession).filter(
            ProfileOnboardingSession.session_id == session_id
        ).first()
        if not session or session.status != "generating":
            return
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == session.user_id).first()
        diagnostic_courses = session.diagnostic_courses or []
        knowledge_graphs = _knowledge_graphs_for_courses(diagnostic_courses, profile.major if profile else "")
        try:
            micro_quiz = await generate_micro_quiz(diagnostic_courses, knowledge_graphs) if diagnostic_courses else {
                "questions": [],
                "meta": {
                    "generated_by": "llm",
                    "generation_failures": [],
                },
            }
        except Exception as exc:
            micro_quiz = {
                "questions": [],
                "meta": {
                    "generated_by": "llm",
                    "generation_failures": [{"reason": f"background_generation_failed: {str(exc)[:160]}"}],
                },
            }
        has_questions = bool(micro_quiz.get("questions"))
        session.micro_quiz = micro_quiz
        session.status = "started" if has_questions else "blocked"
        session.stage = "micro_quiz" if has_questions else "blocked"
        db.commit()
    finally:
        db.close()


@router.post("/prepare")
def prepare_onboarding(req: OnboardingStartRequest, db: Session = Depends(get_db)):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == req.user_id).first()
    available = _available_courses(profile)
    return {
        "ok": True,
        "status": "ready" if available else "blocked",
        "available_courses": available,
        "message": "" if available else "当前专业暂无可用于对话式建档的课程知识点图谱",
    }


@router.post("/start")
async def start_onboarding(
    req: OnboardingStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == req.user_id).first()
    available = _available_courses(profile)
    selected_names = set(req.course_names or [])
    diagnostic_courses = [
        course for course in available
        if not selected_names or course["course_name"] in selected_names
    ][:3]

    knowledge_graphs = _knowledge_graphs_for_courses(diagnostic_courses, profile.major if profile else "")
    cached_quiz = _cached_micro_quiz(db, req.user_id, diagnostic_courses)
    micro_quiz = cached_quiz or {
        "questions": [],
        "meta": {
            "generated_by": "llm",
            "status": "pending",
            "generation_failures": [],
        },
    }
    has_questions = bool(micro_quiz.get("questions"))
    if not available:
        status = "blocked"
        stage = "blocked"
        message = "当前专业暂无可用于对话式建档的课程知识点图谱"
    elif not diagnostic_courses:
        status = "blocked"
        stage = "blocked"
        message = "未选择有效的可诊断课程"
    elif has_questions:
        status = "started"
        stage = "micro_quiz"
        message = ""
    else:
        status = "generating"
        stage = "micro_quiz_generating"
        message = "正在生成多课程微测验，请稍候"
    session = ProfileOnboardingSession(
        session_id=uuid.uuid4().hex,
        user_id=req.user_id,
        mode=req.mode,
        status=status,
        stage=stage,
        available_courses=available,
        diagnostic_courses=diagnostic_courses,
        micro_quiz=micro_quiz,
        diagnosis={},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    if status == "generating":
        background_tasks.add_task(_generate_micro_quiz_job, session.session_id)
    payload = _session_payload(session)
    payload["knowledge_graphs"] = knowledge_graphs
    payload["interview_question"] = INTERVIEW_QUESTIONS[0] if status == "started" else None
    payload["message"] = message or payload.get("message", "")
    return payload


@router.get("/{session_id}")
def get_onboarding_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ProfileOnboardingSession).filter(
        ProfileOnboardingSession.session_id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="建档会话不存在")
    if _is_stale_generating(session):
        session.status = "blocked"
        session.stage = "blocked"
        session.micro_quiz = {
            "questions": [],
            "meta": {
                "generated_by": "llm",
                "generation_failures": [{"reason": "generation_timeout"}],
            },
        }
        db.commit()
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == session.user_id).first()
    knowledge_graphs = _knowledge_graphs_for_courses(session.diagnostic_courses or [], profile.major if profile else "")
    return _session_payload(session, knowledge_graphs)


@router.post("/answer")
def answer_onboarding(req: OnboardingAnswerRequest, db: Session = Depends(get_db)):
    session = db.query(ProfileOnboardingSession).filter(
        ProfileOnboardingSession.session_id == req.session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="建档会话不存在")
    if session.status == "generating":
        raise HTTPException(status_code=409, detail="微测验仍在生成中，请稍候")
    if session.status == "blocked":
        raise HTTPException(status_code=400, detail="当前会话没有可诊断课程")

    if req.step == "micro_quiz":
        if not (session.micro_quiz or {}).get("questions"):
            raise HTTPException(status_code=400, detail="当前建档会话没有可提交的微测验题目")
        answers = req.payload.get("answers") or {}
        diagnosis = _diagnose(session.micro_quiz or {}, answers)
        session.micro_quiz_answers = answers
        session.diagnosis = diagnosis
        session.stage = "interview"
        details = _as_list(diagnosis.get("details"))
        wrong_questions = []
        for item in details:
            if item.get("correct"):
                continue
            question = next(
                (
                    q for q in _as_list((session.micro_quiz or {}).get("questions"))
                    if str(q.get("id")) == str(item.get("id"))
                ),
                {},
            )
            wrong_questions.append({
                "question": question,
                "knowledge_points": [item.get("knowledge_point")] if item.get("knowledge_point") else [],
                "user_answer": answers.get(str(item.get("id"))),
                "correct_answer": question.get("answer") if isinstance(question, dict) else "",
            })
        quiz_score = (
            sum(1 for item in details if item.get("correct")) / len(details)
            if details else 0.0
        )
        apply_quiz_result(
            db,
            session.user_id,
            diagnosis.get("knowledge_base") or {},
            wrong_questions,
            quiz_score,
            resource_id=None,
            alpha=0.8,
        )
        progress = 0.35
        result = {
            "ok": True,
            "progress": progress,
            "next_step": "interview",
            "next_question": INTERVIEW_QUESTIONS[0],
            "diagnosis": diagnosis,
            "mastery_updated": True,
            "updated_knowledge_points": list((diagnosis.get("knowledge_base") or {}).keys()),
        }
    elif req.step == "interview":
        answers = list(session.interview_answers or [])
        question = req.payload.get("question") or (
            INTERVIEW_QUESTIONS[len(answers)] if len(answers) < len(INTERVIEW_QUESTIONS) else ""
        )
        answers.append({"question": question, "answer": req.payload.get("answer", "")})
        session.interview_answers = answers
        if len(answers) < len(INTERVIEW_QUESTIONS):
            session.stage = "interview"
            result = {
                "ok": True,
                "progress": round(0.35 + len(answers) / len(INTERVIEW_QUESTIONS) * 0.3, 2),
                "next_step": "interview",
                "next_question": INTERVIEW_QUESTIONS[len(answers)],
            }
        else:
            session.stage = "knowledge_graph"
            result = {"ok": True, "progress": 0.72, "next_step": "knowledge_graph"}
    elif req.step == "knowledge_graph":
        marks = req.payload.get("marks") or {}
        session.graph_marks = marks
        session.stage = "finish_ready"
        result = {"ok": True, "progress": 0.9, "next_step": "finish"}
    else:
        raise HTTPException(status_code=400, detail="不支持的建档步骤")

    db.commit()
    return result


@router.post("/finish")
async def finish_onboarding(req: OnboardingFinishRequest, db: Session = Depends(get_db)):
    session = db.query(ProfileOnboardingSession).filter(
        ProfileOnboardingSession.session_id == req.session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="建档会话不存在")
    if session.status == "blocked":
        raise HTTPException(status_code=400, detail="当前会话没有可诊断课程")

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == session.user_id).first()
    if not profile:
        profile = StudentProfile(user_id=session.user_id)
        db.add(profile)

    diagnosis = dict(session.diagnosis or {})
    diagnosis, weak_points = _apply_graph_marks(diagnosis, session.graph_marks or {})
    interview_profile = _infer_profile_from_interview(session.interview_answers or [])
    course_mastery = diagnosis.get("course_mastery") or {}
    weak_courses = _weak_courses_from_diagnosis(diagnosis)
    evidence = {
        "knowledge_base": "多课程微测验 + 知识图谱自评",
        "course_mastery": "按课程内知识点诊断结果聚合",
        "weak_points": "微测验错题 + 图谱陌生/重点标记",
        "learning_goal": "AI学习面试官回答",
        "cognitive_style": "AI学习面试官回答",
        "preferred_format": "AI学习面试官回答",
        "mistake_tendency": "微测验错题 + 面试困难描述",
    }

    evidence["knowledge_base"] = "微测验题目正确率自动更新；知识图谱自评不改掌握度"
    profile.course_mastery = {**(profile.course_mastery or {}), **course_mastery}
    profile.weak_points = list(dict.fromkeys((profile.weak_points or []) + weak_points))[-20:]
    profile.weak_courses = weak_courses or (profile.weak_courses or [])
    profile.learning_goal = interview_profile["learning_goal"] or profile.learning_goal
    profile.cognitive_style = interview_profile["cognitive_style"] or profile.cognitive_style
    profile.preferred_format = list(dict.fromkeys((profile.preferred_format or []) + interview_profile["preferred_format"]))
    profile.mistake_tendency = interview_profile["mistake_tendency"]
    profile.profile_evidence = {**(profile.profile_evidence or {}), **evidence}
    profile.ability_summary = interview_profile["ability_summary"]

    session.status = "finished"
    session.stage = "finished"
    session.diagnosis = diagnosis
    db.commit()
    db.refresh(profile)

    snapshot = {
        "knowledge_base": profile.knowledge_base or {},
        "course_mastery": profile.course_mastery or {},
        "weak_points": profile.weak_points or [],
        "learning_goal": profile.learning_goal or "",
        "cognitive_style": profile.cognitive_style or "",
        "preferred_format": profile.preferred_format or [],
    }
    db.add(ProfileHistory(
        user_id=session.user_id,
        trigger="onboarding",
        snapshot=snapshot,
        delta={"profile_evidence": evidence},
    ))
    db.commit()

    await emit("profile.updated", {"user_id": session.user_id})

    return {
        "ok": True,
        "profile": ProfileResponse.model_validate(profile).model_dump(),
        "course_mastery": course_mastery,
        "weak_courses": weak_courses,
        "evidence_summary": evidence,
        "next_recommendations": [
            {"course_name": item["name"], "knowledge_points": item["knowledge_points"]}
            for item in weak_courses[:3]
        ],
    }
