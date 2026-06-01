from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from core.database import Base
from datetime import datetime, timezone


class CoursePath(Base):
    __tablename__ = "course_paths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    course_name = Column(String, index=True)
    steps = Column(JSON)
    total_steps = Column(Integer, default=0)
    done_steps = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
