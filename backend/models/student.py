from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
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
    current_semester = Column(Integer)
    discipline = Column(String)
    cross_disciplines = Column(JSON)
    ability_scores = Column(JSON)
    weak_courses = Column(JSON)
    ability_summary = Column(String)
    mistake_tendency = Column(JSON)
    course_mastery = Column(JSON)
    profile_evidence = Column(JSON)
    resource_feedback_profile = Column(JSON)

    focus_stamina_score = Column(Integer)
    focus_peak_hours = Column(JSON)
    focus_interrupt_rate = Column(Float)
    focus_weekly_avg_min = Column(Integer)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
