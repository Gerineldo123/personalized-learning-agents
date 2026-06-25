from sqlalchemy import Column, Integer, String, DateTime, JSON
from core.database import Base
from datetime import datetime


class PptSession(Base):
    __tablename__ = "ppt_sessions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, index=True)
    user_id = Column(String, index=True)
    topic = Column(String)
    course_name = Column(String)
    knowledge_points = Column(JSON, default=list)
    status = Column(String, default="created")  # created / generating / completed / failed
    docmee_token = Column(String)
    ppt_id = Column(String)
    cover_url = Column(String)
    template_id = Column(String)
    file_url = Column(String)
    pptx_file = Column(String)
    resource_id = Column(Integer)
    error_message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
