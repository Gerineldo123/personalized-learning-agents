from sqlalchemy import Column, Integer, String, DateTime, JSON, UniqueConstraint
from core.database import Base
from datetime import datetime, timezone


class MistakeQuestion(Base):
    __tablename__ = "mistake_questions"
    __table_args__ = (
        UniqueConstraint('user_id', 'resource_id', 'question_id', name='uq_mistake_user_resource_question'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    resource_id = Column(Integer, index=True)
    question_id = Column(Integer, index=True)
    reason = Column(String, default="manual")
    question = Column(JSON)
    user_answer = Column(String, default="")
    correct_answer = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
