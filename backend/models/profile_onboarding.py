from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String

from core.database import Base


class ProfileOnboardingSession(Base):
    __tablename__ = "profile_onboarding_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, index=True)
    user_id = Column(String, index=True)
    mode = Column(String, default="first_build")
    status = Column(String, default="started")
    stage = Column(String, default="course_confirm")
    available_courses = Column(JSON, default=list)
    diagnostic_courses = Column(JSON, default=list)
    micro_quiz = Column(JSON, default=dict)
    micro_quiz_answers = Column(JSON, default=dict)
    interview_answers = Column(JSON, default=list)
    graph_marks = Column(JSON, default=dict)
    diagnosis = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
