from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from models.focus import FocusSession
from models.profile_history import ProfileHistory
from models.student import StudentProfile
from services.event_service import emit


RESOURCE_FORMAT_LABELS = {
    "article": "文章",
    "quiz": "互动练习",
    "code": "实操案例",
    "anime": "动画",
    "mindmap": "思维导图",
    "ppt": "PPT课件",
    "video": "视频",
    "evaluation": "学习评估",
}


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def get_or_create_profile(db: Session, user_id: str) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if profile:
        return profile
    profile = StudentProfile(user_id=user_id)
    db.add(profile)
    db.flush()
    return profile


def update_profile_evidence(profile: StudentProfile, evidence: dict[str, str]) -> None:
    merged = dict(profile.profile_evidence or {})
    merged.update({key: value for key, value in evidence.items() if value})
    profile.profile_evidence = merged


def update_knowledge_scores(profile: StudentProfile, kp_scores: dict[str, float], alpha: float = 0.3) -> dict[str, float]:
    if not kp_scores:
        return {}
    kb = dict(profile.knowledge_base or {})
    alpha = max(0.0, min(float(alpha), 1.0))
    changed: dict[str, float] = {}
    for kp, raw_score in kp_scores.items():
        if not kp:
            continue
        score = max(0.0, min(float(raw_score), 1.0))
        old = float(kb.get(kp, 0.0) or 0.0)
        new_score = round(old * (1 - alpha) + score * alpha, 4)
        kb[kp] = new_score
        changed[kp] = new_score
    profile.knowledge_base = kb
    return changed


def set_knowledge_scores(profile: StudentProfile, kp_scores: dict[str, float]) -> dict[str, float]:
    return {}


def add_weak_points(profile: StudentProfile, weak_points: list[str], limit: int = 20) -> list[str]:
    points = [str(kp).strip() for kp in weak_points if str(kp).strip()]
    if not points:
        return as_list(profile.weak_points)
    merged = list(dict.fromkeys(as_list(profile.weak_points) + points))[-limit:]
    profile.weak_points = merged
    return merged


def remove_mastered_weak_points(
    profile: StudentProfile,
    changed_scores: dict[str, float],
    threshold: float = 0.7,
) -> list[str]:
    mastered = {
        str(kp).strip()
        for kp, score in changed_scores.items()
        if str(kp).strip() and float(score or 0.0) >= threshold
    }
    if not mastered:
        return as_list(profile.weak_points)
    profile.weak_points = [
        kp for kp in as_list(profile.weak_points)
        if str(kp).strip() not in mastered
    ]
    return profile.weak_points


def snapshot_profile(profile: StudentProfile) -> dict[str, Any]:
    return {
        "knowledge_base": profile.knowledge_base or {},
        "weak_points": profile.weak_points or [],
        "mistake_tendency": profile.mistake_tendency or {},
        "resource_feedback_profile": profile.resource_feedback_profile or {},
        "preferred_format": profile.preferred_format or [],
        "focus_stamina_score": profile.focus_stamina_score,
        "focus_peak_hours": profile.focus_peak_hours or [],
        "focus_interrupt_rate": profile.focus_interrupt_rate,
        "focus_weekly_avg_min": profile.focus_weekly_avg_min,
        "profile_evidence": profile.profile_evidence or {},
    }


def record_history(
    db: Session,
    user_id: str,
    trigger: str,
    profile: StudentProfile,
    delta: dict | None = None,
    snapshot: dict | None = None,
) -> None:
    db.add(ProfileHistory(
        user_id=user_id,
        trigger=trigger,
        snapshot=snapshot or snapshot_profile(profile),
        delta=delta or {},
    ))


def emit_profile_updated(user_id: str) -> None:
    async def _emit():
        await emit("profile.updated", {"user_id": user_id})

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_emit())
    except RuntimeError:
        asyncio.run(_emit())


