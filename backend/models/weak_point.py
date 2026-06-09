from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime, timezone
from core.database import Base


class WeakPoint(Base):
    __tablename__ = "weak_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)

    # 状态机：active / reviewing / mastered / archived
    status = Column(String, default="active", nullable=False)

    mastery_score = Column(Float, default=0.0)
    quiz_count = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)

    # SM-2 间隔重复字段
    ease_factor = Column(Float, default=2.5)
    interval_days = Column(Integer, default=1)
    next_review_at = Column(DateTime, nullable=True)

    related_resource_ids = Column(JSON, default=list)

    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_quizzed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
