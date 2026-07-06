from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.course_path import CoursePath
from models.focus import FocusSession
from models.mistake_question import MistakeQuestion
from models.resource import LearningResource
from models.student import StudentProfile


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _short(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _question_text(question: Any) -> str:
    if isinstance(question, dict):
        for key in ("question", "title", "stem", "content"):
            if question.get(key):
                return str(question.get(key))
        return json.dumps(question, ensure_ascii=False)
    return str(question or "")


def _question_options(question: Any) -> list:
    if not isinstance(question, dict):
        return []
    options = question.get("options") or []
    if not isinstance(options, list):
        return []
    normalized = []
    for option in options[:6]:
        if isinstance(option, dict):
            key = option.get("key") or option.get("label") or ""
            text = option.get("text") or option.get("content") or option.get("value") or ""
            normalized.append({"key": key, "text": _short(text, 120)})
        else:
            normalized.append(_short(option, 140))
    return normalized


def _question_kps(question: Any, resource: LearningResource | None) -> list[str]:
    points: list[str] = []
    if isinstance(question, dict):
        raw_points = question.get("knowledge_points") or question.get("knowledge_point") or question.get("kp")
        if isinstance(raw_points, list):
            points.extend(str(item) for item in raw_points if item)
        elif raw_points:
            points.append(str(raw_points))
    if resource:
        points.extend(str(item) for item in _as_list(resource.knowledge_points) if item)
    return list(dict.fromkeys(points))[:8]


def _profile_context(profile: StudentProfile | None) -> dict:
    if not profile:
        return {"found": False}
    return {
        "found": True,
        "major": profile.major or "",
        "grade": profile.grade or "",
        "current_semester": profile.current_semester,
        "education_level": profile.education_level or "",
        "discipline": profile.discipline or "",
        "learning_goal": profile.learning_goal or "",
        "cognitive_style": profile.cognitive_style or "",
        "preferred_format": _as_list(profile.preferred_format),
        "knowledge_base": _as_dict(profile.knowledge_base),
        "weak_points": _as_list(profile.weak_points),
        "weak_courses": _as_list(profile.weak_courses)[:8],
        "course_mastery": _as_dict(profile.course_mastery),
        "mistake_tendency": _as_dict(profile.mistake_tendency),
        "resource_feedback_profile": _as_dict(profile.resource_feedback_profile),
        "focus_profile": {
            "stamina_score": profile.focus_stamina_score,
            "peak_hours": _as_list(profile.focus_peak_hours),
            "interrupt_rate": profile.focus_interrupt_rate,
            "weekly_avg_min": profile.focus_weekly_avg_min,
        },
    }


def _mistake_context(db: Session, user_id: str, limit: int = 8) -> dict:
    rows = (
        db.query(MistakeQuestion, LearningResource)
        .outerjoin(LearningResource, MistakeQuestion.resource_id == LearningResource.id)
        .filter(MistakeQuestion.user_id == user_id)
        .order_by(MistakeQuestion.last_wrong_at.desc(), MistakeQuestion.created_at.desc())
        .limit(limit)
        .all()
    )
    total = db.query(MistakeQuestion).filter(MistakeQuestion.user_id == user_id).count()
    items = []
    for mistake, resource in rows:
        question = mistake.question or {}
        items.append({
            "id": mistake.id,
            "resource_id": mistake.resource_id,
            "resource_title": resource.title if resource else "",
            "course_name": resource.course_name if resource else "",
            "knowledge_points": _question_kps(question, resource),
            "question": _short(_question_text(question), 420),
            "options": _question_options(question),
            "user_answer": mistake.user_answer or "",
            "correct_answer": mistake.correct_answer or "",
            "reason": mistake.reason or "",
            "analysis": _as_dict(mistake.analysis),
            "wrong_count": mistake.wrong_count or 1,
            "last_wrong_at": _iso(mistake.last_wrong_at or mistake.created_at),
        })
    return {"total": total, "recent": items}


def _resource_context(db: Session, user_id: str, limit: int = 10) -> dict:
    resources = (
        db.query(LearningResource)
        .filter(LearningResource.user_id == user_id)
        .order_by(LearningResource.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "recent": [
            {
                "id": item.id,
                "title": item.title or "",
                "type": item.resource_type or "",
                "course_name": item.course_name or "",
                "knowledge_points": _as_list(item.knowledge_points),
                "learning_status": item.learning_status or "not_started",
                "progress": item.progress or 0,
                "completed_at": _iso(item.completed_at),
                "created_at": _iso(item.created_at),
            }
            for item in resources
        ]
    }


def _path_context(db: Session, user_id: str, limit: int = 3) -> dict:
    paths = (
        db.query(CoursePath)
        .filter(CoursePath.user_id == user_id, CoursePath.status.in_(["active", "completed"]))
        .order_by(CoursePath.updated_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for path in paths:
        steps = _as_list(path.steps)
        pending = [step for step in steps if isinstance(step, dict) and step.get("status") != "done"]
        items.append({
            "id": path.id,
            "course_name": path.course_name or "",
            "status": path.status or "",
            "progress": path.progress or 0,
            "done_steps": path.done_steps or 0,
            "total_steps": path.total_steps or len(steps),
            "next_steps": [
                {
                    "title": _short(step.get("title"), 120),
                    "description": _short(step.get("description"), 180),
                    "resource_ids": _as_list(step.get("resource_ids")),
                }
                for step in pending[:3]
            ],
        })
    return {"items": items}


def _focus_context(db: Session, user_id: str) -> dict:
    sessions = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user_id)
        .order_by(FocusSession.started_at.desc())
        .limit(20)
        .all()
    )
    if not sessions:
        return {"summary": "无专注记录", "recent": []}
    total_min = sum(item.duration_min for item in sessions)
    completed = sum(1 for item in sessions if item.completed)
    return {
        "summary": f"累计专注{total_min}分钟，完成{completed}/{len(sessions)}次",
        "recent": [
            {
                "duration_min": item.duration_min,
                "completed": bool(item.completed),
                "started_at": _iso(item.started_at),
            }
            for item in sessions[:5]
        ],
    }


def _curriculum_context(profile: StudentProfile | None) -> dict:
    if not profile or not profile.major:
        return {"found": False}
    try:
        from services.curriculum_service import (
            build_user_curriculum_graph,
            infer_current_semester,
            load_curriculum_by_major,
            semester_rank,
        )

        current_semester = infer_current_semester(profile.grade or "", profile.current_semester)
        curriculum = load_curriculum_by_major(profile.major)
        graph = build_user_curriculum_graph(
            curriculum,
            profile.knowledge_base or {},
            current_semester,
            {},
        )
        nodes = graph.get("nodes") or []
        priority = {"weak": 0, "learning": 1, "recommended": 2, "available": 3, "completed": 4, "locked": 5}
        sorted_nodes = sorted(nodes, key=lambda node: (
            priority.get(node.get("status"), 9),
            abs(semester_rank(node.get("semester") or current_semester) - current_semester),
        ))
        return {
            "found": True,
            "major_name": graph.get("meta", {}).get("major_name") or profile.major,
            "current_semester": current_semester,
            "relation_count": len(graph.get("links") or []),
            "courses": [
                {
                    "course_id": item.get("course_id"),
                    "name": item.get("name") or item.get("id"),
                    "semester": item.get("semester"),
                    "status": item.get("status"),
                    "mastery": item.get("mastery"),
                    "category": item.get("category"),
                    "kp_file": item.get("kp_file"),
                }
                for item in sorted_nodes[:16]
            ],
        }
    except Exception as exc:
        return {"found": False, "error": str(exc)}


def build_agent_context(db: Session, user_id: str, profile: StudentProfile | None = None) -> dict:
    profile = profile or db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    return {
        "profile": _profile_context(profile),
        "mistakes": _mistake_context(db, user_id),
        "resources": _resource_context(db, user_id),
        "learning_paths": _path_context(db, user_id),
        "curriculum": _curriculum_context(profile),
        "focus": _focus_context(db, user_id),
    }


def build_mistake_prompt_context(mistakes: dict | None, limit: int = 6) -> str:
    mistakes = mistakes or {}
    recent = _as_list(mistakes.get("recent"))[:limit]
    total = int(mistakes.get("total") or 0)
    if total <= 0 or not recent:
        return "错题本为空：当前没有可用于分析的历史错题记录。"

    kp_counts: dict[str, int] = {}
    for item in recent:
        for point in _as_list(item.get("knowledge_points")):
            kp_counts[str(point)] = kp_counts.get(str(point), 0) + 1
    weak_points = sorted(kp_counts.items(), key=lambda pair: pair[1], reverse=True)

    lines = [
        f"错题本共有 {total} 条记录，以下列出最近 {len(recent)} 条真实错题。",
    ]
    if weak_points:
        lines.append("高频知识点：" + "、".join(f"{point}({count})" for point, count in weak_points[:8]))

    for index, item in enumerate(recent, start=1):
        knowledge_points = "、".join(_as_list(item.get("knowledge_points"))) or "未标注"
        options = _as_list(item.get("options"))
        option_text = ""
        if options:
            option_text = "；选项：" + " / ".join(_short(opt.get("text") if isinstance(opt, dict) else opt, 80) for opt in options[:4])
        analysis = _as_dict(item.get("analysis"))
        analysis_text = analysis.get("error_analysis") or analysis.get("summary") or ""
        lines.append(
            f"{index}. 课程：{item.get('course_name') or '未分类'}；知识点：{knowledge_points}；"
            f"题目：{_short(item.get('question'), 220)}{option_text}；"
            f"学生答案：{item.get('user_answer') or '未填写'}；正确答案：{item.get('correct_answer') or '未提供'}；"
            f"错误次数：{item.get('wrong_count') or 1}"
            + (f"；错因分析：{_short(analysis_text, 160)}" if analysis_text else "")
        )
    return "\n".join(lines)


def build_agent_context_text(context: dict) -> str:
    mistakes = context.get("mistakes") or {}
    payload = {
        "使用要求": [
            "这是系统已读取到的真实模块数据。",
            "当错题本/学习资源/学习路径/知识图谱列表非空时，不要声称无法访问这些数据。",
            "涉及错题分析时，必须优先基于 mistakes.recent 中的题目、学生答案、正确答案和知识点进行分析。",
            "如果 mistakes.total > 0，禁止说错题本为空、没有历史错题或缺少错题内容。",
            "涉及资源推荐或学习规划时，结合 resources、learning_paths、curriculum 和 profile。",
        ],
        "mistakes": mistakes,
        "mistake_summary": build_mistake_prompt_context(mistakes),
        "学生画像": context.get("profile") or {},
        "错题本": mistakes,
        "学习资源": context.get("resources") or {},
        "学习路径": context.get("learning_paths") or {},
        "知识图谱": context.get("curriculum") or {},
        "专注记录": context.get("focus") or {},
    }
    return json.dumps(payload, ensure_ascii=False)