def apply_quiz_result(
    db: Session,
    user_id: str,
    kp_scores: dict[str, float],
    wrong_questions: list[dict],
    score: float,
    resource_id: int | None = None,
    alpha: float = 0.3,
    mastery_threshold: float = 0.7,
) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    old_kb = dict(profile.knowledge_base or {})
    changed_kb = update_knowledge_scores(profile, kp_scores, alpha=alpha)
    mastery_delta = {
        kp: {
            "before": round(float(old_kb.get(kp, 0.0) or 0.0), 4),
            "after": round(float(after or 0.0), 4),
        }
        for kp, after in changed_kb.items()
    }

    wrong_kps: list[str] = []
    question_type_counts = Counter()
    for item in wrong_questions:
        question = as_dict(item.get("question"))
        wrong_kps.extend(as_list(item.get("knowledge_points")))
        question_type_counts[str(question.get("type") or "unknown")] += 1
    wrong_kps = list(dict.fromkeys([kp for kp in wrong_kps if kp]))
    if wrong_kps:
        add_weak_points(profile, wrong_kps)
    weak_points = remove_mastered_weak_points(profile, changed_kb, mastery_threshold)

    tendency = dict(profile.mistake_tendency or {})
    by_kp = dict(tendency.get("by_knowledge_point") or {})
    for kp in wrong_kps:
        by_kp[kp] = int(by_kp.get(kp, 0) or 0) + 1
    by_type = dict(tendency.get("by_question_type") or {})
    for q_type, count in question_type_counts.items():
        by_type[q_type] = int(by_type.get(q_type, 0) or 0) + count
    tendency.update({
        "by_knowledge_point": by_kp,
        "by_question_type": by_type,
        "last_quiz": {
            "resource_id": resource_id,
            "score": score,
            "wrong_knowledge_points": wrong_kps,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    })
    profile.mistake_tendency = tendency
    update_profile_evidence(profile, {
        "knowledge_base": "题库提交：按题目级知识点正确率更新",
        "weak_points": "题库错题知识点",
        "mistake_tendency": "题库错题统计",
    })
    record_history(db, user_id, "quiz", profile, {
        "resource_id": resource_id,
        "score": score,
        "knowledge_base": changed_kb,
        "knowledge_mastery_delta": mastery_delta,
        "wrong_knowledge_points": wrong_kps,
        "weak_points": weak_points,
        "update_alpha": alpha,
    })
    db.commit()
    emit_profile_updated(user_id)
    return {
        "profile": profile,
        "updated_knowledge_points": list(changed_kb.keys()),
        "knowledge_mastery_delta": mastery_delta,
    }


def apply_resource_completed(
    db: Session,
    user_id: str,
    resource_type: str,
    resource_id: int,
    knowledge_points: list[str],
    mastery_score: float,
    alpha: float,
) -> StudentProfile:
    profile = get_or_create_profile(db, user_id)
    update_profile_evidence(profile, {
        "resource_completed": "学习资源完成记录",
        "knowledge_base": "掌握度仅由题目正确率自动更新；资源完成不改掌握度",
    })
    record_history(db, user_id, "resource_completed", profile, {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "knowledge_points": [kp for kp in knowledge_points if kp],
        "knowledge_base": {},
        "note": "资源完成只记录学习行为，不更新掌握度",
    })
    db.commit()
    emit_profile_updated(user_id)
    return profile


def apply_resource_feedback(
    db: Session,
    user_id: str,
    resource,
    feedback: str,
    note: str | None = None,
) -> StudentProfile:
    profile = get_or_create_profile(db, user_id)
    resource_type = getattr(resource, "resource_type", "") or ""
    feedback_profile = dict(profile.resource_feedback_profile or {})
    counts = dict(feedback_profile.get("counts") or {})
    counts[feedback] = int(counts.get(feedback, 0) or 0) + 1

    by_type = dict(feedback_profile.get("by_resource_type") or {})
    type_counts = dict(by_type.get(resource_type) or {})
    type_counts[feedback] = int(type_counts.get(feedback, 0) or 0) + 1
    by_type[resource_type] = type_counts

    format_scores = dict(feedback_profile.get("format_scores") or {})
    label = RESOURCE_FORMAT_LABELS.get(resource_type, resource_type)
    if feedback == "helpful":
        format_scores[label] = int(format_scores.get(label, 0) or 0) + 1
    elif feedback == "irrelevant":
        format_scores[label] = int(format_scores.get(label, 0) or 0) - 1

    current_preferred = [str(fmt).strip() for fmt in as_list(profile.preferred_format) if str(fmt).strip()]
    if feedback == "helpful" and label and label not in current_preferred:
        current_preferred.append(label)
    elif feedback == "irrelevant":
        current_preferred = [fmt for fmt in current_preferred if fmt != label]
    feedback_preferred = [
        fmt for fmt, value in sorted(format_scores.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ]
    profile.preferred_format = list(dict.fromkeys(current_preferred + feedback_preferred))[:8]

    feedback_profile.update({
        "counts": counts,
        "by_resource_type": by_type,
        "format_scores": format_scores,
        "last_feedback": {
            "resource_id": getattr(resource, "id", None),
            "resource_type": resource_type,
            "course_name": getattr(resource, "course_name", None),
            "knowledge_points": as_list(getattr(resource, "knowledge_points", [])),
            "feedback": feedback,
            "note": note or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    })
    profile.resource_feedback_profile = feedback_profile
    update_profile_evidence(profile, {
        "resource_feedback_profile": "学习资源反馈",
        "preferred_format": "学习资源反馈" if feedback in {"helpful", "irrelevant"} else "",
    })
    record_history(db, user_id, "resource_feedback", profile, {
        "feedback": feedback,
        "resource_id": getattr(resource, "id", None),
        "resource_type": resource_type,
        "preferred_format": profile.preferred_format or [],
    })
    db.commit()
    emit_profile_updated(user_id)
    return profile


def apply_path_step_completed(
    db: Session,
    user_id: str,
    course_name: str,
    step_title: str,
    matched_kps: list[str],
    course_completed: bool = False,
) -> StudentProfile:
    profile = get_or_create_profile(db, user_id)
    update_profile_evidence(profile, {
        "path_progress": "学习路径步骤验收通过",
    })
    record_history(db, user_id, "path_step", profile, {
        "course_name": course_name,
        "step_title": step_title,
        "matched_knowledge_points": matched_kps,
        "course_completed": course_completed,
        "knowledge_base": {},
        "note": "路径步骤只记录验收证据，知识点掌握度由题目级测验结果更新",
    })
    db.commit()
    emit_profile_updated(user_id)
    return profile


def apply_focus_session(db: Session, user_id: str) -> StudentProfile:
    profile = get_or_create_profile(db, user_id)
    sessions = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user_id)
        .order_by(FocusSession.started_at.desc())
        .all()
    )
    if not sessions:
        return profile

    total = len(sessions)
    completed = sum(1 for session in sessions if session.completed)
    now = datetime.now(timezone.utc)
    four_weeks_ago = now - timedelta(weeks=4)
    recent = [
        session for session in sessions
        if (session.started_at.replace(tzinfo=timezone.utc) if session.started_at.tzinfo is None else session.started_at) >= four_weeks_ago
    ]
    weekly_avg = round(sum(session.duration_min for session in recent) / 4) if recent else 0
    interrupt_rate = round((total - completed) / total, 4) if total else 0
    hour_counts = Counter(session.started_at.hour for session in sessions if session.completed)
    peak_hours = sorted([hour for hour, _ in hour_counts.most_common(3)])

    profile.focus_weekly_avg_min = weekly_avg
    profile.focus_interrupt_rate = interrupt_rate
    profile.focus_peak_hours = peak_hours
    profile.focus_stamina_score = 8 if weekly_avg > 300 and interrupt_rate < 0.1 else (5 if weekly_avg > 100 else 2)
    update_profile_evidence(profile, {
        "focus_stamina_score": "专注学习记录",
        "focus_peak_hours": "专注学习记录",
        "focus_interrupt_rate": "专注学习记录",
    })
    record_history(db, user_id, "focus", profile, {
        "weekly_avg_min": weekly_avg,
        "interrupt_rate": interrupt_rate,
        "peak_hours": peak_hours,
        "focus_stamina_score": profile.focus_stamina_score,
    })
    db.commit()
    emit_profile_updated(user_id)
    return profile
