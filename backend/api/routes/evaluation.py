from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from api.deps import get_db
from models.resource import LearningResource

router = APIRouter(prefix="/api/evaluation", tags=["评估"])


@router.get("")
def list_evaluations(
    user_id: str,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    evaluations = (
        db.query(LearningResource)
        .filter(
            LearningResource.user_id == user_id,
            LearningResource.resource_type == "evaluation",
        )
        .order_by(LearningResource.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(evaluations),
        "items": [
            {
                "id": e.id,
                "title": e.title,
                "content": e.content,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in evaluations
        ],
    }


@router.get("/{evaluation_id}")
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    e = db.query(LearningResource).get(evaluation_id)
    if not e or e.resource_type != "evaluation":
        return {"found": False}
    return {
        "found": True,
        "id": e.id,
        "title": e.title,
        "content": e.content,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
