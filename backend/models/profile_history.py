from sqlalchemy import Column, Integer, String, DateTime, JSON
from core.database import Base
from datetime import datetime, timezone


class ProfileHistory(Base):
    __tablename__ = "profile_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    trigger = Column(String)          # "quiz" | "focus" | "path_step" | "chat" | "questionnaire"
    snapshot = Column(JSON)           # 更新后的 ability_scores + weak_points 快照
    delta = Column(JSON)              # 本次变化的字段
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
