from sqlalchemy import Column, Integer, String, Boolean, DateTime
from core.database import Base
from datetime import datetime, timezone


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    started_at = Column(DateTime, nullable=False)
    duration_min = Column(Integer, nullable=False)
    completed = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
