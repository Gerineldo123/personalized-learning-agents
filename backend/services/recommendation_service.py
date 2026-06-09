"""
推荐引擎服务：基于 SM-2 间隔重复算法管理薄弱知识点生命周期。

SM-2 规则：
  quality 0~1（本次答题质量）
  quality >= 0.6：interval *= ease_factor；ease_factor += 0.1 - (1-quality)*0.8
  quality <  0.6：interval = 1（重置）
  ease_factor 最小值 = 1.3，interval 最大值 = 180 天
"""
from datetime import datetime, timezone, timedelta
from core.database import SessionLocal
from models.weak_point import WeakPoint

MIN_EASE = 1.3
MAX_INTERVAL = 180
MASTERY_THRESHOLD = 0.75   # score >= 此值且 quiz_count >= 5 → mastered
REVIEWING_THRESHOLD = 0.5  # score >= 此值 → reviewing


def _sm2_update(wp: WeakPoint, quality: float) -> None:
    if quality >= 0.6:
        if wp.quiz_count == 1:
            wp.interval_days = 1
        elif wp.quiz_count == 2:
            wp.interval_days = 6
        else:
            wp.interval_days = max(1, int(wp.interval_days * wp.ease_factor))
        wp.ease_factor = max(MIN_EASE, wp.ease_factor + 0.1 - (1 - quality) * 0.8)
    else:
        wp.interval_days = 1
    wp.interval_days = min(wp.interval_days, MAX_INTERVAL)
    wp.next_review_at = datetime.now(timezone.utc) + timedelta(days=wp.interval_days)


def _update_status(wp: WeakPoint) -> None:
    if wp.status == "archived":
        return
    if wp.mastery_score >= MASTERY_THRESHOLD and wp.quiz_count >= 5:
        wp.status = "mastered"
    elif wp.mastery_score >= REVIEWING_THRESHOLD:
        wp.status = "reviewing"
    else:
        wp.status = "active"


def record_quiz_result(user_id: str, weak_point_name: str, correct: bool) -> None:
    """记录一次答题结果，更新 SM-2 状态。知识点不存在则自动创建。"""
    db = SessionLocal()
    try:
        wp = db.query(WeakPoint).filter(
            WeakPoint.user_id == user_id,
            WeakPoint.name == weak_point_name,
            WeakPoint.status != "archived",
        ).first()
        if not wp:
            wp = WeakPoint(user_id=user_id, name=weak_point_name)
            db.add(wp)
        wp.quiz_count += 1
        if correct:
            wp.correct_count += 1
        wp.mastery_score = wp.correct_count / wp.quiz_count
        wp.last_quizzed_at = datetime.now(timezone.utc)
        _sm2_update(wp, 1.0 if correct else 0.0)
        _update_status(wp)
        db.commit()
    finally:
        db.close()


def upsert_weak_points_batch(user_id: str, names: list[str]) -> None:
    """批量新增薄弱知识点，已存在（任何状态）则跳过。"""
    if not names:
        return
    db = SessionLocal()
    try:
        existing = {
            wp.name for wp in db.query(WeakPoint).filter(
                WeakPoint.user_id == user_id
            ).with_entities(WeakPoint.name).all()
        }
        for name in names:
            if name and name not in existing:
                db.add(WeakPoint(user_id=user_id, name=name))
                existing.add(name)
        db.commit()
    finally:
        db.close()


def get_active_recommendations(user_id: str, limit: int = 10) -> list[dict]:
    """
    返回推荐列表（active + reviewing），按优先级排序：
      1. 已到期需复习（next_review_at <= now）
      2. 掌握度低
      3. 最久未做题
    """
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        wps = db.query(WeakPoint).filter(
            WeakPoint.user_id == user_id,
            WeakPoint.status.in_(["active", "reviewing"]),
        ).all()

        def sort_key(wp: WeakPoint):
            overdue = wp.next_review_at is not None and wp.next_review_at <= now
            return (not overdue, wp.mastery_score, wp.last_quizzed_at or datetime.min)

        wps.sort(key=sort_key)
        return [_to_dict(w) for w in wps[:limit]]
    finally:
        db.close()


def _to_dict(w: WeakPoint) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "status": w.status,
        "mastery_score": round(w.mastery_score, 2),
        "quiz_count": w.quiz_count,
        "interval_days": w.interval_days,
        "next_review_at": w.next_review_at.isoformat() if w.next_review_at else None,
        "last_quizzed_at": w.last_quizzed_at.isoformat() if w.last_quizzed_at else None,
        "related_resource_ids": w.related_resource_ids or [],
    }
