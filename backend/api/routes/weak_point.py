from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.deps import get_db
from models.student import StudentProfile

router = APIRouter(prefix="/weak-point", tags=["薄弱点"])


@router.get("/list")
def get_weak_points(user_id: str, db: Session = Depends(get_db)):
    """获取学生的薄弱知识点列表"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile or not profile.weak_points:
        return {"weak_points": []}
    return {"weak_points": profile.weak_points}


@router.delete("/remove")
def remove_weak_point(user_id: str, point: str, db: Session = Depends(get_db)):
    """移除一个已掌握的薄弱知识点"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile or not profile.weak_points:
        return {"weak_points": []}
    updated = [p for p in profile.weak_points if p != point]
    profile.weak_points = updated
    db.commit()
    return {"weak_points": updated}
