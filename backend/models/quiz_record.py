from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from core.database import Base
from datetime import datetime, timezone


class QuizRecord(Base):
    __tablename__ = "quiz_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    resource_id = Column(Integer)
    answers = Column(JSON)
    score = Column(Float)
    time_spent = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
