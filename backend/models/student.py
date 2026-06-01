from sqlalchemy import Column, Integer, String, DateTime, JSON
from core.database import Base
from datetime import datetime, timezone


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, unique=True, index=True)

    major = Column(String)
    grade = Column(String)
    knowledge_base = Column(JSON)
    cognitive_style = Column(String)
    weak_points = Column(JSON)
    learning_goal = Column(String)
    preferred_format = Column(JSON)

    education_level = Column(String)
    education_year = Column(String)
    discipline = Column(String)
    cross_disciplines = Column(JSON)
    ability_scores = Column(JSON)
    weak_courses = Column(JSON)
    ability_summary = Column(String)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
