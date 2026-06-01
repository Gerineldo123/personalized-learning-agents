from sqlalchemy import Column, Integer, String, DateTime, JSON
from core.database import Base
from datetime import datetime


class LearningResource(Base):
    __tablename__ = "learning_resources"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True)
    resource_type = Column(String)
    title = Column(String)
    content = Column(JSON)
    tags = Column(JSON)
    pinned = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
