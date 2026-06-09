from fastapi import APIRouter, Query, HTTPException
from core.database import SessionLocal
from models.weak_point import WeakPoint
from services.recommendation_service import get_active_recommendations, _to_dict

router = APIRouter(prefix="/api/weak-points", tags=["薄弱知识点"])


@router.get("")
def list_weak_points(user_id: str = Query(...), status: str = Query(None)):
    db = SessionLocal()
    try:
        q = db.query(WeakPoint).filter(WeakPoint.user_id == user_id)
        if status:
            q = q.filter(WeakPoint.status == status)
        return [_to_dict(w) for w in q.order_by(WeakPoint.mastery_score).all()]
    finally:
        db.close()


@router.get("/recommendations")
def get_recommendations(user_id: str = Query(...), limit: int = Query(10)):
    return get_active_recommendations(user_id, limit)


@router.patch("/{wp_id}/status")
def update_status(wp_id: int, status: str, user_id: str = Query(...)):
    if status not in {"active", "reviewing", "mastered", "archived"}:
        raise HTTPException(400, "status 须为 active/reviewing/mastered/archived 之一")
    db = SessionLocal()
    try:
        wp = db.query(WeakPoint).filter(WeakPoint.id == wp_id, WeakPoint.user_id == user_id).first()
        if not wp:
            raise HTTPException(404, "未找到")
        wp.status = status
        db.commit()
        return _to_dict(wp)
    finally:
        db.close()


@router.delete("/{wp_id}")
def delete_weak_point(wp_id: int, user_id: str = Query(...)):
    db = SessionLocal()
    try:
        wp = db.query(WeakPoint).filter(WeakPoint.id == wp_id, WeakPoint.user_id == user_id).first()
        if not wp:
            raise HTTPException(404, "未找到")
        db.delete(wp)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
