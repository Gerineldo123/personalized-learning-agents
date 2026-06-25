from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
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
    course_name = Column(String, index=True)
    knowledge_points = Column(JSON, default=list)
    kp_weights = Column(JSON, default=dict)
    tag_confidence = Column(Float, default=0.0)
    learning_status = Column(String, default="not_started")
    progress = Column(Float, default=0.0)
    completed_at = Column(DateTime)
    pinned = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
