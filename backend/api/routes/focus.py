from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from collections import Counter
from api.deps import get_db
from models.focus import FocusSession

router = APIRouter(prefix="/focus", tags=["专注"])


class FocusSessionIn(BaseModel):
    started_at: str
    duration_min: int
    completed: bool = True


@router.post("/session", status_code=201)
def create_session(body: FocusSessionIn, user_id: str, db: Session = Depends(get_db)):
    session = FocusSession(
        user_id=user_id,
        started_at=datetime.fromisoformat(body.started_at.replace("Z", "+00:00")),
        duration_min=body.duration_min,
        completed=body.completed,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id}


@router.get("/stats")
def get_stats(user_id: str, db: Session = Depends(get_db)):
    sessions = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user_id)
        .order_by(FocusSession.started_at.desc())
        .all()
    )
    if not sessions:
        return {
            "total_sessions": 0, "completed_sessions": 0,
            "interrupt_rate": 0, "total_minutes": 0,
            "weekly_avg_min": 0, "peak_hours": [], "recent_sessions": [],
        }

    total = len(sessions)
    completed = sum(1 for s in sessions if s.completed)
    total_min = sum(s.duration_min for s in sessions)

    now = datetime.now(timezone.utc)
    four_weeks_ago = now - timedelta(weeks=4)
    recent = [s for s in sessions if (s.started_at.replace(tzinfo=timezone.utc) if s.started_at.tzinfo is None else s.started_at) >= four_weeks_ago]
    weekly_avg = round(sum(s.duration_min for s in recent) / 4)

    hour_counts = Counter(s.started_at.hour for s in sessions if s.completed)
    peak_hours = [h for h, _ in hour_counts.most_common(3)]

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "interrupt_rate": round((total - completed) / total, 2),
        "total_minutes": total_min,
        "weekly_avg_min": weekly_avg,
        "peak_hours": peak_hours,
        "recent_sessions": [
            {"started_at": s.started_at.isoformat(), "duration_min": s.duration_min, "completed": s.completed}
            for s in sessions[:20]
        ],
    }
